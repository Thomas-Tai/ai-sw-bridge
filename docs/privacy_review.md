# Privacy Review

Data inventory, sensitivity classification, egress paths, and consent
gates for `ai-sw-bridge`. This document is the public-facing
counterpart of the bridge's privacy posture — anything an
adopter / security reviewer / DPO needs to understand what the bridge
collects, where it stores it, and what (if anything) leaves the
machine.

**North-star principle:** *local-only by default; egress is opt-in,
explicit, and per-artifact-redacted.*

Last reviewed: 2026-05-28 (v0.13.0 release prep).

---

## 1. Data inventory

Everything the bridge can read, write, or store, classified by
sensitivity tier.

| Artifact | Where it lives | Tier | Egress path |
|---|---|---|---|
| **JSON spec** (e.g. `examples/<part>/spec.json`) | User-controlled directory | **PUBLIC** — declarative geometry definition, no user identity | None (user-owned) |
| **`*_locals.txt`** (parameter values for parametric specs) | Adjacent to spec | **SENSITIVE** — may encode internal part-number prefixes, project codenames, customer-confidential dimensions | Scrubbed by `tools/spec_redact.py` before sharing |
| **Built `.SLDPRT`** files | User's SW workspace | **SENSITIVE** — full 3D geometry, may be IP | None (SW owns the file; bridge writes via SW's SaveAs3) |
| **Checkpoint DB** (`.checkpoints/<part>.sqlite`) | Repo root by default; configurable via `--checkpoint-root` | **SENSITIVE** — `locals_snapshot` + `com_call_log` columns contain the parameter values + the COM call sequence. Encrypted at rest when `--checkpoint-encrypt <key-source>` is set (Fernet, see `docs/checkpoint_encryption_design.md`) | Scrubbed by `tools/checkpoint_redact.py` before sharing |
| **Telemetry SQLite** (`.telemetry/metrics.db`) | Repo root | **AGGREGATE-ONLY** — counters + histogram buckets + trace IDs. **No PII, no spec values, no file paths.** | Never auto-uploaded. Manual export via `tools/export_metrics.py` requires `.telemetry/consent.txt` to exist |
| **Bug-report bundles** (`bug_report_<ts>.zip` from `tools/bundle_bug_report.py`) | User's repo root | **SCRUBBED-SENSITIVE** — collects spec + error envelopes + telemetry; runs the redaction pipeline before zipping | Manual upload by user to wherever they file the report |
| **Build manifest sidecars** (`build_metrics.json`, `build_brep.json`) | Adjacent to built `.SLDPRT` | **SENSITIVE** — feature names + durations + B-rep fingerprints; same sensitivity as the part itself | None (user-owned) |
| **Spec validation errors** (stdout from `ai-sw-build` / MCP tool returns) | Caller's process | **SENSITIVE-IN-CONTEXT** — error messages may quote `*_locals.txt` values | Caller decides what to do with stdout |
| **Environment-derived state** (path to active SW doc, RevisionNumber, etc.) | Active SW process | **SENSITIVE** — file path reveals project structure | Observed by `sw_get_active_doc` etc.; user is the caller, never auto-collected |

## 2. Sensitivity tiers

- **PUBLIC** — fine to share verbatim. Spec JSON definitions of
  geometry primitives.
- **SENSITIVE** — never auto-uploaded; must pass through a redaction
  pipeline before any sharing. Locals files, full geometry, paths.
- **SENSITIVE-IN-CONTEXT** — the bytes themselves aren't secret, but
  their relationship to the caller's context might be (e.g. an error
  message quoting a locals value). Treat as SENSITIVE when in doubt.
- **AGGREGATE-ONLY** — counter / histogram data with no per-call
  attribution; safe for opt-in export.

## 3. Egress paths

The bridge does **not** call out to the network. There is no
auto-upload of any artifact. The four egress paths are all
operator-driven:

1. **`tools/export_metrics.py`** — opt-in JSON export of telemetry.
   Refuses to run unless `.telemetry/consent.txt` exists. Output is
   AGGREGATE-ONLY data only. User uploads the JSON manually if they
   choose to.
2. **`tools/bundle_bug_report.py`** — opt-in bundling of recent
   builds + telemetry + spec submissions. Runs the redaction
   pipeline (path scrubbing, locals stripping, trade-secret-pattern
   masking per `.ai-sw-bridge.toml`) before producing the `.zip`.
   User uploads manually.
3. **`tools/spec_redact.py`** + **`tools/checkpoint_redact.py`** —
   user-invoked one-shot redactors for ad-hoc sharing.
4. **Spec / build artifacts that the user themselves chooses to
   share** — outside the bridge's responsibility.

The MCP server (`ai-sw-mcp`) speaks stdio JSON-RPC to a single
client process (typically Claude Desktop). It does not open network
sockets. Whatever the MCP client does with the responses is the
client's privacy boundary, not the bridge's.

## 4. Consent gates

Operations that *could* exfiltrate data are gated behind explicit
consent files or flags:

| Operation | Gate |
|---|---|
| Telemetry write to `.telemetry/metrics.db` | Always enabled; AGGREGATE-ONLY data; no PII so no consent gate. |
| Telemetry export via `tools/export_metrics.py` | **Requires `.telemetry/consent.txt` to exist.** Refuses otherwise. |
| Bug-report bundle telemetry inclusion | **Same consent file**, OR pass `--no-telemetry` to bundle without it. |
| Checkpoint snapshots | `--checkpoint` flag on `ai-sw-build`; opt-in per build. |
| Encrypted checkpoints | `--checkpoint-encrypt <key-source>` flag; implies `--checkpoint`. Bridge does NOT escrow keys; lost key = lost history. |

## 5. PII commitment

**The bridge does not collect PII.** The only identity-shaped fields
ever recorded are:

- Path components (which may reveal usernames if the user works under
  `C:\Users\<name>\...`). These are scrubbed to `<HOME>\...` by the
  redaction pipeline before any egress.
- SOLIDWORKS revision number (e.g. "32.1.0"). Aggregate only.

No telemetry counter has a per-user, per-machine, or per-session
attribution beyond a per-process UUID4 `trace_id` that exists for
debug-log correlation and is regenerated every process start.

## 6. Encryption at rest

Per `docs/checkpoint_encryption_design.md`:

- **Default:** plain SQLite. Acceptable for repos behind disk
  encryption (BitLocker / FileVault).
- **`--checkpoint-encrypt env:NAME`** — Fernet wrap of
  `locals_snapshot` + `com_call_log` columns. Key from env var.
- **`--checkpoint-encrypt file:/path`** — same, key from file.
- **`--checkpoint-encrypt keyring:SERVICE`** — same, key from OS
  keyring (Windows Credential Manager, macOS Keychain, etc.).
- **`--checkpoint-encrypt prompt`** — same, key derived from
  user-typed passphrase via PBKDF2-HMAC-SHA256 600k iterations.

`_meta` table (algo, fingerprint, encrypted columns) is plaintext by
design so `ai-sw-checkpoint info` works without the key.

## 7. Threats out of scope

The bridge does not defend against:

- **A compromised SOLIDWORKS install** — if the SW binary is
  malicious, COM calls are untrusted; encryption-at-rest of
  checkpoints doesn't protect against the SW process reading the
  spec live.
- **A compromised Python interpreter / pywin32** — bridge runs in
  the user's process; compromise of the host process compromises
  everything.
- **A compromised MCP client** — Claude Desktop / Cursor receives
  full tool payloads; if the client is compromised, the data it
  receives is exposed.
- **Side-channel inference from timing / metric data** — telemetry
  histograms could in principle leak structural info about specs
  (e.g., a long build duration implies many features). Out of scope;
  if you need this defense, disable telemetry by not creating
  `.telemetry/consent.txt`.

## 8. Audit log

Decisions affecting privacy posture are recorded in
[`decisions.md`](decisions.md). Material changes (new egress paths,
relaxed consent gates, new PII fields) must also update this
document and bump the "Last reviewed" date at the top.

Past entries:

- **2026-05-28** — v0.13.0 release: at-rest encryption layer
  shipped; `--checkpoint-encrypt` available across all four key
  sources; lost key explicitly documented as "lost history" per
  `CHANGELOG.md`. No new auto-egress paths.
- **2026-05-23** — Telemetry consent file requirement formalized;
  `tools/export_metrics.py` refuses without `.telemetry/consent.txt`.

---

## How to update this doc

When you add a new artifact, new egress path, or new sensitivity
classification:

1. Add the row to §1 or update the affected section.
2. Bump "Last reviewed" at the top.
3. If the change is material (new egress, new PII, relaxed gate),
   log a `decisions.md` entry referencing this section.
4. Mention in the relevant `CHANGELOG.md` entry.
