# Lane Designs — high-level reference

Compact design reference for the v0.11–v0.13 capability lanes. Each
section answers four questions:

1. **What does this lane own?** (responsibility)
2. **What are its load-bearing invariants?** (the things that, if
   broken, break the lane)
3. **Where do I look in code?** (file paths)
4. **What's the rationale?** (why this shape, what was rejected)

Companion docs:

- `docs/mcp_server_design.md` — Lane M (MCP server) — full design
- `docs/checkpoint_encryption_design.md` — L4 encryption layer
- `docs/decisions.md` — strategic decisions behind the lane shapes
- `docs/com_failure_modes.md` — failure modes referenced below
- `CODESTYLE.md` — cross-cutting code discipline

---

## L1 — B-rep interrogation

**What this lane owns.** After each feature handler completes, walk
the resulting `IFace2` set in SOLIDWORKS and produce a topological
fingerprint per feature — per-face bounding box, surface normal,
centroid. The fingerprint is then quantized (currently 6-decimal,
see `docs/DEFERRED.md` for the open tolerance question) into a
stable key that survives small rebuild noise. The LLM consumes this
manifest to reason about *which face is which* after the part has
been rebuilt.

**Load-bearing invariants.**

- **Active-configuration only.** L1 fingerprints reflect the active
  config at interrogation time; switching configs invalidates the
  manifest. Documented in `docs/known_limitations.md`.
- **Per-feature emission, not per-build.** A spec with 10 features
  emits 10 fingerprint blocks. Aggregating loses the
  before/after-feature topology delta that the resolver needs.
- **Eager-by-default, lazy-on-demand.** `--enable-flag
  brep_interrogation` enables eager walking; `--brep-mode lazy`
  defers until a manifest entry is asked for. Histogram
  `brep_interrogation_seconds{mode}` tracks the cost.

**Code:**

- `src/ai_sw_bridge/brep/interrogator.py` — per-face extraction
- `src/ai_sw_bridge/brep/fingerprint.py` — quantization + stable
  hash
- `src/ai_sw_bridge/brep/manifest.py` — per-feature block
  serialization
- `src/ai_sw_bridge/brep/resolver.py` — symbolic `face_role`
  resolution at validate time

**Rationale.** Without topological feedback, the LLM has no way to
say "fillet the top face of the boss I just extruded" — it can only
reference faces by coordinate, which is brittle. L1 turns
coordinate-references into stable symbolic references.

Alternatives rejected:

- *Single end-of-build fingerprint.* Misses the per-feature delta
  needed for symbolic resolution.
- *Hash the entire body.* Too coarse — any tiny change rebuilds the
  whole hash; useless for "which face?".
- *Per-edge fingerprints.* Doubles the surface and most resolution
  is face-based anyway.

---

## L2 — Envelope closure (error wrapping + auto-retry)

**What this lane owns.** Every COM call site through `spec/builder.py`
is wrapped by a `@com_error_boundary` decorator that catches
`pywintypes.com_error` (and dead-dispatch `AttributeError` — see
`docs/com_failure_modes.md`), classifies it into Tier A / B / C, and
emits a structured `BuildError` envelope. A hint catalog maps
recognized failure patterns to actionable hints
(`face-not-found`, `sketch-under-constrained`, etc.). The auto-retry
guard refuses identical-spec resubmissions to break LLM retry loops.

**Load-bearing invariants.**

- **No raw `com_error` reaches the CLI surface.** Either the
  boundary catches it and emits a Tier B/C envelope, OR it's a Tier
  A coding bug that propagates as-is (and gets caught by tests).
- **Hint catalog is append-only.** Removing a hint requires
  telemetry evidence that it's never triggered.
- **Anti-loop: identical-hash specs refuse retry.** `auto_retry.py`
  computes canonical-JSON SHA-256; same hash within session → return
  `identical_spec_resubmitted` exit code, no COM call.
- **Material change required for retry acceptance.** Even one
  parameter change unblocks retry; whitespace-only diff (after
  canonicalization) does not.

**Code:**

- `src/ai_sw_bridge/errors/build_error.py` — `BuildError` dataclass
  with Tier A/B/C classification, HRESULT, hint key, trace ID
- `src/ai_sw_bridge/errors/wrapper.py` — `@com_error_boundary`
  decorator at every COM call site
- `src/ai_sw_bridge/errors/hints.py` — hint catalog (currently
  13 entries; was 9 at v0.11)
- `src/ai_sw_bridge/errors/auto_retry.py` — `RetryGuard` with
  cross-session persistence via telemetry store
- `src/ai_sw_bridge/errors/circuit_breaker.py` — closed → open
  → half-open state machine (ported from
  `SolidworksMCP-python/circuit_breaker.py` — MIT)

**Rationale.** LLMs in auto-retry loops are dangerous when each
retry hits the same error and accumulates a no-progress trace. L2's
envelope + anti-loop ensures every retry is informed (hint changed,
or parameter changed) — or the loop is broken with a clear "your
last attempt was identical" message.

Alternatives rejected:

- *Just let `com_error` propagate.* Caller has no idea which Tier
  the error is or whether it's recoverable.
- *Generic retry-N-times wrapper.* Wastes attempts and obscures
  patterns; hint-aware retry only retries when the situation
  materially changed.
- *Single hint per error.* Many failures match multiple hints
  (e.g., "face not found" + "end condition mismatch"); multi-key
  resolution is more useful to LLMs.

---

## L3 — API RAG (CHM corpus retrieval)

**What this lane owns.** A locally-indexed, embedding-based search
over the SOLIDWORKS API CHM corpus. The committed index ships at
`src/ai_sw_bridge/rag/data/api_index.sqlite`; the embedder is
sentence-transformers with a default model dimension that matches
the committed index. Five `ai-sw-apidoc` subcommands (`search`,
`detail`, `members`, `examples`, `enum`) plus the matching MCP
tools.

**Load-bearing invariants.**

- **No network calls at runtime.** Embeddings are computed locally;
  the model is mirrored to repo-local storage. `make_embedder()`
  rejects any backend that would touch the network.
- **Committed index is deterministic.** `tools/build_api_index.py`
  produces the same SQLite given the same CHM input; CI verifies
  index reproducibility per the supply-chain gate.
- **Backend auto-resolution by dimension.** When the index dim
  matches `DEFAULT_DIM`, backend defaults to the cheap hash
  embedder; otherwise the full sentence-transformer is loaded.
  Avoids accidentally embedding at the wrong dimension against the
  index column.
- **Enum corpus is currently stubbed.** `sw_apidoc_enum` returns
  `{ok: false, reason: "enum_corpus_missing"}` because the
  committed index carries the programmer's guide only. The
  sldworksapi batch corpus ingestion is a v0.14 follow-up. See
  `docs/DEFERRED.md` for the L3 corpus-boundary decision.

**Code:**

- `src/ai_sw_bridge/rag/corpus.py` — normalized document model
- `src/ai_sw_bridge/rag/chunk.py` — paragraph-based chunking with
  table-boundary preservation
- `src/ai_sw_bridge/rag/embed.py` — sentence-transformers
  wrapper + hash-embedder fallback
- `src/ai_sw_bridge/rag/index.py` — sqlite-vec-backed KNN +
  metadata queries
- `src/ai_sw_bridge/cli/apidoc.py` — five subcommands
- `tools/chm_extract.py` — CHM → JSON pipeline
- `tools/build_api_index.py` — JSON → committed index

**Rationale.** LLMs hallucinate SW API surfaces aggressively — wrong
method names, wrong arg counts, deprecated calls. L3 gives the LLM
a retrievable, citation-tagged reference so it can ground its API
choices instead of guessing.

Alternatives rejected:

- *Ship the CHM raw and let the LLM read it.* CHM is a Windows-only
  binary format; not practical.
- *Use an external embedding API.* Requires network egress;
  violates the local-only privacy posture (see
  `docs/privacy_review.md`).
- *Single corpus mixing programmer's guide + API reference.*
  Currently kept separate (programmer's guide only ships); see
  `docs/DEFERRED.md` for the open decision on whether to merge.

---

## L4 — SQLite checkpoints

**What this lane owns.** Per-feature snapshots of build state to a
local SQLite. Each successful feature handler commit appends a row
with feature index, name, type, timestamp, `locals_snapshot`,
spec/pre/post tree hashes, and `com_call_log`. Provides
`ai-sw-history` queries (part / since / diff / rollback) and
encryption-at-rest via Fernet wrap.

**Load-bearing invariants.**

- **Per-feature granularity.** Not per-build, not per-spec — per
  individual feature commit. The rollback story requires this
  granularity (rewind to before the *one* feature that broke).
- **`locals_snapshot` + `com_call_log` are SENSITIVE.** Always
  encrypted columns when `--checkpoint-encrypt` is set. Per W3.1
  privacy hotfix (commit `421724f`), writes to an encrypted DB
  without a key source are refused (raise `KeySourceError` —
  prevents PLAINTEXT-in-encrypted-DB).
- **`_meta` table is plaintext by design.** Algo, fingerprint,
  encrypted-columns list. `ai-sw-checkpoint info` works without the
  key.
- **Tree-hash rollback verification.** `rollback_to(..., doc=)`
  with a live SW doc calls `IModelDoc2.EditRollback`, then
  re-computes the tree hash and compares against the checkpoint's
  `pre_tree_hash`. Mismatch raises `RollbackError`.
- **Key escrow: NONE.** The bridge does not store or back up
  encryption keys. Lost key = lost history.

**Code:**

- `src/ai_sw_bridge/checkpoint/store.py` — SQLite schema +
  insert/commit/mark_failed/record_rollback writes + the
  `_check_writable()` privacy guard
- `src/ai_sw_bridge/checkpoint/snapshot.py` — capture pipeline
- `src/ai_sw_bridge/checkpoint/rollback.py` — software-side rewind +
  optional live-SW `EditRollback`
- `src/ai_sw_bridge/checkpoint/history.py` — `by_part` / `since` /
  `feature_diff` query helpers
- `src/ai_sw_bridge/checkpoint/crypto.py` — Fernet wrap, four key
  sources, atomic rekey
- `src/ai_sw_bridge/checkpoint/gc.py` — retention policy (count,
  age, size cap)
- `src/ai_sw_bridge/cli/history.py` — four subcommands
- `src/ai_sw_bridge/cli/checkpoint.py` — info/genkey/rekey/migrate
- `docs/checkpoint_encryption_design.md` — full design rationale

**Rationale.** Without checkpoints, an LLM that breaks the model on
feature N has no path back to "the state before that feature." Manual
SW Ctrl+Z is fragile across COM-driven builds. L4 makes
try-rollback-retry a first-class verb.

Alternatives rejected:

- *Single end-of-build snapshot.* No granularity for
  rewind-to-before-feature-N.
- *Full-disk snapshot via VSS.* Heavyweight; doesn't capture the
  `locals_snapshot` semantic state.
- *SQLCipher for encryption.* Pure-Python install matters more
  than the marginal security benefit; Fernet at the application
  layer is sufficient for "encrypted at rest" and easier to audit.

---

## Lane M — MCP server

See `docs/mcp_server_design.md` for the full design. Quick summary
here for navigational completeness:

**What this lane owns.** A stdio MCP server (`ai-sw-mcp`) that
exposes 21 tools — 10 observation + 1 build + 5 apidoc + 4
history/checkpoint-info + 1 reconnect — to MCP-capable AI clients
(Claude Desktop, Cursor, Continue.dev). Same tool surface as the
CLIs; different transport.

**Load-bearing invariants.**

- **`@com_tool` discipline.** Every COM-touching tool MUST be
  decorated; the decorator submits the body to the STA-threaded
  `ComExecutor`. Forgetting it is a registration-time failure
  (contract test catches).
- **Auto-flip `is_sw_dead` on dead-dispatch pattern.** Post-hoc
  detection in `@com_tool` flips the flag when a returned payload
  matches the `AttributeError('SldWorks.<member>')` regex; next
  call short-circuits with `sw_reconnect` hint (v0.13.0 A.1 fix,
  commit `6e1778a`).
- **`GetActiveObject` before `Dispatch`** in `sw_com.get_sw_app()`.
  Attaches to the user's foreground SW instead of spawning a ghost
  via auto-launch (v0.13.0 fix, commit `c8627f3`).
- **Write tools are restricted.** Only `sw_build` is exposed;
  `sw_mutate_apply` and key-management ops stay CLI-only.

**Code:** `src/ai_sw_bridge/mcp/` — `server.py`, `runtime.py`,
`tools.py`, plus per-tool registration files (`_tool_observe.py`,
`_tool_build.py`, `_tool_apidoc.py`, `_tool_history.py`,
`_tool_reconnect.py`).

---

## L5 — C# in-process adapter (indefinitely deferred)

Not shipped. Reserved for the day pywin32 stability degrades
meaningfully against a benchmark spec; see `docs/DEFERRED.md` for
the open trigger-telemetry question. The VBA-emit-and-run
alternative (`SolidworksMCP-python/vba_adapter.py`) is the likely
collapse path.

If L5 ever opens, the canonical reference is
`solidworks-api/SolidDna/` from angelsix/solidworks-api (see
`docs/reference_repos.md`).
