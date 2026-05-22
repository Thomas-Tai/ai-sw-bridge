"""Close the currently active doc in SW without saving."""

from __future__ import annotations

import pythoncom  # noqa: F401
import win32com.client


def main() -> int:
    sw = win32com.client.GetActiveObject("SldWorks.Application")
    doc = sw.ActiveDoc
    if doc is None:
        print("no active doc to close")
        return 0
    title = doc.GetTitle
    sw.CloseDoc(title)
    print(f"closed: {title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
