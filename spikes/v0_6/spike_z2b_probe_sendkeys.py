"""Spike Z2b: probe how to actually invoke SW keystroke-injection.

First run of Z2 hit AttributeError on both `sw.SendKeys` and
`sw.SendKeystrokes`. Possible causes:

  1. Method is on a different interface (ModelView, MainFrame, etc.).
  2. Method is typelib-only -- late-bound Dispatch can't see it; need
     EnsureDispatch or _oleobj_.Invoke(dispid).
  3. The name has different casing or different signature than guessed.

This spike makes no SW build calls. It just enumerates what dispatch
methods exist on the candidate objects, so we can pick the right one
before re-running Z2.

Run from venv-freshtest with SW open.
"""
import pythoncom
import win32com.client


def list_methods_containing(obj, needle, label):
    needle = needle.lower()
    names = []
    try:
        # late-bound: dir() shows what win32com cached after introspection
        for name in dir(obj):
            if needle in name.lower() and not name.startswith("_"):
                names.append(name)
    except Exception as e:
        print(f"  [{label}] dir() ERR: {e!r}")
        return
    if names:
        print(f"  [{label}] dispatch names matching '{needle}': {names}")
    else:
        print(f"  [{label}] no dispatch names matching '{needle}'")


def try_call(obj, attr_name, *args, label=""):
    try:
        attr = getattr(obj, attr_name)
    except AttributeError:
        print(f"  [{label}] {attr_name}: AttributeError on getattr")
        return
    try:
        result = attr(*args)
        print(f"  [{label}] {attr_name}({args!r}) -> {result!r}")
    except Exception as e:
        print(f"  [{label}] {attr_name}({args!r}) ERR: {e!r}")


def main():
    pythoncom.CoInitialize()

    # Late-bound (what Z2 used)
    sw_late = win32com.client.Dispatch("SldWorks.Application")
    print(f"SW revision: {sw_late.RevisionNumber}")
    print()

    # Try EnsureDispatch (loads typelib if available)
    print("=== EnsureDispatch attempt ===")
    try:
        sw_early = win32com.client.gencache.EnsureDispatch("SldWorks.Application")
        print(f"  EnsureDispatch OK: {type(sw_early).__name__}")
    except Exception as e:
        print(f"  EnsureDispatch ERR: {e!r}")
        sw_early = None
    print()

    # Enumerate candidate names on late-bound sw
    print("=== Late-bound sw: names matching 'key' or 'send' ===")
    list_methods_containing(sw_late, "key", "late")
    list_methods_containing(sw_late, "send", "late")
    print()

    if sw_early is not None:
        print("=== EnsureDispatch sw: names matching 'key' or 'send' ===")
        list_methods_containing(sw_early, "key", "early")
        list_methods_containing(sw_early, "send", "early")
        print()

    # Try several casing/spelling variants late-bound
    print("=== Try casing variants on late-bound sw ===")
    for name in [
        "SendKeys",
        "SendKeystrokes",
        "SendKeyStrokes",
        "sendkeystrokes",
        "sendkeys",
    ]:
        try_call(sw_late, name, "{ENTER}", label="late")
    print()

    # Try same variants on early-bound if available
    if sw_early is not None:
        print("=== Try casing variants on EnsureDispatch sw ===")
        for name in [
            "SendKeys",
            "SendKeystrokes",
            "SendKeyStrokes",
        ]:
            try_call(sw_early, name, "{ENTER}", label="early")
        print()

    # Try the methods on the active doc / its ModelView
    doc = sw_late.ActiveDoc
    if doc is None:
        print("No ActiveDoc -- can't probe ModelDoc2 / ModelView for SendKeys methods.")
        print("Open any part first, then re-run this spike.")
        return

    print(f"=== ActiveDoc: {doc.GetTitle if hasattr(doc, 'GetTitle') else '?'} ===")
    list_methods_containing(doc, "key", "doc")
    list_methods_containing(doc, "send", "doc")
    print()

    try:
        mv = doc.ActiveView
        if mv is not None:
            print("=== ActiveDoc.ActiveView ===")
            list_methods_containing(mv, "key", "view")
            list_methods_containing(mv, "send", "view")
    except Exception as e:
        print(f"  ActiveView access ERR: {e!r}")


if __name__ == "__main__":
    main()
