"""Utility to display a lightweight floating preset overlay on Windows/macOS/Linux.

The overlay is implemented with Tkinter so it is non-invasive and auto-closes
after the configured timeout. If Tkinter is unavailable (e.g., stripped
Python), the helper simply logs the issue and no overlay is shown.
"""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)


def show_preset_overlay(
    message: str,
    *,
    duration: float = 5.0,
    x: int = 32,
    y: int = 32,
    background: str = "#1E40AF",
    foreground: str = "#FFFFFF",
) -> None:
    """Render a small always-on-top toast with ``message`` for ``duration`` seconds.

    The toast is non-blocking; the UI is rendered on a daemon thread so the
    caller can continue execution immediately.
    """

    if not message:
        return

    duration = max(1.0, float(duration or 0.0))

    def _worker() -> None:
        try:
            import tkinter as tk  # type: ignore
            from tkinter import font as tkfont
        except Exception as exc:  # pragma: no cover - executed only when Tk missing
            logger.debug("Preset overlay unavailable (tkinter import failed): %s", exc)
            return

        try:
            root = tk.Tk()
            root.overrideredirect(True)
            root.attributes("-topmost", True)
            try:
                root.wm_attributes("-alpha", 0.94)
            except Exception:
                pass
            root.configure(bg="")

            container = tk.Frame(root, bg=background, bd=0, relief="flat")
            container.pack(padx=0, pady=0)

            body = tk.Frame(container, bg=background)
            body.pack(padx=0, pady=0)

            icon_size = 18
            icon_canvas = tk.Canvas(
                body,
                width=icon_size,
                height=icon_size,
                highlightthickness=0,
                bg=background,
                bd=0,
            )
            icon_canvas.grid(row=0, column=0, padx=(18, 10), pady=12)
            icon_canvas.create_oval(
                2,
                2,
                icon_size - 2,
                icon_size - 2,
                fill="#FACC15",
                outline="",
            )

            title_font = tkfont.Font(family="Segoe UI", size=13, weight="bold")

            label = tk.Label(
                body,
                text=message,
                font=title_font,
                fg=foreground,
                bg=background,
                justify="left",
            )
            label.grid(row=0, column=1, padx=(0, 20), pady=12, sticky="w")

            root.update_idletasks()
            width = root.winfo_width()
            height = root.winfo_height()

            geom = f"{width}x{height}+{max(0, x)}+{max(0, y)}"
            root.geometry(geom)

            # Add subtle shadow using additional transparent toplevel if supported
            try:
                shadow = tk.Toplevel(root)
                shadow.overrideredirect(True)
                shadow.attributes("-topmost", True)
                shadow.geometry(f"{width}x{height}+{max(0, x)+4}+{max(0, y)+6}")
                shadow.configure(bg="#000000")
                shadow.attributes("-alpha", 0.15)
                shadow.lower(root)
                root.after(int(duration * 1000), shadow.destroy)
            except Exception:
                pass

            root.after(int(duration * 1000), root.destroy)
            root.mainloop()
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.exception("Failed to render preset overlay: %s", exc)

    threading.Thread(target=_worker, daemon=True).start()
