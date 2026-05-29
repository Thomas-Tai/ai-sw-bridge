# `--checkpoint-encrypt` — Design (W3.1)

**Status:** Design approved, implementation pending (W3.1-impl).
**Authors:** v0.13 closure track.
**Cross-refs:** *(retired v0.13.0; see decisions.md 2026-05-28 entry)* §4.2, *(retired v0.13.0; see decisions.md 2026-05-28 entry)* §5.

This document is the binding design for the `--checkpoint-encrypt` flag.
It commits to the encryption library, the key-source contract, the
schema additions, the CLI surface, and the test contract. The impl
task (W3.1-impl, Sonnet/GLM) fills in the bodies; behavior must match
this document.

---

## 1. Problem statement

The L4 checkpoint store at `./.checkpoints/<part>.sqlite` contains
`locals_snapshot` and `com_call_log` strings drawn directly from the
user's `*_locals.txt` files. For users whose locals encode trade-secret
dimensions, the SQLite file is itself a trade-secret artifact
(*(retired v0.13.0; see decisions.md 2026-05-28 entry)* §3.1, threat
model §5.1 "L4 checkpoint store exposure").

The existing mitigations — `.gitignore` defaults, no telemetry uplink,
no auto-backup — protect against accidental egress but leave the file
readable to anyone with filesystem access on the machine (multi-user
machines, backups, lost laptops, malware that exfiltrates the working
directory).

`--checkpoint-encrypt` adds at-rest encryption to close this gap.

## 2. Non-goals

- **Not transport encryption.** The bridge has no network surface; the
  flag protects data at rest on disk only.
- **Not key escrow.** Lost key = lost checkpoint history. The bridge
  does not stash a recovery key anywhere. This is documented
  prominently and matches the privacy_review §4.2 guarantee.
- **Not protection against an attacker who controls the running
  process.** While a build is active and the key is in memory, the
  decrypted values are reachable via a memory dump. The threat model
  is "stolen disk image" / "shared filesystem," not "compromised
  process."
- **Not retroactive encryption of existing plain DBs.** A separate
  one-shot migration tool (`ai-sw-checkpoint migrate`) handles that;
  it's a follow-up, not part of W3.1.

## 3. Library choice — app-layer Fernet (vs. SQLCipher)

**Decision:** App-layer encryption of the two sensitive columns
(`locals_snapshot`, `com_call_log`) using `cryptography.fernet`
(AES-128-CBC + HMAC-SHA256, AEAD).

**Why not SQLCipher** (the industry-standard choice for this class
of problem):

| Concern | SQLCipher | App-layer Fernet |
|---|---|---|
| Pure-Python install | ❌ native binary; pysqlcipher3 wheels lag; Windows users often need a compiler | ✅ `cryptography` ships universal wheels |
| Transparent to existing queries | ✅ open the file with a key, every query just works | ⚠️ encrypted columns can't be used in `WHERE`/`LIKE` |
| Dependency footprint | ⚠️ pulls SQLCipher + bundled OpenSSL | ✅ `cryptography` already an indirect dep via `keyring` |
| Audit surface | ✅ widely deployed, formal review | ✅ Fernet is well-reviewed; AEAD primitive is conservative |
| File format | proprietary SQLCipher header | plain SQLite + extra `_meta` table |
| Forensics / repair | only SQLCipher tools | any SQLite tool can see the schema (cells are opaque blobs) |

The "encrypted columns can't be used in `WHERE`" downside is acceptable:
the existing `CheckpointStore.query()` filters on `part_name`, `status`,
and `timestamp` — none of those are encrypted. Indexes on
`(part_name, timestamp)` and `(status)` continue to work as today.

The pure-Python install path is load-bearing: the project's
"pywin32 LATE BINDING ONLY, no exotic native deps" discipline (see
`CONTRIBUTING.md`) extends to this choice. Adding a SQLCipher dep
would create a Windows install failure path that doesn't exist today.

**Library spec:**

```
cryptography >= 41.0
```

Already a transitive dep via `keyring` on most platforms. Pin in
`pyproject.toml` `[project.optional-dependencies] crypto`.

## 4. Key-source contract

The `--checkpoint-encrypt <source>` flag accepts one of four forms:

| Form | Meaning | Key handling |
|---|---|---|
| `env:NAME` | Read 32-byte URL-safe base64 from env var `NAME` | Direct — value must be a Fernet key |
| `file:/path/to/keyfile` | Read first line of file | Direct — first line must be a Fernet key |
| `keyring:SERVICE` | Fetch key from OS keyring under service `SERVICE`, account `ai-sw-bridge` | Direct — keyring value must be a Fernet key |
| `prompt` | Prompt user via `getpass.getpass()` interactively | PBKDF2-HMAC-SHA256, 600k iter, salt from `_meta.kdf_salt` |

**Default:** no encryption (flag absent → existing unencrypted store).

**Why no PBKDF2 on `env:`/`file:`/`keyring:` sources?**
PBKDF2 with bad parameters is a footgun. By insisting these forms
carry a Fernet key directly, we eliminate the
"silently-weakened-by-low-iterations" failure mode. Users who want a
passphrase-derived key use `prompt`; the bridge owns the KDF params.

**Why no `pass:LITERAL` form?**
Passing a key as a literal CLI argument leaks it into shell history,
`ps aux`, and process listings. Rejected.

**Key generation helper:**

```
$ ai-sw-checkpoint genkey
gAAAAABg...  (44-char URL-safe base64 = 32 bytes)
```

Generates a fresh Fernet key, writes to stdout, exits 0. The user
saves it to env var, file, or keyring as they prefer.

## 5. Schema additions

New `_meta` table, single row, populated when encryption is first
enabled on a DB:

```sql
CREATE TABLE IF NOT EXISTS _meta (
    encrypted_at     TEXT NOT NULL,          -- ISO timestamp
    encryption_algo  TEXT NOT NULL,          -- 'fernet-v1'
    encrypted_cols   TEXT NOT NULL,          -- JSON: ["locals_snapshot","com_call_log"]
    kdf_algo         TEXT,                   -- 'pbkdf2-sha256-600000' when prompt source
    kdf_salt         TEXT,                   -- base64 16-byte salt when prompt source
    key_fingerprint  TEXT NOT NULL           -- sha256(key)[:16] for re-key validation
);
```

**Auto-detection:** `CheckpointStore.__init__` checks for `_meta` on
first connect. If present, encryption mode is active and a `key_source`
constructor arg is required. If absent, plain mode (today's behavior).

**`key_fingerprint`:** lets `rekey` verify the supplied "old" key is
in fact the current one before rewriting cells. Prevents the
"oops-I-used-the-wrong-old-key-and-now-the-DB-is-double-encrypted-junk"
class of error.

## 6. Encrypted-cell format

Each encrypted cell stores:

```
fernet_v1:<base64_token>
```

The literal prefix `fernet_v1:` is the version tag. Future algorithm
changes (`fernet_v2:`, `chacha20:`, ...) write a new prefix while
old cells continue to be decryptable by the prefix dispatch.

Plain (pre-encryption) cells have no prefix; the read path detects
the prefix and falls back to "return as-is" when absent — which lets
a DB transition from plain to encrypted without rewriting old rows
(though the `migrate` tool does so explicitly).

## 7. Module surface

New module: `src/ai_sw_bridge/checkpoint/crypto.py`.

```python
class KeySource(ABC):
    """Resolves a --checkpoint-encrypt source string to a Fernet key."""

    @classmethod
    def parse(cls, source: str, meta: dict | None = None) -> "KeySource": ...

    @abstractmethod
    def get_key(self) -> bytes: ...  # 32-byte URL-safe base64

    @abstractmethod
    def fingerprint(self) -> str: ...  # sha256(key)[:16]


class EnvKeySource(KeySource): ...
class FileKeySource(KeySource): ...
class KeyringKeySource(KeySource): ...
class PromptKeySource(KeySource): ...


def encrypt_cell(plaintext: str, key: bytes) -> str:
    """Wrap one cell. Returns 'fernet_v1:<token>'."""


def decrypt_cell(blob: str, key: bytes) -> str:
    """Unwrap one cell. Handles prefix dispatch. Returns plaintext.

    No prefix → returned as-is (plain cell, pre-encryption).
    Wrong key → raises InvalidToken (caller decides how to surface).
    Unknown prefix → raises ValueError.
    """


def generate_key() -> bytes:
    """Return a fresh Fernet.generate_key() result."""


class KeySourceError(Exception):
    """Raised when a key source string can't be resolved."""
```

`CheckpointStore` gains:

```python
def __init__(
    self,
    part_name: str,
    root: Path | None = None,
    *,
    key_source: KeySource | None = None,    # NEW
) -> None: ...
```

When `key_source` is set, `insert_pending` / `commit` /
`record_rollback` wrap the two sensitive columns before INSERT/UPDATE,
and `get` / `query` unwrap on SELECT. The wire-format outside the DB
(the `Checkpoint` dataclass) carries plaintext — encryption is purely
storage.

## 8. CLI surface

**Two new CLIs:**

`ai-sw-build --checkpoint-encrypt <source>` — extends the existing
`--checkpoint` flag with at-rest encryption. Implies `--checkpoint`.

`ai-sw-checkpoint` (new entry point) with subcommands:

| Subcommand | Purpose | Args |
|---|---|---|
| `genkey` | Print a fresh Fernet key to stdout | none |
| `info <part>` | Show encryption status of `.checkpoints/<part>.sqlite` (meta row, fingerprint, encrypted_cols) | `<part>` |
| `rekey <part> --from <source> --to <source>` | Re-encrypt all cells with a new key | `<part>`, `--from`, `--to` |
| `migrate <part> --to <source>` | One-shot: encrypt a previously plain DB | `<part>`, `--to` |

**Wire format:** two-stream contract preserved.
- `genkey` → key to stdout as plain text (NOT JSON — it's a credential
  that may be piped to `cat > keyfile` or similar tools that don't
  parse JSON). stderr carries the usage hint.
- `info` / `rekey` / `migrate` → JSON to stdout, human messages to
  stderr.

**Stability tier:** `experimental` (new surface).

## 9. Failure modes

| Symptom | Cause | Surface |
|---|---|---|
| `--checkpoint-encrypt env:KEY` but `$KEY` unset | Missing env var | `KeySourceError` → CLI rc=2, stderr `"env var KEY not set"` |
| Wrong key on `--checkpoint-encrypt` against an already-encrypted DB | Fingerprint mismatch on `_meta.key_fingerprint` | `KeySourceError` → CLI rc=2, stderr `"key fingerprint mismatch; refusing to write"` BEFORE any cell rewrite |
| Key file exists but contains malformed base64 | Fernet rejects on construction | `KeySourceError` → CLI rc=2 |
| Plain DB + `--checkpoint-encrypt` set + `_meta` absent | First-time encryption — opt-in via `--checkpoint-encrypt-init` (W3.1 ships this as a one-shot guard; without it, the bridge refuses to add `_meta` mid-build) | rc=2, stderr `"DB is plain; run 'ai-sw-checkpoint migrate' to enable encryption"` |
| `rekey` partial failure (DB write error mid-rewrite) | SQLite transaction rolls back | `_meta` and cells stay consistent — either all rows have new key or all have old |
| Concurrent builds with different key sources | Second build sees fingerprint mismatch | rc=2 BEFORE any write; existing build unaffected |

The `--checkpoint-encrypt-init` guard exists because silently
encrypting a plain DB on a regular build is a footgun: if the user
forgets to supply the key on a subsequent build, the DB is
unreadable. Explicit migration via `ai-sw-checkpoint migrate` makes
the state change visible.

## 10. Interaction with `checkpoint_redact.py` (W3.2)

`tools/checkpoint_redact.py` consumes encrypted DBs and produces
sanitized output. The flow:

1. Open the source DB with `CheckpointStore(..., key_source=...)`.
2. Iterate rows via `query()` — values come out decrypted (plaintext).
3. Apply the redaction substitution (`<redacted_local>` per
   privacy_review §4.3).
4. Write to a fresh plain DB (no `_meta` table).

The redacted output is intentionally plain — once the secrets are
substituted out, encryption serves no purpose. This means the W3.2
tool needs to accept `--from-key-source <source>` to read an
encrypted source, but the output is always plain.

W3.2 imports `KeySource.parse` from this module; that is the entire
shared surface.

## 11. Test contract

Tests live in `tests/checkpoint/test_crypto_contract.py`. Initial
state is a set of `@pytest.mark.skip(reason="W3.1-impl pending")`
markers; the impl task removes the markers as bodies land.

### 11.1 Cell wrap/unwrap

- `test_encrypt_cell_roundtrip` — wrap then unwrap = original.
- `test_decrypt_cell_no_prefix_returns_as_is` — plain cells pass through.
- `test_decrypt_cell_wrong_key_raises_invalid_token`.
- `test_decrypt_cell_unknown_prefix_raises_value_error`.
- `test_encrypt_cell_format_starts_with_version_tag`.

### 11.2 Key source resolution

- `test_env_key_source_reads_env_var` — set env, parse `env:NAME`,
  `get_key()` returns the bytes.
- `test_env_key_source_missing_var_raises_key_source_error`.
- `test_file_key_source_reads_first_line`.
- `test_file_key_source_missing_file_raises_key_source_error`.
- `test_keyring_key_source_reads_keyring` — patched `keyring.get_password`.
- `test_prompt_key_source_derives_via_pbkdf2` — patched `getpass`,
  asserts PBKDF2 produces expected key for known salt + passphrase.
- `test_fingerprint_is_sha256_prefix_16` — sanity check for the
  fingerprint contract.

### 11.3 Store behavior with encryption

- `test_encrypted_store_round_trip` — insert_pending + commit + get,
  values come back identical.
- `test_encrypted_store_query_filters_still_work` — query by status,
  by since, by limit — all OK on encrypted DB.
- `test_encrypted_store_rejects_wrong_key_on_open` — fingerprint
  check fires before any read.
- `test_plain_store_unchanged_when_no_key_source` — opening a plain
  DB without `key_source` works exactly as today.
- `test_encrypted_store_persists_meta_row_once` — `_meta` is created
  on first encrypted insert, not rewritten on subsequent ones.

### 11.4 CLI

- `test_genkey_emits_valid_fernet_key` — subprocess invoke, parse
  stdout, construct Fernet, succeed.
- `test_info_subcommand_reports_encryption_state` — JSON payload
  carries `encryption_algo`, `key_fingerprint`, `encrypted_at`.
- `test_rekey_atomic_under_simulated_io_error` — patched sqlite
  raises mid-rewrite; assert old key still works.
- `test_two_stream_contract_genkey` — stdout = raw key only, stderr
  = usage hint, no JSON on stdout.

### 11.5 Integration

- `test_build_with_checkpoint_encrypt_env_creates_encrypted_db` —
  end-to-end against the mock SW; assert `_meta` exists and cells
  start with `fernet_v1:`.

## 12. Acceptance criteria (W3.1-impl ships when ALL pass)

- All tests in §11 green (markers removed).
- `cryptography` added to `pyproject.toml` `[project.optional-dependencies] crypto` and to `requirements.txt`.
- `--checkpoint-encrypt env:KEY` round-trips on the
  `examples/drive_roller/spec.json` build path.
- `ai-sw-checkpoint genkey | head -c 44 > /tmp/k && ai-sw-checkpoint info <part>` reports the correct fingerprint after a build with `--checkpoint-encrypt file:/tmp/k`.
- `lint-imports` still kept (the new module stays inside the
  `checkpoint/` lane).
- `mypy src` still clean.
- `black --check .` (full repo) still clean.
- Privacy review updated: §4.2 status moves from "post-v0.11" to
  "shipped in v0.13".

## 13. Open questions (resolved at impl time, not now)

- **Should `prompt` source cache the derived key for the build's
  duration, or re-prompt per row?** Cache for build duration —
  per-row prompt would be useless. Re-prompt would defeat the build
  loop's atomicity.
- **Should `keyring` use the `keyring` Python lib or fall back to
  pure-Python `cryptography`?** `keyring` lib is the standard;
  optional dep guarded by ImportError in `KeyringKeySource.parse`.
- **Should `_meta.key_fingerprint` be salted to prevent rainbow
  lookups?** No — the fingerprint is purely an "is this the same key
  I had before" check, never compared across DBs. SHA-256 prefix is
  fine.

---

## Appendix A — Why not column-level deterministic encryption?

Deterministic encryption (same plaintext → same ciphertext) would
let us filter on encrypted columns. We reject it because:

1. The `locals_snapshot` column contains free-form JSON; identical
   snapshots across rows would be visible as identical ciphertexts,
   leaking "feature X had the same params in build 47 and build 89."
2. Determinism rules out AEAD with random IVs, which weakens the
   primitive considerably.
3. The existing query API doesn't filter on these columns. There is
   no use case to preserve.

Fernet's per-cell random IV gives semantic security and meets our
threat model.

## Appendix B — Cryptography library footprint

`cryptography` is already pulled into the environment by `keyring`
(via `cryptography.hazmat.primitives.serialization` for keyring
backends on some platforms) and by `pip` itself (for wheel
verification). Adding it as a first-class dep doesn't change the
install surface for the vast majority of users.

For users who explicitly don't want encryption: the flag is opt-in.
The `crypto` extra is opt-in: `pip install ai-sw-bridge` works
without it; `pip install ai-sw-bridge[crypto]` adds the dep.
