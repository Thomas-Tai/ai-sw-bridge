# Glossary

The load-bearing terms used across the design docs. Each is an architectural
concept you need in order to read the rest of `docs/`. Legacy sprint and phase
names are deliberately **not** here — this is the vocabulary of the product, not
of its development history.

### Feature handler

A per-kind Python function — `create_<kind>(doc, feature, target) -> (ok, error)`
— that builds one CAD feature and then verifies the result actually materialized
(a returned `Feature` object alone is never treated as success). Handlers are
registered in `features.HANDLER_REGISTRY`, keyed by feature `kind`, through
`_register_lane`, which admits a handler **only** once it is seat-proven on a real
SOLIDWORKS instance; unproven or walled kinds are imported for provenance but never
advertised. See [CLASS_RELATION_MAP.md](CLASS_RELATION_MAP.md) §3 and
[verify_substrate.md](verify_substrate.md).

### Lane M

The Model Context Protocol (MCP) server boundary — the transport lane that exposes
the bridge's tools to MCP clients, as distinct from the CLI transport. Because MCP
tool handlers run on async worker threads while the SOLIDWORKS COM API is
single-threaded-apartment (STA), every COM-touching call is marshalled onto one
dedicated worker via `ComExecutor`, enforced by the `@com_tool` decorator. See
[mcp_server_design.md](mcp_server_design.md) and
[com_failure_modes.md](com_failure_modes.md) rows M-01 / M-02.

### Out-of-process

The bridge's core architectural constraint: it drives the SOLIDWORKS COM API from a
**separate Python process** (via pywin32), never as an in-process add-in DLL loaded
inside `SLDWORKS.exe`. This keeps the product `pip`-installable and keeps the agent
out of the CAD process, but it means a class of kernel features that only
materialize in-process cannot be created out-of-process — those are "walled" and
fail closed rather than silently no-op. The default execution path is **Route-A**
(below). See [DEFERRED.md](DEFERRED.md) and [decisions.md](decisions.md) (the
invariant "out-of-process Python, no agent COM access").

### Route-A / B / C / D

The candidate execution paths for driving SOLIDWORKS, in escalating invasiveness.
Only **Route-A** ships.

- **Route-A** — native out-of-process pywin32, late-bound by default with a narrow
  early-bound typed-wrap (`com.earlybind.typed()`) for the OUT-parameter / `Callout`
  marshalling class. The sole shipped path; stays out-of-process and
  `pip`-installable.
- **Route-B** — VBA emit-and-run: emit a `.bas` macro and execute it inside
  SOLIDWORKS' own VBA host. Rejected — it puts agent-authored code in-process.
- **Route-C** — a C# in-process adapter (an `ISwAddin` add-in, or PythonNET) loaded
  into the SW process. Used only to *probe* whether a wall is a COM-marshalling
  artifact or a genuine kernel refusal; rejected as a strategic vehicle and closed
  (decisions.md, 2026-05-30).
- **Route-D** — an OPTIONAL, separately-installed in-process C# add-in. Parked as a
  backlog item — the sanctioned future drain for the commit-time boolean-wall class,
  admissible only behind an explicit invariant carve-out.

See [decisions.md](decisions.md) (the 2026-05-30 and 2026-06-11 entries).

### Seat

A running SOLIDWORKS process the bridge talks to — and one consumed license "seat."
The bridge attaches to an operator's live instance through the running-object table
(ROT) or, under the resilience envelope, spawns and reaps its own. A respawned seat
may be windowless/headless; the envelope reaps orphaned `SLDWORKS.exe` processes so a
leaked one doesn't keep pinning a license. See
[supervised_session_spec.md](supervised_session_spec.md).

### Tier 1 / Tier 2 recovery

The two recovery strategies of the resilience envelope when a seat dies mid-batch.
**Both respawn the seat and replay the proposal list idempotently** — they differ by
*when* the death struck:

- **Tier 1** — death during document open or feature apply. The on-disk file is still
  pristine, so recovery respawns and replays the whole batch onto it.
- **Tier 2** — death during the atomic save. The file may be half-written, so recovery
  restores a pre-save snapshot first, then replays.

See [supervised_session_spec.md](supervised_session_spec.md) and
[CLASS_RELATION_MAP.md](CLASS_RELATION_MAP.md) §4.
