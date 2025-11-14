from __future__ import annotations

import queue
import threading
import traceback
from typing import Any, Callable

try:
    from typing import TYPE_CHECKING
except ImportError:  # pragma: no cover - Python <3.11 fallback
    TYPE_CHECKING = False

__all__ = ["ensure_tk_loop", "call", "post"]

if TYPE_CHECKING:
    import tkinter as tk  # pragma: no cover

# Holds the hidden Tk root created on the UI thread
_root: "tk.Tk | None" = None
_ui_thread: threading.Thread | None = None
_ready = threading.Event()
_task_q: "queue.Queue[tuple[Callable[..., Any], tuple[Any, ...], dict[str, Any], threading.Event | None, list[Any] | None]]" = queue.Queue()


def _ui_main() -> None:
    global _root

    import tkinter as tk  # Local import so Tk is only touched on this thread

    root = tk.Tk()
    root.withdraw()
    globals()["_root"] = root
    _ready.set()

    def _pump() -> None:
        try:
            while True:
                try:
                    fn, args, kwargs, ev, box = _task_q.get_nowait()
                except queue.Empty:
                    break
                try:
                    result = fn(root, *args, **kwargs)
                    if box is not None:
                        box.append(result)
                except Exception:
                    traceback.print_exc()
                finally:
                    if ev is not None:
                        ev.set()
        finally:
            root.after(10, _pump)

    _pump()
    root.mainloop()


def ensure_tk_loop() -> None:
    """Start the dedicated Tk UI loop thread (idempotent)."""

    global _ui_thread
    if _ui_thread and _ui_thread.is_alive():
        return

    _ui_thread = threading.Thread(target=_ui_main, name="TkUI", daemon=True)
    _ui_thread.start()
    _ready.wait()


def call(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run *fn* on the Tk UI thread and return its result."""

    ensure_tk_loop()
    done = threading.Event()
    box: list[Any] = []
    _task_q.put((fn, args, kwargs, done, box))
    done.wait()
    return box[0] if box else None


def post(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
    """Schedule *fn* to run on the Tk UI thread (fire-and-forget)."""

    ensure_tk_loop()
    _task_q.put((fn, args, kwargs, None, None))
