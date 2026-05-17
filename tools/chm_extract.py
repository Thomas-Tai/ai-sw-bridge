"""
CHM signature/enum extractor for the SOLIDWORKS API help files.

Reads decompiled sldworksapi.chm and swconst.chm output (HTML files
written by `hh.exe -decompile <dst> <src.chm>`) and produces a clean
JSON reference. Two functions:

  extract_method(interface, method, html_root)
      Returns {method, interface, args: [{name, type, doc}, ...],
               return_type, doc, availability}
      Parses the per-method HTML file (named
      `SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.<iface>~<method>.html`).

  extract_enum(enum_name, html_root)
      Returns {enum, values: [{name, value, doc}, ...]}
      Parses the per-enum HTML file (named
      `SolidWorks.Interop.swconst~SolidWorks.Interop.swconst.<enum_name>.html`).

CLI:
  python tools/chm_extract.py method IFeatureManager FeatureCut4
  python tools/chm_extract.py enum swEndConditions_e
  python tools/chm_extract.py batch <input.json> <output.json>

The batch input.json schema:
  {
    "methods":  [["IFeatureManager", "FeatureCut4"], ...],
    "enums":    ["swEndConditions_e", "swUserPreferenceToggle_e", ...]
  }
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# Default locations for decompiled CHM trees
DEFAULT_API_ROOT = (
    Path(__file__).resolve().parent.parent / "spikes" / "phase0" / "_chm_decompiled"
)
DEFAULT_CONST_ROOT = (
    Path(__file__).resolve().parent.parent
    / "spikes"
    / "phase0"
    / "_chm_decompiled_swconst"
)


def _strip_html(s: str) -> str:
    """Strip HTML tags and normalize whitespace. Decodes a few common entities."""
    s = re.sub(r"<[^>]+>", "", s)
    s = (
        s.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
    )
    s = re.sub(r"\s+", " ", s).strip()
    return s


# Regex to extract the C# signature block. The C# section uses a class
# selector `LanguageSpecific id=Syntax_CS` followed by a <pre>...</pre>.
_CS_SECTION_RE = re.compile(
    r"id=Syntax_CS.*?<pre>(.*?)</pre>",
    re.IGNORECASE | re.DOTALL,
)

# Regex to extract one C# arg. Captures *any* type token preceding the
# `<i><a class="parameter" id="<name>" ...>` block. Two type shapes:
#   System.<scalar>   -- e.g. System.bool, System.double
#   <InterfaceName>   -- e.g. Callout, IFeature, Object
# Pattern relies on the `id="<name>"` attribute uniquely tagging each param.
_CS_ARG_RE = re.compile(
    r"(?P<ctype>System\.\w+|[A-Z][\w]+)"
    r'\s*<i><a\s+class="parameter"\s+id="(?P<name>\w+)"',
)


def _build_file_index(root: Path) -> dict[str, Path]:
    """One-pass build of a lowercase-filename -> path map for fast lookup.

    Cached in module state via the closure pattern below.
    """
    index: dict[str, Path] = {}
    for p in root.iterdir():
        if p.is_file():
            index[p.name.lower()] = p
    return index


_FILE_INDEX_CACHE: dict[Path, dict[str, Path]] = {}


def _get_index(root: Path) -> dict[str, Path]:
    if root not in _FILE_INDEX_CACHE:
        _FILE_INDEX_CACHE[root] = _build_file_index(root)
    return _FILE_INDEX_CACHE[root]


def extract_method(
    interface: str, method: str, api_root: Path
) -> dict[str, Any] | None:
    """Find and parse the .html file for `interface.method`.

    Returns None if not found.
    """
    # Decompiled file naming pattern:
    # SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.<iface>~<method>.html
    # Case can vary (SolidWorks vs SOLIDWORKS). Build a lowercase index and look up.
    idx = _get_index(api_root)
    candidates = [
        f"SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.{interface}~{method}.html",
        f"SolidWorks.Interop.sldworks~SOLIDWORKS.Interop.sldworks.{interface}~{method}.html",
        f"SOLIDWORKS.Interop.sldworks~SOLIDWORKS.Interop.sldworks.{interface}~{method}.html",
    ]
    html_path = None
    for c in candidates:
        html_path = idx.get(c.lower())
        if html_path is not None:
            break
    if html_path is None:
        # Fuzzy: suffix match on the lowercased index keys
        needle = f"{interface}~{method}.html".lower()
        for name, p in idx.items():
            if name.endswith(needle):
                html_path = p
                break

    if html_path is None:
        return None

    text = html_path.read_text(encoding="utf-8", errors="replace")

    # Extract C# signature
    cs_match = _CS_SECTION_RE.search(text)
    args: list[dict[str, Any]] = []
    return_type = None
    if cs_match:
        cs_block = cs_match.group(1)
        # First line: return type + method name + opening paren
        # E.g. "Feature FeatureCut4(" -> return_type = "Feature"
        head_match = re.search(r"^\s*(\S+)\s+\w+\s*\(", cs_block.strip().split("\n")[0])
        if head_match:
            return_type = head_match.group(1)
        for am in _CS_ARG_RE.finditer(cs_block):
            args.append(
                {
                    "name": am.group("name"),
                    "type": am.group("ctype").lower(),
                    "doc": None,
                }
            )

    # Extract per-param docs from popup-bubble divs (id="<name>_box")
    # Pattern: <DD class="popupbubble">...doc...</DD>
    for arg in args:
        bubble_re = re.compile(
            r'id="'
            + re.escape(arg["name"])
            + r'_box".*?<DD class="popupbubble">(.*?)</DD>',
            re.IGNORECASE | re.DOTALL,
        )
        m = bubble_re.search(text)
        if m:
            arg["doc"] = _strip_html(m.group(1))

    # Extract Availability
    avail_match = re.search(
        r'id="availabilitySection".*?>(.*?)</div>',
        text,
        re.IGNORECASE | re.DOTALL,
    )
    availability = _strip_html(avail_match.group(1)) if avail_match else None

    # Extract one-line summary (the first text node after the body)
    summary_match = re.search(
        r'<div class="saveHistory".*?</div>\s*(.*?)<h1',
        text,
        re.IGNORECASE | re.DOTALL,
    )
    summary = _strip_html(summary_match.group(1)) if summary_match else None

    return {
        "interface": interface,
        "method": method,
        "summary": summary,
        "return_type": return_type,
        "args": args,
        "args_count": len(args),
        "availability": availability,
        "source": html_path.name,
    }


# Enum extraction
def extract_enum(enum_name: str, const_root: Path) -> dict[str, Any] | None:
    """Find and parse the enum HTML file in the swconst decompiled tree."""
    idx = _get_index(const_root)
    candidates = [
        f"SolidWorks.Interop.swconst~SolidWorks.Interop.swconst.{enum_name}.html",
        f"SolidWorks.Interop.swconst~SOLIDWORKS.Interop.swconst.{enum_name}.html",
        f"SOLIDWORKS.Interop.swconst~SOLIDWORKS.Interop.swconst.{enum_name}.html",
    ]
    html_path = None
    for c in candidates:
        html_path = idx.get(c.lower())
        if html_path is not None:
            break
    if html_path is None:
        needle = f"{enum_name}.html".lower()
        for name, p in idx.items():
            if name.endswith(needle):
                html_path = p
                break

    if html_path is None:
        return None

    text = html_path.read_text(encoding="utf-8", errors="replace")

    # Enum members are listed in a table. Pattern in CHM is:
    # <tr><td>memberName</td><td>=</td><td>value</td><td>doc</td></tr>
    # Or in another style: <pre>enum {
    #   memberName = N,   // doc
    # }</pre>
    # Try both patterns.

    values: list[dict[str, Any]] = []

    # Primary pattern (SW CHM "FilteredItemListTable"):
    #   <TD CLASS=MemberNameCell><strong>NAME</strong></TD>
    #   <TD CLASS="DescriptionCell">VALUE</TD>
    # or
    #   <TD CLASS="DescriptionCell">VALUE = doc text</TD>
    table_re = re.compile(
        r"<TD CLASS=MemberNameCell>\s*<strong>(?P<name>\w+)</strong>\s*</TD>\s*"
        r'<TD CLASS="DescriptionCell">\s*(?P<rest>[^<]+?)\s*</TD>',
        re.IGNORECASE,
    )
    for mm in table_re.finditer(text):
        rest = mm.group("rest").replace("&nbsp;", " ").strip()
        # `rest` may be just "0" or "4 = doc"
        vm = re.match(r"(-?\d+)\s*(?:=\s*(.*))?", rest)
        if vm:
            doc = vm.group(2).strip() if vm.group(2) else None
            values.append(
                {"name": mm.group("name"), "value": int(vm.group(1)), "doc": doc}
            )

    # Fallback: VB declaration block
    if not values:
        vb_re = re.compile(
            r"<pre>.*?Public Enum\s+\w+(.*?)End Enum",
            re.IGNORECASE | re.DOTALL,
        )
        vbm = vb_re.search(text)
        if vbm:
            body = vbm.group(1)
            for ln in body.split("\n"):
                ln_clean = _strip_html(ln)
                mm = re.match(r"(\w+)\s*=\s*(-?\d+)", ln_clean)
                if mm:
                    values.append(
                        {"name": mm.group(1), "value": int(mm.group(2)), "doc": None}
                    )

    # Deduplicate (sometimes the regex catches multiple presentations)
    seen = set()
    dedup = []
    for v in values:
        if v["name"] not in seen:
            seen.add(v["name"])
            dedup.append(v)

    summary_match = re.search(
        r'<div class="saveHistory".*?</div>\s*(.*?)<h1',
        text,
        re.IGNORECASE | re.DOTALL,
    )
    summary = _strip_html(summary_match.group(1)) if summary_match else None

    return {
        "enum": enum_name,
        "summary": summary,
        "values": dedup,
        "values_count": len(dedup),
        "source": html_path.name,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    pm = sub.add_parser("method")
    pm.add_argument("interface")
    pm.add_argument("method")
    pm.add_argument("--api-root", default=str(DEFAULT_API_ROOT))

    pe = sub.add_parser("enum")
    pe.add_argument("enum_name")
    pe.add_argument("--const-root", default=str(DEFAULT_CONST_ROOT))

    pb = sub.add_parser("batch")
    pb.add_argument("input_json")
    pb.add_argument("output_json")
    pb.add_argument("--api-root", default=str(DEFAULT_API_ROOT))
    pb.add_argument("--const-root", default=str(DEFAULT_CONST_ROOT))

    args = parser.parse_args()

    if args.cmd == "method":
        result = extract_method(args.interface, args.method, Path(args.api_root))
        if result is None:
            print(
                json.dumps(
                    {"error": f"not found: {args.interface}.{args.method}"}, indent=2
                )
            )
            return 1
        print(json.dumps(result, indent=2))
        return 0

    if args.cmd == "enum":
        result = extract_enum(args.enum_name, Path(args.const_root))
        if result is None:
            print(json.dumps({"error": f"not found: {args.enum_name}"}, indent=2))
            return 1
        print(json.dumps(result, indent=2))
        return 0

    if args.cmd == "batch":
        with open(args.input_json, encoding="utf-8") as f:
            spec = json.load(f)

        out: dict[str, Any] = {"methods": {}, "enums": {}, "missing": []}
        for iface, method in spec.get("methods", []):
            res = extract_method(iface, method, Path(args.api_root))
            if res is None:
                out["missing"].append(f"method:{iface}.{method}")
            else:
                out["methods"][f"{iface}.{method}"] = res
        for ename in spec.get("enums", []):
            res = extract_enum(ename, Path(args.const_root))
            if res is None:
                out["missing"].append(f"enum:{ename}")
            else:
                out["enums"][ename] = res

        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, ensure_ascii=False)
        print(
            json.dumps(
                {
                    "methods_found": len(out["methods"]),
                    "enums_found": len(out["enums"]),
                    "missing_count": len(out["missing"]),
                    "missing": out["missing"],
                    "written": args.output_json,
                },
                indent=2,
            )
        )
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
