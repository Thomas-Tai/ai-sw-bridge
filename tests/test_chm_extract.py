"""Tests for tools/chm_extract.py (progguide extension, spec.md §4.2).

Covers the new programmer's-guide extractor:

* Single-topic extraction from a synthetic HTML blob.
* Corpus walk over a fake decompiled tree (multiple topics, categories,
  image-dir exclusion, stable sort order).
* CLI smoke: ``progguide`` subcommand writes a JSON corpus file and
  prints a summary to stdout.
* CLI error path: missing root prints a decompile hint and exits 2.

The API-reference extractors (method / enum / batch) are exercised by
the existing Spike-0 scripts and are out of scope for this task.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tools.chm_extract import (
    _progguide_code_blocks,
    _progguide_keywords,
    _progguide_title,
    extract_progguide_corpus,
    extract_progguide_topic,
)


REPO_ROOT = Path(__file__).resolve().parent.parent


# -- helpers ----------------------------------------------------------------


_FAKE_TOPIC_TEMPLATE = """<!doctype HTML public "-//W3C//DTD HTML 4.0 Frameset//EN">
<html>
<head>
<title>{title}</title>
<meta name=MS-HKWD content="{keywords}">
</head>
<body>
<h1><span style="font-weight: normal; font-size: 7.5pt;">SOLIDWORKS API Help</span></h1>
<h1>{title}</h1>
<p>{prose}</p>
{code_block}
</body>
</html>
"""


def _write_topic(
    root: Path,
    category: str,
    filename: str,
    *,
    title: str,
    prose: str = "Some narrative prose.",
    keywords: str = "foo, bar",
    code_block: str = "",
) -> Path:
    cat_dir = root / category
    cat_dir.mkdir(parents=True, exist_ok=True)
    p = cat_dir / filename
    p.write_text(
        _FAKE_TOPIC_TEMPLATE.format(
            title=title,
            prose=prose,
            keywords=keywords,
            code_block=code_block,
        ),
        encoding="utf-8",
    )
    return p


# -- single-topic extractor -------------------------------------------------


def test_extract_progguide_topic_basic_fields(tmp_path: Path) -> None:
    html = _write_topic(
        tmp_path,
        "Overview",
        "Sample_Topic.htm",
        title="A Sample Topic",
        prose="This is a paragraph about an API concept.",
        keywords="Bodies, Interfaces",
    )
    topic = extract_progguide_topic(html)

    assert topic is not None
    assert topic["title"] == "A Sample Topic"
    assert topic["category"] == "Overview"
    assert "Bodies" in topic["keywords"]
    assert "Interfaces" in topic["keywords"]
    assert "API concept" in topic["text"]
    # Banner + title h1s must NOT leak into prose.
    assert "SOLIDWORKS API Help" not in topic["text"]
    assert "A Sample Topic" not in topic["text"]


def test_extract_progguide_topic_captures_pre_and_apicode(
    tmp_path: Path,
) -> None:
    html = _write_topic(
        tmp_path,
        "Macro_Features",
        "With_Code.htm",
        title="Code Sample",
        prose="Explanation text.",
        code_block=(
            '<pre>Dim swApp As Object\nSet swApp = CreateObject("SldWorks.Application")</pre>\n'
            '<p class=apiCode>"MY_CONST" = 42</p>'
        ),
    )
    topic = extract_progguide_topic(html)

    assert topic is not None
    assert len(topic["code_examples"]) == 2
    assert "CreateObject" in topic["code_examples"][0]
    assert "MY_CONST" in topic["code_examples"][1]
    # Code must NOT leak into the prose paragraph.
    assert "CreateObject" not in topic["text"]
    assert "MY_CONST" not in topic["text"]


def test_extract_progguide_topic_skips_unreadable(tmp_path: Path) -> None:
    missing = tmp_path / "nope.htm"
    assert extract_progguide_topic(missing) is None


# -- helpers (unit-level) ---------------------------------------------------


def test_progguide_title_picks_real_h1_over_banner() -> None:
    html = "<h1>SOLIDWORKS API Help</h1>" "<h1>The Real Topic Title</h1>" "<p>body</p>"
    assert _progguide_title(html) == "The Real Topic Title"


def test_progguide_title_falls_back_to_meta_title() -> None:
    html = (
        "<html><head><title>Fallback Title</title></head><body><p>x</p></body></html>"
    )
    assert _progguide_title(html) == "Fallback Title"


def test_progguide_keywords_splits_comma_separated() -> None:
    html = (
        '<meta name=MS-HKWD content="Bodies (see also IBody2 Interface),body folders">\n'
        '<meta name=MS-HKWD content="Attributes">'
    )
    kws = _progguide_keywords(html)
    assert "Bodies (see also IBody2 Interface)" in kws
    assert "body folders" in kws
    assert "Attributes" in kws


def test_progguide_code_blocks_prefers_pre_over_apicode() -> None:
    html = "<pre>multi\nline</pre>" "<p class=apiCode>single</p>"
    blocks = _progguide_code_blocks(html)
    assert blocks == ["multi line", "single"]


# -- corpus extractor -------------------------------------------------------


def test_extract_progguide_corpus_walks_tree(tmp_path: Path) -> None:
    _write_topic(tmp_path, "Overview", "A.htm", title="Alpha", prose="p1")
    _write_topic(tmp_path, "Overview", "B.htm", title="Beta", prose="p2")
    _write_topic(tmp_path, "GettingStarted", "C.htm", title="Gamma", prose="p3")
    # image/ directory must be skipped.
    img = tmp_path / "image"
    img.mkdir()
    (img / "noise.htm").write_text("<h1>noise</h1><p>not a topic</p>", encoding="utf-8")

    corpus = extract_progguide_corpus(tmp_path)

    assert corpus["corpus"] == "sldworksapiprogguide"
    assert corpus["topics_count"] == 3
    # Stable sort: category asc, then title asc.
    cats = [t["category"] for t in corpus["topics"]]
    assert cats == sorted(cats)
    titles_by_cat = {
        t["category"]: [
            x["title"] for x in corpus["topics"] if x["category"] == t["category"]
        ]
        for t in corpus["topics"]
    }
    assert titles_by_cat["Overview"] == ["Alpha", "Beta"]


def test_extract_progguide_corpus_deterministic(tmp_path: Path) -> None:
    """Two runs over the same tree produce byte-identical JSON."""
    _write_topic(tmp_path, "Overview", "X.htm", title="X", prose="p1")
    _write_topic(tmp_path, "Overview", "Y.htm", title="Y", prose="p2")

    a = json.dumps(extract_progguide_corpus(tmp_path), sort_keys=True)
    b = json.dumps(extract_progguide_corpus(tmp_path), sort_keys=True)
    assert a == b


# -- CLI --------------------------------------------------------------------


def test_progguide_cli_writes_corpus(tmp_path: Path) -> None:
    root = tmp_path / "decompiled"
    _write_topic(root, "Overview", "A.htm", title="Alpha", prose="p1")
    out = tmp_path / "out.json"

    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "tools" / "chm_extract.py"),
            "progguide",
            str(out),
            "--progguide-root",
            str(root),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["topics_found"] == 1
    assert payload["written"] == str(out)

    corpus = json.loads(out.read_text(encoding="utf-8"))
    assert corpus["topics_count"] == 1
    assert corpus["topics"][0]["title"] == "Alpha"


def test_progguide_cli_missing_root_prints_decompile_hint(
    tmp_path: Path,
) -> None:
    out = tmp_path / "out.json"
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "tools" / "chm_extract.py"),
            "progguide",
            str(out),
            "--progguide-root",
            str(tmp_path / "does-not-exist"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert "error" in payload
    assert "hh.exe" in payload["hint"]
    assert not out.exists()
