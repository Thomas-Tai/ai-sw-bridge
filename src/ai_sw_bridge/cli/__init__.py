"""Command-line entry points for ai-sw-bridge.

Each module here defines a `main()` callable matching pyproject.toml's
[project.scripts]. Convention: every CLI prints exactly one JSON object
to stdout and exits 0 on success / non-zero on failure. This makes the
CLI trivially scriptable from any AI agent harness.
"""
