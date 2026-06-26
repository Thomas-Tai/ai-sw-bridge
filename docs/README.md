# Documentation index

Navigation for `docs/`. Large generated references (`sw_api_full.*`, `api_reference.*`,
`ribbon_api_progress_relation_audit.md`) are **gitignored** build outputs — regenerate
locally. Internal maintainer-only material (release runbooks, AI-agent orchestration
prompts, session reconstructions, R&D spike reports) is kept out of the repository.

## Getting started
- [ONBOARDING.md](ONBOARDING.md) — first-run setup for a new operator/contributor.
- [AGENTS.md](AGENTS.md) — how an AI agent drives the bridge (the contract agents read).
- [CAPABILITIES.md](CAPABILITIES.md) — what the bridge can build/observe today.
- [spec_reference.md](spec_reference.md) — per-primitive JSON spec schema reference.
- [known_limitations.md](known_limitations.md) — spec-author sharp edges (read before your first spec).
- [known_gotchas.md](known_gotchas.md) — COM/pywin32 marshalling gotchas (contributors).

## Public surface & stability
- [PUBLIC_API.md](PUBLIC_API.md) — the supported-surface stability contract (CLI / MCP / Python facade) + SemVer promise.
- [cli_stability.md](cli_stability.md) — CLI stability tiers (stable/experimental/deprecated); CI-enforced.
- [deprecation_policy.md](deprecation_policy.md) — the back-compat / deprecation commitment.
- [tools_reference.md](tools_reference.md) — the `tools/` helper scripts.

## Architecture & design
- [architecture.md](architecture.md) — system structure.
- [CLASS_RELATION_MAP.md](CLASS_RELATION_MAP.md) — the client/facades/registry/verify/COM relation map (mermaid + layer hierarchy).
- [decisions.md](decisions.md) — the running architecture decision log (ADRs).
- [lane_designs.md](lane_designs.md) — per-lane design notes.
- [mcp_server_design.md](mcp_server_design.md) — the MCP server contract.
- [checkpoint_encryption_design.md](checkpoint_encryption_design.md) — at-rest encryption design.
- [supervised_session_spec.md](supervised_session_spec.md) · [supervised_session_test_spec.md](supervised_session_test_spec.md) — crash-recovery envelope.
- [com_failure_modes.md](com_failure_modes.md) — the COM incident registry (verify-the-postcondition).
- [addins_research.md](addins_research.md) · [why_no_addim2.md](why_no_addim2.md) — add-in vehicle research.
- [w67_verify_substrate.md](w67_verify_substrate.md) — the verify-the-EFFECT sign convention (cited by `features/verify.py`).
- [DEFERRED.md](DEFERRED.md) — the forensic record of every OOP/kernel wall.

## Security & compliance
- [privacy_review.md](privacy_review.md) — data inventory, sensitivity tiers, egress paths.
- [supply_chain_security.md](supply_chain_security.md) — pinned-commit policy, CVE response, license audit; **Appendix A** is the upstream-port CVE ledger.

## Reference
- [ROADMAP.md](ROADMAP.md) — direction.
- [sw_version_matrix_runner.md](sw_version_matrix_runner.md) — SW-version compatibility matrix runner.
- [sketch_axes.md](sketch_axes.md) — sketch axis reference notes.
