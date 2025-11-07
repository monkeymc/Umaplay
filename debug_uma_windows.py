# list_windows.py
# Enumerate ALL top-level windows using Win32 API. Shows hwnd, PID, process name,
# visibility/minimized, class name, and full window title. Supports regex filtering.

import argparse
import re
import sys
from typing import List, Dict

import psutil
import win32con
import win32gui
import win32process

# Make DPI-aware so coordinates/titles aren’t scaled/weird on HiDPI
try:
    import ctypes
    ctypes.windll.user32.SetProcessDPIAware()
except Exception:
    pass


def get_proc_name(pid: int) -> str:
    try:
        return psutil.Process(pid).name()
    except Exception:
        return "?"


def is_minimized(hwnd: int) -> bool:
    try:
        return bool(win32gui.IsIconic(hwnd))
    except Exception:
        return False


def enum_windows(include_invisible: bool, pattern: str | None) -> List[Dict]:
    rx = re.compile(pattern, re.IGNORECASE) if pattern else None
    out: List[Dict] = []

    def _cb(hwnd, _):
        try:
            title = win32gui.GetWindowText(hwnd)
        except Exception:
            title = ""
        if not include_invisible and not win32gui.IsWindowVisible(hwnd):
            return True  # continue
        if not title:
            return True  # skip empty titles to reduce noise

        if rx and not rx.search(title):
            return True

        try:
            cls = win32gui.GetClassName(hwnd)
        except Exception:
            cls = "?"

        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
        except Exception:
            pid = 0

        out.append(
            dict(
                hwnd=hwnd,
                hwnd_hex=f"0x{hwnd:08X}",
                pid=pid,
                proc=get_proc_name(pid),
                visible=bool(win32gui.IsWindowVisible(hwnd)),
                minimized=is_minimized(hwnd),
                cls=cls,
                title=title,
            )
        )
        return True

    win32gui.EnumWindows(_cb, None)
    # Sort visible first, then by process name, then by title
    out.sort(key=lambda d: (not d["visible"], d["proc"].lower(), d["title"].lower()))
    return out


def main():
    ap = argparse.ArgumentParser(description="List top-level Windows window titles.")
    ap.add_argument("--filter", type=str, default=None, help="Regex filter (case-insensitive).")
    ap.add_argument("--all", action="store_true", help="Include hidden/minimized windows.")
    args = ap.parse_args()

    rows = enum_windows(include_invisible=args.all, pattern=args.filter)
    if not rows:
        msg = "No windows found"
        if args.filter:
            msg += f" matching regex: {args.filter!r}"
        print(msg + ". Try --all or a looser --filter (e.g., 'uma|derby|steam|unity|cygames').")
        sys.exit(2)

    print("=" * 120)
    print(f"Found {len(rows)} windows" + (f" (filter={args.filter!r})" if args.filter else "") + ":")
    print("=" * 120)
    for i, r in enumerate(rows, 1):
        print(
            f"[{i:03d}] hwnd={r['hwnd_hex']} pid={r['pid']:>6} {r['proc']:<25} "
            f"vis={str(r['visible']):<5} min={str(r['minimized']):<5} class={r['cls']}\n"
            f"      title='{r['title']}'\n"
        )


if __name__ == "__main__":
    main()
