# Documentation index

Navigation for `docs/`. Archived single-epoch process artifacts (W*-era worker prompts, W0
directives, handoffs) live under [`history/`](history/) and are kept for provenance only.
Large generated references (`sw_api_full.*`, `api_reference.*`, `ribbon_api_progress_relation_audit.md`,
`central_idea_vs_implementation_audit.md`) are **gitignored** build outputs — regenerate locally.

## Getting started
- [ONBOARDING.md](ONBOARDING.md) — first-run setup for a new operator/contributor.
- [AGENTS.md](AGENTS.md) — how an AI agent drives the bridge (the contract agents read).
- [CAPABILITIES.md](CAPABILITIES.md) — what the bridge can build/observe today.
- [spec_reference.md](spec_reference.md) — per-primitive JSON spec schema reference.
- [known_limitations.md](known_limitations.md) — spec-author sharp edges (read before your first spec).
- [known_gotchas.md](known_gotchas.md) — COM/pywin32 marshalling gotchas (contributors).

## Public surface & stability
- [cli_stability.md](cli_stability.md) — CLI stability tiers (stable/experimental/deprecated); CI-enforced.
- [deprecation_policy.md](deprecation_policy.md) — the back-compat / deprecation commitment.
- [tools_reference.md](tools_reference.md) — the `tools/` helper scripts.

## Architecture & design
- [architecture.md](architecture.md) · [ai_driven_architecture_review.md](ai_driven_architecture_review.md) — structure + review.
- [decisions.md](decisions.md) — the running architecture decision log.
- [lane_designs.md](lane_designs.md) — per-lane design notes.
- [mcp_server_design.md](mcp_server_design.md) — the MCP server contract.
- [checkpoint_encryption_design.md](checkpoint_encryption_design.md) — at-rest encryption design.
- [supervised_session_spec.md](supervised_session_spec.md) · [supervised_session_test_spec.md](supervised_session_test_spec.md) — crash-recovery envelope.
- [com_failure_modes.md](com_failure_modes.md) — the COM incident registry (verify-the-postcondition).
- [addins_research.md](addins_research.md) · [why_no_addim2.md](why_no_addim2.md) — add-in vehicle research.
- [w67_verify_substrate.md](w67_verify_substrate.md) — the verify-the-EFFECT sign convention (cited by `features/verify.py`).
- [DEFERRED.md](DEFERRED.md) — the forensic record of every OOP/kernel wall.
- [pending_gates.md](pending_gates.md) — live-seat (PAE) gates still pending vs proven.

## Security & compliance
- [privacy_review.md](privacy_review.md) — data inventory, sensitivity tiers, egress paths.
- [supply_chain_security.md](supply_chain_security.md) — pinned-commit policy, CVE response, license audit.
- [supply_chain_audit.md](supply_chain_audit.md) — the upstream-CVE ledger (appendix to the above).

## Process, releases & history
- [commercial_readiness_audit.md](commercial_readiness_audit.md) — **current** commercial-hardening audit + plan.
- [ROADMAP.md](ROADMAP.md) · [ROLES.md](ROLES.md) — direction + role model.
- [release_engineering.md](release_engineering.md) — the release/CI machinery.
- [sw_version_matrix_runner.md](sw_version_matrix_runner.md) — SW-version compatibility matrix runner.
- [reference_repos.md](reference_repos.md) · [sketch_axes.md](sketch_axes.md) — reference notes.
- Release archaeology: [migration_to_v0.12.md](migration_to_v0.12.md) · [migration_to_v0.14.md](migration_to_v0.14.md) · [v0.14_commercial_hardening_plan.md](v0.14_commercial_hardening_plan.md) · [launch_readiness_checklist.md](launch_readiness_checklist.md) · [audit_s1_cli_mcp_parallelism.md](audit_s1_cli_mcp_parallelism.md).
- [handoff_template.md](handoff_template.md) — session-handoff template (referenced by AGENTS.md).

## Archived (`history/`)
Single-epoch worker prompts (W60–W68), W0 isolation/handoff directives, and superseded planning
docs (the v1.0 RFC + A4 runbook). Provenance only — not current product docs.
