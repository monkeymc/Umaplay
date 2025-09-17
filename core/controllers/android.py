# core/controllers/scrcpy.py
from __future__ import annotations

import random
import time
from typing import Optional, Tuple, Union

import pyautogui
import pygetwindow as gw
from PIL import ImageGrab, Image

# Requires pywin32
import win32con
import win32gui

from core.controllers.base import IController, RegionXYWH
from core.types import XYXY


class ScrcpyController(IController):
    """
    Controller tailored for a scrcpy window (Android mirroring).
    - focus(): restores & foregrounds the target window.
    - screenshot(): captures the window client area (full), much faster than full screen.
    - move_xyxy_center(), click_xyxy_center(): convenience helpers using last screenshot space.
    """

    def __init__(
        self, window_title: str = "23117RA68G", capture_client_only: bool = True
    ):
        super().__init__(window_title=window_title, capture_client_only=capture_client_only)

    # --- window discovery ---

    def _find_window(self):
        """
        Prefer exact title match; if none, fall back to substring (case-insensitive).
        """
        wins = gw.getAllWindows()
        exact = [w for w in wins if w.title.strip() == self.window_title]
        if exact:
            return exact[0]
        sub = [w for w in wins if self.window_title.lower() in w.title.lower()]
        return sub[0] if sub else None

    def _get_hwnd(self) -> Optional[int]:
        w = self._find_window()
        return int(w._hWnd) if w else None  # pygetwindow stores HWND on _hWnd

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
                time.sleep(0.10)
                w.restore()
                time.sleep(0.20)

            # Activate via pygetwindow too
            try:
                w.activate()
            except Exception:
                pass

            time.sleep(0.10)
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

    # --- IController API ---

    def screenshot(self, region: Optional[RegionXYWH] = None) -> Image.Image:
        """
        If region is provided (absolute screen XYWH), capture that.
        Else, capture the window client area if capture_client_only=True, otherwise full screen.
        Keeps self._last_origin and self._last_bbox updated.
        """
        if region is not None:
            left, top, width, height = region
            bbox = (left, top, left + width, top + height)
            self._last_origin = (left, top)
            self._last_bbox = (left, top, width, height)
            return ImageGrab.grab(bbox=bbox)

        if self.capture_client_only:
            xywh = self._client_bbox_screen_xywh()
            if xywh:
                left, top, width, height = xywh
                self._last_origin = (left, top)
                self._last_bbox = (left, top, width, height)
                return ImageGrab.grab(bbox=(left, top, left + width, top + height))

        # Fallback: full screen
        scr = ImageGrab.grab()
        self._last_origin = (0, 0)
        self._last_bbox = (0, 0, scr.width, scr.height)
        return scr

    def scroll(
        self,
        delta_or_xyxy: Union[int, XYXY],
        *,
        steps: int = 1,
        default_down: bool = True,
        invert: bool = False,
        min_px: int = 30,
        jitter: int = 6,
        duration_range: Tuple[float, float] = (0.16, 0.26),
        pause_range: Tuple[float, float] = (0.03, 0.07),
        end_hold_range: Tuple[float, float] = (
            0.05,
            0.12,
        ),  # hold at end to kill inertia
    ) -> None:
        """
        Drag-based scroll for scrcpy windows.

        - scroll(-180)  -> scroll DOWN ~180 px (drag upward)
        - scroll(+220)  -> scroll UP   ~220 px (drag downward)
        - scroll((x1,y1,x2,y2)) -> use box height as distance (default DOWN)
        """
        xywh = self._client_bbox_screen_xywh()
        if not xywh:
            return
        L, T, W, H = xywh

        use_xyxy = isinstance(delta_or_xyxy, (tuple, list)) and len(delta_or_xyxy) == 4
        if use_xyxy:
            x1, y1, x2, y2 = map(float, delta_or_xyxy)
            cx, cy = self.center_from_xyxy((x1, y1, x2, y2))
            px = max(min_px, int(abs(y2 - y1)))
            down = default_down
        else:
            cx, cy = L + W // 2, T + H // 2
            delta = int(delta_or_xyxy)
            down = delta < 0
            px = max(min_px, abs(delta))

        if invert:
            down = not down

        def _clamp_y(y: int) -> int:
            return max(T + 10, min(T + H - 10, y))

        for _ in range(max(1, int(steps))):
            half = px // 2
            if down:
                y0 = _clamp_y(cy + half)  # start lower
                y1 = _clamp_y(cy - half)  # drag upward
            else:
                y0 = _clamp_y(cy - half)  # start upper
                y1 = _clamp_y(cy + half)  # drag downward

            j = int(jitter)
            xj = cx + (random.randint(-j, j) if j else 0)
            y0j = y0 + (random.randint(-j, j) if j else 0)
            y1j = y1 + (random.randint(-j, j) if j else 0)

            # Drag with a short HOLD at the end to dampen kinetic scrolling
            self.move_to(xj, y0j, duration=random.uniform(0.05, 0.10))
            pyautogui.mouseDown(xj, y0j)
            self.move_to(xj, y1j, duration=random.uniform(*duration_range))
            time.sleep(random.uniform(*end_hold_range))  # <<< hold here
            pyautogui.mouseUp(xj, y1j)

            time.sleep(random.uniform(*pause_range))
