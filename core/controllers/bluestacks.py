# core/controllers/bluestacks.py
from __future__ import annotations

import random
import time
from typing import Optional, Tuple, Union

import pyautogui
import pygetwindow as gw
from PIL import ImageGrab
import ctypes
import win32api
import win32process

# Requires pywin32
import win32con
import win32gui

from core.controllers.base import IController, RegionXYWH
from core.types import XYXY

user32 = ctypes.windll.user32
class BlueStacksController(IController):
    """
    Controller tailored for the BlueStacks emulator window on Windows.

    Key ideas:
    - Window discovery prefers an exact match to the provided `window_title`,
      then falls back to common BlueStacks title patterns (substring match).
    - Screenshots are taken from the window CLIENT AREA (fast), and we store
      the last-capture origin so YOLO/ocr local coords can be translated into
      absolute screen coords for pointer actions.
    - Input uses standard mouse move/click/scroll (BlueStacks maps these to touch/scroll).

    Notes:
    - If your BlueStacks layout has extra toolbars (top/side), you can pass
      `content_insets=(L,T,R,B)` to crop them out from the client area when
      capturing and clicking. Defaults to (0,0,0,0).
    """

    # Common substrings BlueStacks windows usually contain
    FALLBACK_TITLES = (
        "bluestacks",          # "BlueStacks", "BlueStacks 5", "BlueStacks App Player", etc.
        "app player",          # some versions
    )

    def __init__(
        self,
        window_title: str = "BlueStacks",
        *,
        capture_client_only: bool = True,
        content_insets: Tuple[int, int, int, int] = (0, 0, 0, 0),
    ):
        """
        Args:
            window_title: Preferred title to match (exact or substring).
            capture_client_only: Always True for speed/consistency.
            content_insets: (left, top, right, bottom) pixels to crop away
                            from the client area (useful if BlueStacks shows
                            a top bar or side toolbar inside client).
        """
        super().__init__(window_title=window_title, capture_client_only=capture_client_only)
        self.content_insets = tuple(int(v) for v in content_insets)
        self._client_bbox_cache: Optional[RegionXYWH] = None  # screen-space client bbox (x, y, w, h)

    # -------------------------
    # Window discovery
    # -------------------------
    def _find_window(self):
        """
        Prefer exact match; then substring match for provided `window_title`;
        finally fall back to generic BlueStacks title patterns.
        """
        wins = gw.getAllWindows()
        if not wins:
            return None

        # 1) Exact title match
        for w in wins:
            if w.title.strip() == self.window_title:
                return w

        # 2) Substring match with the configured title
        if self.window_title:
            low = self.window_title.lower()
            subs = [w for w in wins if low in w.title.lower()]
            if subs:
                # Prefer the most visible/normal window (not minimized)
                subs.sort(key=lambda ww: (not ww.isMinimized, ww.isActive, len(ww.title)), reverse=True)
                return subs[0]

        # 3) Fallback to common BlueStacks patterns
        candidates = []
        for w in wins:
            t = w.title.lower()
            if any(pat in t for pat in self.FALLBACK_TITLES):
                candidates.append(w)
        if candidates:
            candidates.sort(key=lambda ww: (not ww.isMinimized, ww.isActive, len(ww.title)), reverse=True)
            return candidates[0]

        return None

    def _get_hwnd(self) -> Optional[int]:
        w = self._find_window()
        return int(getattr(w, "_hWnd", 0)) if w else None

    # -------------------------
    # Focus / restore
    # -------------------------
    def focus(self) -> bool:
        """
        Robustly bring BlueStacks to the foreground. Handles the Windows
        foreground lock by temporarily attaching input queues, toggling
        TOPMOST, and using minimize/restore as a last resort.
        """
        w = self._find_window()
        if not w:
            return False

        hwnd = int(getattr(w, "_hWnd", 0))
        if not hwnd or not win32gui.IsWindow(hwnd):
            return False

        try:
            # If minimized, restore first
            if w.isMinimized:
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                time.sleep(0.05)

            # Try the simple path first
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.02)
            if win32gui.GetForegroundWindow() == hwnd:
                return True
        except Exception:
            pass

        # Hard path: attach thread input and promote z-order
        try:
            # Current foreground window & its thread
            fore = win32gui.GetForegroundWindow()
            cur_tid = win32api.GetCurrentThreadId()
            fore_tid = win32process.GetWindowThreadProcessId(fore)[0] if fore else 0
            target_tid = win32process.GetWindowThreadProcessId(hwnd)[0]

            attached = False
            if fore and fore_tid and fore_tid != target_tid:
                # Attach input queues so we can legally steal focus
                attached = bool(user32.AttachThreadInput(fore_tid, target_tid, True))

            # Make it topmost momentarily, then normal top to bubble it
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW)
            time.sleep(0.01)
            win32gui.SetWindowPos(hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0,
                                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW)

            # Activate/bring to top
            try:
                win32gui.BringWindowToTop(hwnd)
                win32gui.SetActiveWindow(hwnd)
            except Exception:
                pass

            # Try foreground again
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.02)

            # Detach if we attached
            if attached:
                user32.AttachThreadInput(fore_tid, target_tid, False)

            if win32gui.GetForegroundWindow() == hwnd:
                return True
        except Exception:
            pass

        # Last-resort tricks: ALT key jiggle and minimize/restore
        try:
            VK_MENU = 0x12  # ALT
            win32api.keybd_event(VK_MENU, 0, 0, 0)
            win32api.keybd_event(VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.01)
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.02)
            if win32gui.GetForegroundWindow() == hwnd:
                return True
        except Exception:
            pass

        try:
            win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
            time.sleep(0.05)
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            time.sleep(0.05)
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.02)
            return win32gui.GetForegroundWindow() == hwnd
        except Exception:
            return False

    # -------------------------
    # Geometry helpers
    # -------------------------
    def _client_bbox_screen_xywh(self) -> RegionXYWH:
        """
        Return the BlueStacks *client area* rectangle in SCREEN coordinates (x, y, w, h),
        cropped by `content_insets`.

        We cache it for the session unless BlueStacks is moved/resized; if you need
        live updates every call, drop the cache (or we could add a staleness check).
        """
        hwnd = self._get_hwnd()
        if not hwnd:
            # Return a degenerate rect; the caller will likely fail to capture & handle it.
            return (0, 0, 0, 0)

        # Client rect (0,0)-(w,h) in client coords
        try:
            cx1, cy1, cx2, cy2 = win32gui.GetClientRect(hwnd)
        except Exception:
            return (0, 0, 0, 0)

        # Convert client coords to screen coords
        try:
            sx1, sy1 = win32gui.ClientToScreen(hwnd, (cx1, cy1))
            sx2, sy2 = win32gui.ClientToScreen(hwnd, (cx2, cy2))
        except Exception:
            return (0, 0, 0, 0)

        x, y = int(sx1), int(sy1)
        w, h = max(0, int(sx2 - sx1)), max(0, int(sy2 - sy1))

        # Apply optional content insets to drop BlueStacks toolbars inside client area
        if any(self.content_insets):
            l, t, r, b = self.content_insets
            x += l
            y += t
            w = max(0, w - l - r)
            h = max(0, h - t - b)

        # Cache & return
        self._client_bbox_cache = (x, y, w, h)
        return self._client_bbox_cache

    # -------------------------
    # Capture
    # -------------------------
    def screenshot(self, region=None):
        """
        Capture the current BlueStacks client area (respecting content insets),
        store the last-capture origin/size for downstream coordinate transforms,
        and return a PIL.Image in RGB.
        """
        x, y, w, h = self._client_bbox_screen_xywh()
        if w <= 0 or h <= 0:
            # Nothing to capture
            return None

        # Grab window client bbox (screen coords)
        img = ImageGrab.grab(bbox=(x, y, x + w, y + h))

        # Update origin & size so local_to_screen() and click helpers remain correct
        try:
            # Preferred: base class helper if present
            self._set_last_capture_origin((x, y), (w, h))  # type: ignore[attr-defined]
        except Exception:
            # Fallback: set common fields used by base.local_to_screen
            setattr(self, "_last_origin", (x, y))
            setattr(self, "_last_size", (w, h))

        return img

    # -------------------------
    # Scroll
    # -------------------------
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
