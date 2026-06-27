# Documentation index

Navigation for `docs/`. Large generated references (`sw_api_full.*`, `api_reference.*`,
`ribbon_api_progress_relation_audit.md`) are **gitignored** build outputs — regenerate
locally. Internal maintainer-only material (release runbooks, AI-agent orchestration
prompts, session reconstructions, R&D research/spike reports) is kept out of the repository.

## Getting started
- [ONBOARDING.md](ONBOARDING.md) — first-run setup for a new operator/contributor.
- [AGENTS.md](AGENTS.md) — how an AI agent drives the bridge (the contract agents read).
- [CAPABILITIES.md](CAPABILITIES.md) — what the bridge can build/observe today.
- [spec_reference.md](spec_reference.md) — per-primitive JSON spec schema reference (incl. sketch-axis reference).
- [known_limitations.md](known_limitations.md) — spec-author sharp edges (read before your first spec).
- [known_gotchas.md](known_gotchas.md) — COM/pywin32 marshalling gotchas (contributors).

## Public surface & stability
- [PUBLIC_API.md](PUBLIC_API.md) — the supported-surface contract: CLI / MCP / Python facade, **per-command stability tiers**, the **deprecation policy**, and the SemVer promise.
- [tools_reference.md](tools_reference.md) — the `tools/` helper scripts (incl. the SW-version compatibility matrix runner).

## Architecture & design
- [architecture.md](architecture.md) — system structure.
- [CLASS_RELATION_MAP.md](CLASS_RELATION_MAP.md) — the client/facades/registry/verify/COM relation map (mermaid + layer hierarchy).
- [decisions.md](decisions.md) — the running architecture decision log (ADRs).
- [mcp_server_design.md](mcp_server_design.md) — the MCP server contract.
- [checkpoint_encryption_design.md](checkpoint_encryption_design.md) — at-rest encryption design.
- [supervised_session_spec.md](supervised_session_spec.md) — crash-recovery envelope (spec + test specification).
- [com_failure_modes.md](com_failure_modes.md) — the COM incident registry (verify-the-postcondition).
- [why_no_addim2.md](why_no_addim2.md) — why `--no-dim` exists (the `AddDimension2` popup wall).
- [verify_substrate.md](verify_substrate.md) — the verify-the-EFFECT sign convention (cited by `features/verify.py`).
- [DEFERRED.md](DEFERRED.md) — the forensic record of every OOP/kernel wall.

## Security & compliance
- [SECURITY.md](SECURITY.md) — privacy posture (data inventory, sensitivity tiers, egress paths) + supply-chain security (pinned-commit policy, CVE response, license audit).

## Reference
- [ROADMAP.md](ROADMAP.md) — direction.
