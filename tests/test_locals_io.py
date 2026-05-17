"""Tests for ai_sw_bridge.locals_io.

ExclusiveLock is Windows-specific and hard to fixture without races; skipped.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_sw_bridge.locals_io import (
    LocalEntry,
    atomic_write,
    parse,
    replace_rhs,
)


# -----------------------------------------------------------------------------
# parse()
# -----------------------------------------------------------------------------


def test_parse_extracts_name_and_expression() -> None:
    text = '"PART_DIAMETER"          = 25.0\n' '"PART_LENGTH"            = 80.0\n'
    entries = parse(text)
    assert entries == [
        LocalEntry(line_index=0, name="PART_DIAMETER", expression="25.0"),
        LocalEntry(line_index=1, name="PART_LENGTH", expression="80.0"),
    ]


def test_parse_skips_blank_and_comment_lines() -> None:
    text = (
        "# top comment\n" "\n" '"A" = 1\n' "// other comment style\n" '"B" = "A" + 3\n'
    )
    entries = parse(text)
    names = [e.name for e in entries]
    assert names == ["A", "B"]
    # B is at original file index 4 (0-based)
    b = entries[1]
    assert b.line_index == 4
    assert b.expression == '"A" + 3'


def test_parse_strips_trailing_whitespace_from_expression() -> None:
    text = '"X" = 5.0   \n'
    [e] = parse(text)
    assert e.expression == "5.0"


# -----------------------------------------------------------------------------
# replace_rhs()
# -----------------------------------------------------------------------------


def test_replace_rhs_round_trip() -> None:
    text = '"A" = 1.0\n"B" = 2.0\n'
    new_text = replace_rhs(text, line_index=1, new_expression="99.5")
    entries = parse(new_text)
    b = next(e for e in entries if e.name == "B")
    assert b.expression == "99.5"


def test_replace_rhs_preserves_crlf() -> None:
    text = '"A" = 1.0\r\n"B" = 2.0\r\n'
    out = replace_rhs(text, line_index=0, new_expression="9.9")
    # CRLF terminators must survive
    assert "\r\n" in out
    # And no stray bare \n should have appeared
    assert out.count("\n") == out.count("\r\n")
    assert out.startswith('"A" = 9.9\r\n')


def test_replace_rhs_preserves_lf() -> None:
    text = '"A" = 1.0\n"B" = 2.0\n'
    out = replace_rhs(text, line_index=0, new_expression="9.9")
    assert "\r\n" not in out
    assert out == '"A" = 9.9\n"B" = 2.0\n'


def test_replace_rhs_preserves_whitespace_alignment_and_neighbours() -> None:
    text = (
        "# header comment\n"
        "\n"
        '   "X"                = 10.0    # trailing comment-ish text\n'
        '   "Y"                = 20.0\n'
        "\n"
    )
    out = replace_rhs(text, line_index=2, new_expression="42.0")
    out_lines = out.split("\n")
    # Header / blank / Y / trailing-blank all intact
    assert out_lines[0] == "# header comment"
    assert out_lines[1] == ""
    assert out_lines[3] == '   "Y"                = 20.0'
    assert out_lines[4] == ""
    # X line: indent, name, alignment whitespace preserved exactly; only RHS replaced.
    assert out_lines[2] == '   "X"                = 42.0'


def test_replace_rhs_raises_on_non_variable_line() -> None:
    text = "# header\n\n"
    with pytest.raises(ValueError):
        replace_rhs(text, line_index=0, new_expression="1.0")


def test_replace_rhs_raises_on_out_of_range_index() -> None:
    text = '"A" = 1\n'
    with pytest.raises(ValueError):
        replace_rhs(text, line_index=99, new_expression="1.0")


# -----------------------------------------------------------------------------
# atomic_write()
# -----------------------------------------------------------------------------


def test_atomic_write_creates_file_with_exact_content(tmp_path: Path) -> None:
    target = tmp_path / "locals.txt"
    text = '"A" = 1.0\n"B" = 2.0\n'
    atomic_write(target, text)
    assert target.read_text(encoding="utf-8") == text


def test_atomic_write_overwrites_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "locals.txt"
    target.write_text("OLD", encoding="utf-8")
    atomic_write(target, "NEW")
    assert target.read_text(encoding="utf-8") == "NEW"


def test_atomic_write_cleans_up_tmp_sibling(tmp_path: Path) -> None:
    target = tmp_path / "locals.txt"
    atomic_write(target, "hello")
    # After a successful atomic_write the .tmp sibling must be gone
    # (os.replace renames it on top of target).
    tmp_sibling = target.with_suffix(target.suffix + ".tmp")
    assert not tmp_sibling.exists()
    assert target.exists()


def test_atomic_write_preserves_line_terminators_literally(tmp_path: Path) -> None:
    target = tmp_path / "crlf.txt"
    text = '"A" = 1\r\n"B" = 2\r\n'
    atomic_write(target, text)
    # newline="" passed to write_text => bytes round-trip exactly.
    raw = target.read_bytes()
    assert b"\r\n" in raw
    assert raw == text.encode("utf-8")
