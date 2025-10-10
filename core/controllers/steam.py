# core/controllers/steam.py
import time
from typing import Optional

import pyautogui
import pygetwindow as gw

# Requires pywin32
import win32con
import win32gui

from core.controllers.base import IController, RegionXYWH


class SteamController(IController):
    """
    - focus(): restores & foregrounds the target window.
    - screenshot(): by default captures the window's *client area* only (much faster than full screen).
      Keeps track of the last capture origin so you can translate local coords -> screen coords.
    """

    def __init__(
        self, window_title: str = "Umamusume", capture_client_only: bool = True
    ):
        super().__init__(
            window_title=window_title, capture_client_only=capture_client_only
        )

    # --- window discovery ---
    def _find_window(self):
        wins = [
            w
            for w in gw.getWindowsWithTitle(self.window_title)
            if w.title.strip() == self.window_title
        ]
        return wins[0] if wins else None

    def _get_hwnd(self) -> Optional[int]:
        w = self._find_window()
        return int(w._hWnd) if w else None  # pygetwindow stores the HWND on _hWnd

    # --- focusing / restore ---
    def focus(self) -> bool:
        try:
            w = self._find_window()
            if not w:
                return False

            # Restore if minimized
            if w.isMinimized:
                win32gui.ShowWindow(int(w._hWnd), win32con.SW_RESTORE)
                time.sleep(0.15)

            # Bring to foreground
            try:
                win32gui.SetForegroundWindow(int(w._hWnd))
            except Exception:
                # Fallback via minimize/restore trick
                w.minimize()
                time.sleep(0.1)
                w.restore()
                time.sleep(0.2)

            # Activate via pygetwindow too
            try:
                w.activate()
            except Exception:
                pass

            time.sleep(0.1)
            return True
        except Exception:
            return False

    # --- geometry helpers ---

    def _client_bbox_screen_xywh(self) -> Optional[RegionXYWH]:
        """
        Returns (left, top, width, height) of the *client area* in SCREEN coordinates.
        """
        hwnd = self._get_hwnd()
        if (
            not hwnd
            or not win32gui.IsWindow(hwnd)
            or not win32gui.IsWindowVisible(hwnd)
        ):
            return None

        # Client rect is (0,0)-(w,h) in client coords
        try:
            left_top = win32gui.ClientToScreen(hwnd, (0, 0))
            right_bottom = win32gui.ClientToScreen(
                hwnd, win32gui.GetClientRect(hwnd)[2:]
            )
            left, top = left_top
            right, bottom = right_bottom
            width, height = max(0, right - left), max(0, bottom - top)
            if width == 0 or height == 0:
                return None
            return (left, top, width, height)
        except Exception:
            return None

    def scroll(self, amount: int) -> None:
        pyautogui.scroll(amount)

    # convenience: left half bbox in screen coords
    def left_half_bbox(self) -> Optional[RegionXYWH]:
        xywh = self._client_bbox_screen_xywh()
        if not xywh:
            return None
        L, T, W, H = xywh
        return (L, T, W // 2, H)

    # convenience: capture left half (also updates last_origin)
    def screenshot_left_half(self):
        xywh = self.left_half_bbox()
        if not xywh:
            # fall back to full client area which also sets last_origin
            return self.screenshot()
        return self.screenshot(region=xywh)
