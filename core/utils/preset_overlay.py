"""Utility to display a lightweight floating preset overlay on Windows/macOS/Linux.

The overlay is implemented with Tkinter so it is non-invasive and auto-closes
after the configured timeout. If Tkinter is unavailable (e.g., stripped
Python), the helper simply logs the issue and no overlay is shown.
"""

from __future__ import annotations

import logging

from core.utils.tkthread import post

logger = logging.getLogger(__name__)


def show_preset_overlay(
    message: str,
    *,
    duration: float = 5.0,
    x: int = 32,
    y: int | str = 32,
    background: str = "#10B981",  # Modern emerald green
    foreground: str = "#FFFFFF",
) -> None:
    """Render a toast overlay safely on the shared Tk UI thread.
    
    Args:
        y: Vertical position. Can be an int for absolute position, or 'center' to center vertically.
    """

    if not message:
        return

    safe_duration = max(1.0, float(duration or 0.0))

    def _show(root, text: str) -> None:
        try:
            import tkinter as tk
            from tkinter import font as tkfont
        except Exception as exc:  # pragma: no cover - Tk unavailable
            logger.debug("Preset overlay unavailable (tkinter import failed): %s", exc)
            return

        toast = tk.Toplevel(root)
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)
        try:
            toast.wm_attributes("-alpha", 0.94)
        except Exception:
            pass
        toast.configure(bg="")

        container = tk.Frame(toast, bg=background, bd=3, relief="solid", highlightbackground="#FFFFFF", highlightthickness=2)
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
            fill="#FBBF24",  # Brighter amber/gold
            outline="#FFFFFF",
            width=2,
        )

        title_font = tkfont.Font(family="Segoe UI", size=13, weight="bold")
        label = tk.Label(
            body,
            text=text,
            font=title_font,
            fg=foreground,
            bg=background,
            justify="left",
        )
        label.grid(row=0, column=1, padx=(0, 20), pady=12, sticky="w")

        toast.update_idletasks()
        width = toast.winfo_width()
        height = toast.winfo_height()
        
        # Calculate y position
        if y == "center":
            screen_height = toast.winfo_screenheight()
            y_pos = max(0, (screen_height - height) // 2)
        else:
            y_pos = max(0, int(y))
        
        geom = f"{width}x{height}+{max(0, x)}+{y_pos}"
        toast.geometry(geom)

        shadow = None
        try:
            shadow = tk.Toplevel(root)
            shadow.overrideredirect(True)
            shadow.attributes("-topmost", True)
            shadow.geometry(f"{width}x{height}+{max(0, x)+4}+{y_pos+6}")
            shadow.configure(bg="#000000")
            shadow.attributes("-alpha", 0.15)
            shadow.lower(toast)

            def _destroy_shadow(*_):
                try:
                    if shadow and shadow.winfo_exists():
                        shadow.destroy()
                except Exception:
                    pass

            toast.bind("<Destroy>", _destroy_shadow, add=True)
        except Exception:
            shadow = None

        ms = max(250, int(safe_duration * 1000))
        toast.after(ms, lambda: toast.destroy() if toast.winfo_exists() else None)

    post(_show, message)
