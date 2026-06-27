"""Guard: SW zero-arg COM methods must be read through ``sw_com.resolve()``.

A direct ``obj.RevisionNumber`` / ``doc.GetTitle`` read returns the *value*
under late binding but a *bound method* under early binding (any box with a
cached makepy / gen_py typelib for SOLIDWORKS). That asymmetry silently broke
``ai-sw-probe`` (printed a bound-method repr), the ``SW_VERSION_VERIFIED``
gate (parsed a method object -> skipped the check), and
``spec._version_resolver.read_running_major`` (returned ``None`` -> COM-arg
dispatch degraded to the newest signature, a back-compat hazard on SW 2021).

``resolve(obj, "Name")`` is binding-agnostic (it invokes a genuine bound
method, keyed on ``inspect.ismethod``). This AST scan fails CI if a direct
read of one of these names sneaks back in. The check is deterministic (it
parses source, not runtime state).

Note: ``resolve(doc, "GetTitle")`` passes the method name as a *string*, so it
is an ``ast.Constant``, not an ``ast.Attribute`` -- the sanctioned form is
never flagged. Only direct attribute access (``doc.GetTitle`` /
``doc.GetTitle()``) trips the guard.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "ai_sw_bridge"

# COM members that LOOK like properties but are zero-arg *methods* under early
# binding. Reading them off a COM handle directly is the trap. Extend this set
# as new property-shaped zero-arg COM reads are introduced.
FORBIDDEN_ATTRS = frozenset(
    {
        "RevisionNumber",
        "GetTitle",
        "GetType",
        "GetPathName",
    }
)

# ``resolve()`` itself lives here; the module is the sanctioned reader and is
# exempt from the caller-side rule.
EXEMPT_FILES = frozenset({"sw_com.py"})


def _violations() -> list[tuple[str, int, str]]:
    found: list[tuple[str, int, str]] = []
    for path in sorted(SRC.rglob("*.py")):
        if path.name in EXEMPT_FILES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_ATTRS:
                rel = path.relative_to(SRC).as_posix()
                found.append((rel, node.lineno, node.attr))
    return found


def test_no_direct_com_property_reads() -> None:
    violations = _violations()
    assert not violations, (
        "Direct SW COM method reads found -- route each through "
        'sw_com.resolve(obj, "Name") so it works under both COM bindings:\n'
        + "\n".join(f"  {rel}:{ln}  .{attr}" for rel, ln, attr in violations)
    )
