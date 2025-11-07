from __future__ import annotations

from typing import Callable

from core.utils.tkthread import call

ALLOWED_SCENARIOS: tuple[str, str] = ("ura", "unity_cup")


class ScenarioSelectionCancelled(RuntimeError):
    """Raised when the user cancels the scenario selection dialog."""


PromptFn = Callable[[str], str]


def _normalize(value: str | None) -> str:
    if not value:
        return "ura"
    normalized = str(value).strip().lower()
    if normalized in ALLOWED_SCENARIOS:
        return normalized
    return "ura"


def choose_active_scenario(
    last_scenario: str | None,
    prompt: PromptFn | None = None,
) -> str:
    """Return the scenario selected by the user.

    Parameters
    ----------
    last_scenario:
        Previously active scenario. If invalid, defaults to URA.
    prompt:
        Optional callable responsible for prompting the user. Receives the
        default scenario and must return the selected scenario string.
    """

    default_choice = _normalize(last_scenario)
    prompt_fn = prompt or _default_prompt

    try:
        raw_choice = prompt_fn(default_choice)
    except ScenarioSelectionCancelled:
        raise
    except KeyboardInterrupt as exc:  # pragma: no cover - defensive guard
        raise ScenarioSelectionCancelled() from exc

    return _normalize(raw_choice)


def _default_prompt(default_choice: str) -> str:
    """Render the scenario chooser dialog on the dedicated Tk UI thread."""

    def _dialog(root, choice: str):
        import tkinter as tk
        from tkinter import ttk
        from pathlib import Path

        result = {"value": choice}
        cancelled = {"flag": False}

        win = tk.Toplevel(root)
        win.title("Select Scenario")
        win.resizable(False, False)

        win.update_idletasks()
        width = 400
        height = 200
        x = (win.winfo_screenwidth() // 2) - (width // 2)
        y = (win.winfo_screenheight() // 2) - (height // 2)
        win.geometry(f"{width}x{height}+{x}+{y}")
        
        # Aggressive focus stealing for Windows
        win.lift()
        win.attributes("-topmost", True)
        win.focus_force()
        win.grab_set()  # Make modal and capture input
        
        # Schedule repeated focus attempts
        def _refocus():
            try:
                win.lift()
                win.focus_force()
                win.attributes("-topmost", False)
            except Exception:
                pass
        
        win.after(50, _refocus)
        win.after(150, _refocus)

        main_frame = ttk.Frame(win, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        title_label = ttk.Label(
            main_frame,
            text="Choose Scenario",
            font=("Segoe UI", 14, "bold"),
        )
        title_label.pack(pady=(0, 20))

        buttons_frame = ttk.Frame(main_frame)
        buttons_frame.pack(fill=tk.BOTH, expand=True)

        scenarios = [
            {"key": "ura", "label": "URA", "icon": "ura_icon.png"},
            {"key": "unity_cup", "label": "Unity Cup", "icon": "unity_cup_icon.png"},
        ]

        photos = []
        try:
            assets_dir = Path(__file__).resolve().parents[2] / "web" / "public" / "scenarios"
        except Exception:
            assets_dir = None

        def on_select(option: str):
            result["value"] = option
            try:
                win.destroy()
            except Exception:
                pass

        def on_cancel():
            cancelled["flag"] = True
            try:
                win.destroy()
            except Exception:
                pass

        for scenario in scenarios:
            btn_frame = ttk.Frame(buttons_frame)
            btn_frame.pack(side=tk.LEFT, padx=10, fill=tk.BOTH, expand=True)

            photo = None
            if assets_dir and assets_dir.exists():
                icon_path = assets_dir / scenario["icon"]
                if icon_path.exists():
                    try:
                        from PIL import Image, ImageTk

                        img = Image.open(icon_path)
                        img = img.resize((64, 64), Image.Resampling.LANCZOS)
                        photo = ImageTk.PhotoImage(img)
                        photos.append(photo)
                    except Exception:
                        pass

            is_default = scenario["key"] == choice
            btn = tk.Button(
                btn_frame,
                text=scenario["label"],
                command=lambda c=scenario["key"]: on_select(c),
                font=("Segoe UI", 11, "bold" if is_default else "normal"),
                bg="#4CAF50" if is_default else "#2196F3",
                fg="white",
                activebackground="#45a049" if is_default else "#0b7dda",
                activeforeground="white",
                relief=tk.RAISED,
                bd=3 if is_default else 2,
                cursor="hand2",
                padx=20,
                pady=15,
            )

            if photo:
                btn.config(image=photo, compound=tk.TOP)

            btn.pack(fill=tk.BOTH, expand=True)

            if is_default:
                btn.focus_set()

        cancel_btn = ttk.Button(main_frame, text="Cancel", command=on_cancel)
        cancel_btn.pack(pady=(20, 0))

        # Bind window close button (X) to cancel
        win.protocol("WM_DELETE_WINDOW", on_cancel)
        
        win.bind("<Escape>", lambda e: on_cancel())
        win.bind("1", lambda e: on_select("ura"))
        win.bind("2", lambda e: on_select("unity_cup"))

        root.wait_window(win)
        return cancelled["flag"], result["value"]

    cancelled, value = call(_dialog, default_choice)
    if cancelled:
        raise ScenarioSelectionCancelled()

    return _normalize(value)


__all__ = [
    "ALLOWED_SCENARIOS",
    "ScenarioSelectionCancelled",
    "choose_active_scenario",
]
