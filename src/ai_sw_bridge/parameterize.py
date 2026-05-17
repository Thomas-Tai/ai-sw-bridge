"""
Recorded-macro parameterizer (Path C).

Reads a SW-recorded .swp (an OLE Compound Document), extracts the VBA,
and applies two surgical edits driven by a JSON parameterization map:

  1. Injects an equation-link block right after `Set Part = swApp.ActiveDoc`,
     linking the part to a *_locals.txt file. This must run before any
     dimension SystemValue assignments so the variables exist for binding.

  2. Appends `EquationMgr.Add2(-1, "<formula>", True)` calls at the END
     of Sub main(), one per binding. SW evaluates these AFTER the feature
     is created, swapping the literal value for a parametric binding.

Why this design:
  - Never modify recorded VBA in-place; only add. SW-recorded calls are
    ground truth; rewriting them risks breaking signatures we cannot
    reliably re-author from outside.
  - Use the linked-locals approach: the Equation Manager loads the var
    file once, then Add2 creates a parametric binding (same as a user
    typing a row in Tools > Equations).

Why Add2, not Add3:
  - Add2 takes 3 args (index, formula, solveOrder).
  - Add3 takes 4 args (index, formula, suppress, solveOrder) but silently
    fails on some SW builds via late-binding - returns -1, no error.
  - The CodeStack example
    (`document/dimensions/add-equation/Macro.vba`) uses Add2; we follow it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _extract_vba(swp_path: Path) -> str:
    """Pull the recorded module's VBA source out of the binary .swp.

    Uses oletools.olevba to crack the OLE Compound Document. The .swp
    typically contains 2 streams: a ThisLibrary class stub (skip), and
    the user's recorded module (return).
    """
    from oletools.olevba import VBA_Parser

    p = VBA_Parser(str(swp_path))
    if not p.detect_vba_macros():
        raise ValueError(f"no VBA macros found in {swp_path}")
    for _, stream, _, code in p.extract_macros():
        if "ThisLibrary" in stream:
            continue
        return code
    raise ValueError(f"no usable VBA module in {swp_path}")


def _strip_vb_attributes(vba: str) -> str:
    """Remove `Attribute VB_...` lines; they are module metadata, not code.
    Required when pasting into a fresh module in VBE."""
    lines = vba.splitlines()
    return "\n".join(l for l in lines if not l.startswith("Attribute VB_"))


def _build_link_block(locals_path: str) -> str:
    """VBA snippet that links a locals.txt file and reloads. Injected
    after the active-doc grab so subsequent dim sets can reference the
    linked vars."""
    p = locals_path.replace('"', '""')
    return (
        "    ' --- BRIDGE INJECTION: link equation file ---\n"
        "    Dim bridgeEq As Object\n"
        "    Set bridgeEq = Part.GetEquationMgr\n"
        f'    bridgeEq.FilePath = "{p}"\n'
        "    bridgeEq.LinkToFile = True\n"
        "    bridgeEq.AutomaticRebuild = True\n"
        "    Dim bridgeReload As Boolean\n"
        "    bridgeReload = bridgeEq.UpdateValuesFromExternalEquationFile\n"
        "    ' --- END BRIDGE INJECTION ---\n"
    )


def _build_param_bindings(bindings: list[dict[str, str]]) -> str:
    """Each binding has {dim, rhs}. Uses EquationMgr.Add2 (3 args).

    Per the CodeStack `add-equation/Macro.vba` pattern, the LHS is the
    quoted dim name and the RHS is a raw expression string. The RHS may
    be a bare quoted variable ("S1B_X") or any arithmetic expression
    mixing quoted vars and literals ("S1B_X" + 0.5). The user is
    responsible for any quoting inside `rhs`; we paste it verbatim.

    Legacy spec compatibility: if a binding has `var` but no `rhs`, we
    auto-wrap it as `"<var>"` so old specs keep working.
    """
    if not bindings:
        return ""
    out = [
        "",
        "    ' --- BRIDGE INJECTION: bind dims to linked vars via EquationMgr.Add2 ---",
    ]
    out.append("    Dim bridgeAddIdx As Long")
    for b in bindings:
        dim = b["dim"]
        if "rhs" in b:
            rhs = b["rhs"]
        elif "var" in b:
            rhs = f'"{b["var"]}"'
        else:
            raise ValueError(f"binding missing 'rhs' (or legacy 'var'): {b}")
        # Build the VBA string literal for the full formula. Inside an
        # outer VBA string each `"` is doubled, so transform once.
        formula = f'"{dim}" = {rhs}'
        vba_literal = formula.replace('"', '""')
        out.append(f'    bridgeAddIdx = bridgeEq.Add2(-1, "{vba_literal}", True)')
    out.append("    Dim bridgeRebuild As Boolean")
    out.append("    bridgeRebuild = Part.EditRebuild3")
    out.append("    ' --- END BRIDGE INJECTION ---")
    return "\n".join(out) + "\n"


def parameterize(swp_path: Path, spec: dict[str, Any]) -> str:
    """
    Returns the parameterized VBA source as a string.

    spec keys:
      locals_path: absolute path to *_locals.txt to link
      bindings: list of {"dim": "D1@<name>", "rhs": "<raw RHS expression>"}
        - RHS is pasted verbatim into the formula. For a bare variable
          binding, write `"S1B_X"` (quotes included). For an expression,
          write e.g. `"S1B_X" + 0.5` or `"S1B_A" * "S1B_B"`.
        - Legacy: a binding may use `"var": "S1B_X"` (no quotes) instead
          of `"rhs"`; we auto-wrap it as `"S1B_X"`. New specs should use
          `rhs`.

    The returned string is plain .bas content; paste into a SW VBE module
    and run with F5. The user-paste step is necessary because SW's
    RunMacro/RunMacro2 only accept native binary .swp files; plain-text
    .bas is silently rejected.
    """
    raw = _extract_vba(swp_path)
    code = _strip_vb_attributes(raw)

    link = _build_link_block(spec["locals_path"])
    bindings_block = _build_param_bindings(spec.get("bindings", []))

    # Locate `Set Part = swApp.ActiveDoc` and inject the link block AFTER it.
    # SW recordings reliably emit this line near the top.
    lines = code.splitlines()
    out_lines: list[str] = []
    injected_link = False
    for line in lines:
        out_lines.append(line)
        if not injected_link and "Set Part = swApp.ActiveDoc" in line:
            out_lines.append(link.rstrip("\n"))
            injected_link = True

    if not injected_link:
        # Fallback: inject right after `Sub main()`
        for i, line in enumerate(out_lines):
            if line.strip().startswith("Sub main"):
                out_lines.insert(i + 1, link.rstrip("\n"))
                injected_link = True
                break

    # Find the `End Sub` of main() and inject bindings just before it.
    final: list[str] = []
    injected_bindings = False
    for line in out_lines:
        if not injected_bindings and line.strip() == "End Sub":
            final.append(bindings_block.rstrip("\n"))
            injected_bindings = True
        final.append(line)

    return "\n".join(final) + "\n"
