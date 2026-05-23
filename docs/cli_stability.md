# CLI Stability Tiers

Every `ai-sw-bridge` CLI entry point declares an explicit stability tier.
The tier appears in `--help` output as a `[tier]` prefix on the
description line and is tracked in a module-level registry
(``TIER_REGISTRY`` in ``cli/stability.py``) that tests can inspect.

## Tier definitions

| Tier           | Back-compat promise                                                    |
|----------------|------------------------------------------------------------------------|
| **stable**     | No breaking changes to CLI flags, positional args, or JSON output     |
|                | shape without a major version bump (v0.x → v1.0). Minor additions    |
|                | (new optional flags, new output keys) are allowed in any release.     |
| **experimental**| May change or disappear in any release. Output shape and flag names  |
|                | are not guaranteed. Use in production at your own risk.               |
| **deprecated** | Will be removed in the next major release. Emits a stderr warning    |
|                | on every invocation.                                                   |

## How to add a tier

1. Import the decorator and helper:

   ```python
   from .stability import add_tier, cli_stability
   ```

2. Decorate your ``main()`` function:

   ```python
   @cli_stability("stable")
   def main() -> int:
       ...
   ```

3. Call ``add_tire()`` on the ``ArgumentParser`` **after** construction:

   ```python
   parser = argparse.ArgumentParser(...)
   add_tier(parser, "stable")
   ```

4. The test suite enforces that every CLI module in
   ``src/ai_sw_bridge/cli/`` with a ``main()`` function has an explicit
   tier — a new subcommand without one will fail
   ``test_all_cli_modules_registered``.

## Current assignments

| CLI entry point   | Tier           |
|-------------------|----------------|
| ai-sw-build       | stable         |
| ai-sw-observe     | stable         |
| ai-sw-mutate      | stable         |
| ai-sw-probe       | experimental   |
| ai-sw-codegen     | experimental   |
