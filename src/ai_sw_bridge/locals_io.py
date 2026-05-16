"""
Read/write locals.txt-style files used by SOLIDWORKS Equation Manager
(Tools > Equations > Link to file).

Expected format (each line):
    "VARNAME"              = expression
    "DERIVED"              = "OTHER_VAR" + 3
    "LITERAL"              = 25.0

The RHS can be a literal, another quoted variable reference, or any
SW-equation expression. Whitespace between name, '=', and value is for
human alignment only; SW ignores it. Comment lines (`#`, `//`) are
preserved but ignored by the parser.

Design rules:

- All edits go through this module. No direct text fiddling.
- A change preserves every byte of the file *except* the RHS of the one
  variable being changed. Trailing whitespace, blank lines, comments,
  alignment - untouched.
- Atomic write: snapshot -> mutate -> os.replace. The snapshot string is
  what we pass to the proposal store for rollback.
- Exclusive lock during mutation: if the user has the file open in an
  editor, we fail fast with a clear error rather than racing.
"""

from __future__ import annotations

import msvcrt
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path


# Matches:  optional whitespace, "NAME" (no embedded quotes), whitespace, =, the rest.
# Capture groups: 1=indent, 2=name, 3=between-name-and-eq, 4=expression
LOCAL_LINE_RE = re.compile(r'^(\s*)"([^"]+)"(\s*=\s*)(.*)$')


@dataclass(frozen=True)
class LocalEntry:
    """One parsed line. line_index is 0-based file line."""

    line_index: int
    name: str
    expression: str  # RHS, stripped of trailing CR/LF


def parse(text: str) -> list[LocalEntry]:
    """Yield one entry per matching line. Non-matching lines (blank,
    comments, future header lines) are silently skipped; we only care
    about variable definitions."""
    entries: list[LocalEntry] = []
    for i, raw in enumerate(text.splitlines()):
        m = LOCAL_LINE_RE.match(raw)
        if not m:
            continue
        entries.append(
            LocalEntry(
                line_index=i,
                name=m.group(2),
                expression=m.group(4).rstrip(),
            )
        )
    return entries


def find_entry(entries: list[LocalEntry], name: str) -> LocalEntry | None:
    for e in entries:
        if e.name == name:
            return e
    return None


def replace_rhs(text: str, line_index: int, new_expression: str) -> str:
    """
    Replace the RHS of the variable at `line_index`. Preserves the
    original line terminator (CRLF or LF) and everything before '='.

    Raises ValueError if the target line doesn't match LOCAL_LINE_RE
    (e.g. the file was edited between parse and replace).
    """
    if "\r\n" in text:
        term = "\r\n"
    elif "\n" in text:
        term = "\n"
    else:
        term = os.linesep

    lines = text.split(term)
    if line_index >= len(lines):
        raise ValueError(f"line_index {line_index} out of range ({len(lines)} lines)")

    target = lines[line_index]
    m = LOCAL_LINE_RE.match(target)
    if not m:
        raise ValueError(
            f"line {line_index} no longer matches local-var pattern: {target!r}"
        )

    indent, name, between, _old_rhs = m.group(1), m.group(2), m.group(3), m.group(4)
    lines[line_index] = f'{indent}"{name}"{between}{new_expression}'
    return term.join(lines)


class ExclusiveLock:
    """
    Windows-only exclusive lock via msvcrt.locking. Holds the lock for
    the duration of the `with` block. Fails fast if another process
    (e.g. the user's editor) has the file open with write access.

    msvcrt.locking can lock at most 2GB; we lock the first 1MB which is
    plenty for any sane locals file.
    """

    def __init__(self, path: Path):
        self.path = path
        self._fd: int | None = None

    def __enter__(self) -> "ExclusiveLock":
        # Open in r+b so we can lock without truncating. Cloud-sync tools
        # (OneDrive, Dropbox) can transiently hold exclusive handles for
        # a few hundred ms after an atomic replace; retry with short
        # backoff before failing.
        last_exc: Exception | None = None
        last_phase = "init"
        for attempt in range(10):
            try:
                fd = os.open(str(self.path), os.O_RDWR | os.O_BINARY)
            except OSError as exc:
                last_exc = exc
                last_phase = f"os.open[{attempt}]"
                time.sleep(0.1 * (attempt + 1))
                continue
            try:
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1024 * 1024)
            except OSError as exc:
                os.close(fd)
                last_exc = exc
                last_phase = f"msvcrt.locking[{attempt}]"
                time.sleep(0.1 * (attempt + 1))
                continue
            self._fd = fd
            return self

        raise OSError(
            f"could not acquire lock after retries (phase={last_phase}, path={self.path}): {last_exc!r}"
        )

    def __exit__(self, *exc_info: object) -> None:
        if self._fd is not None:
            # msvcrt.locking unlocks at *current* file position. If
            # read_text moved the position forward, unlocking from there
            # targets a region that was never locked and Windows returns
            # EACCES. Seek back to start before unlocking.
            try:
                os.lseek(self._fd, 0, os.SEEK_SET)
                msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1024 * 1024)
            except OSError:
                # Closing the fd will drop the lock anyway; the unlock
                # call is hygienic, not load-bearing.
                pass
            finally:
                os.close(self._fd)
                self._fd = None

    def read_text(self, encoding: str = "utf-8") -> str:
        """Read the file's full contents through the held lock fd.

        Use this instead of `path.read_text(...)` while inside the lock,
        because Windows shared-access denies a separate open call once
        msvcrt.locking has the region locked.
        """
        if self._fd is None:
            raise RuntimeError("ExclusiveLock not entered")
        os.lseek(self._fd, 0, os.SEEK_SET)
        data = b""
        while True:
            chunk = os.read(self._fd, 65536)
            if not chunk:
                break
            data += chunk
        return data.decode(encoding)


def atomic_write(path: Path, text: str) -> None:
    """
    Write `text` to `path` atomically: write to a sibling .tmp then
    os.replace into place. SW's equation-manager file watcher (when
    LinkToFile=True) will pick up the change on the next solve.

    Encoding: UTF-8 with no BOM. SW reads locals files as ANSI on most
    builds but UTF-8 is a safe superset for ASCII variable names.
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="")
    os.replace(tmp, path)
