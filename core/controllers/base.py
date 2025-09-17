from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional, Tuple

import random
import time
import pyautogui
from PIL import ImageGrab, Image

from core.types import XYXY, RegionXYWH
from core.utils.geometry import calculate_jitter



class IController(ABC):
    """
    Abstract device/window controller.

    Concrete subclasses MUST implement:
      - _find_window()
      - _get_hwnd()
      - _client_bbox_screen_xywh()
      - focus()

    Everything else is generic and implemented here.
    """

    def __init__(self, window_title: str, capture_client_only: bool = True) -> None:
        self.window_title = window_title
        self.capture_client_only = capture_client_only
        self._last_origin: Tuple[int, int] = (0, 0)      # (left, top) of last capture in SCREEN coords
        self._last_bbox:   Tuple[int, int, int, int] = (0, 0, 0, 0)  # (L, T, W, H)

    # ---- Abstracts that depend on platform/window system ----
    @abstractmethod
    def _find_window(self):
        """Return a toolkit-specific window object/handle (or None)."""
        ...

    @abstractmethod
    def _get_hwnd(self) -> Optional[int]:
        """Return native HWND/handle if available (Windows), else None."""
        ...

    @abstractmethod
    def _client_bbox_screen_xywh(self) -> Optional[RegionXYWH]:
        """(left, top, width, height) of client area in *screen* coords, or None."""
        ...

    @abstractmethod
    def focus(self) -> bool:
        """Bring window to foreground (restore if minimized)."""
        ...

    @abstractmethod
    def scroll(self, amount: int) -> bool:
        """Scrolling function"""
        ...

    # ---- Generic capture & geometry ----
    def screenshot(self, region: Optional[RegionXYWH] = None) -> Image.Image:
        """
        Capture a screenshot.

        - If `region` is provided, it MUST be absolute SCREEN coords (L, T, W, H).
        - Else if `capture_client_only=True`, capture the client area.
        - Else capture full screen.

        Updates internal origin/bbox accordingly.
        """
        if region is not None:
            L, T, W, H = region
            self._last_origin = (L, T)
            self._last_bbox = (L, T, W, H)
            return ImageGrab.grab(bbox=(L, T, L + W, T + H))

        if self.capture_client_only:
            xywh = self._client_bbox_screen_xywh()
            if xywh:
                L, T, W, H = xywh
                self._last_origin = (L, T)
                self._last_bbox = (L, T, W, H)
                return ImageGrab.grab(bbox=(L, T, L + W, T + H))

        # Fallback: full screen
        scr = ImageGrab.grab()
        self._last_origin = (0, 0)
        self._last_bbox = (0, 0, scr.width, scr.height)
        return scr

    def resolution(self) -> Tuple[int, int]:
        sz = pyautogui.size()
        return sz.width, sz.height

    # ---- Coordinate helpers ----
    def capture_origin(self) -> Tuple[int, int]:
        """(left, top) of the last screenshot, in screen coords."""
        return self._last_origin

    def capture_bbox(self) -> Tuple[int, int, int, int]:
        """(left, top, width, height) of the last screenshot."""
        return self._last_bbox

    def local_to_screen(self, x: int, y: int) -> Tuple[int, int]:
        """Translate a point in *last screenshot space* to absolute screen coords."""
        ox, oy = self._last_origin
        return ox + x, oy + y

    def to_center(self, box_xywh: Tuple[int, int, int, int]) -> Tuple[int, int]:
        """Center of a (x,y,w,h) box defined in *last screenshot* coords, returned in SCREEN coords."""
        x, y, w, h = box_xywh
        ox, oy = self._last_origin
        return ox + x + w // 2, oy + y + h // 2

    def center_from_xyxy(self, xyxy: XYXY) -> Tuple[int, int]:
        """Center of an (x1,y1,x2,y2) rect defined in *last screenshot* coords, returned in SCREEN coords."""
        x1, y1, x2, y2 = xyxy
        cx_local = int(round((x1 + x2) / 2.0))
        cy_local = int(round((y1 + y2) / 2.0))
        ox, oy = self._last_origin
        return ox + cx_local, oy + cy_local

    # ---- Pointer primitives (screen coords) ----
    def move_to(self, x: int, y: int, duration: float = 0.15) -> None:
        pyautogui.moveTo(int(x), int(y), duration=duration)

    def click(
        self,
        x: int,
        y: int,
        *,
        clicks: int = 1,
        duration: float = 0.15,
        use_organic_move: bool = True,
        jitter: int = 2,
    ) -> None:
        tx, ty = int(x), int(y)
        if jitter and jitter > 0:
            tx += random.randint(-jitter, jitter)
            ty += random.randint(-jitter, jitter)

        if use_organic_move:
            self.move_to(tx, ty, duration=random.uniform(0.12, 0.22))
            time.sleep(random.uniform(0.03, 0.08))
            interval = 0 if clicks <= 1 else random.uniform(0.17, 0.47)
            pyautogui.click(tx, ty, clicks=clicks, duration=0.00, interval=interval)
        else:
            self.move_to(tx, ty, duration=duration)
            pyautogui.click(tx, ty, clicks=clicks)

    def click_xyxy_center(
        self,
        xyxy: XYXY,
        *,
        clicks: int = 1,
        move_duration: float = 0.08,
        use_organic_move: bool = True,
        jitter: Optional[int] = None,
        percentage_offset: float = 0.20,
    ) -> None:
        if jitter is None:
            jitter = calculate_jitter(xyxy, percentage_offset=percentage_offset)
        sx, sy = self.center_from_xyxy(xyxy)
        self.click(
            sx,
            sy,
            clicks=clicks,
            duration=move_duration,
            use_organic_move=use_organic_move,
            jitter=jitter,
        )

    def move_xyxy_center(
        self,
        xyxy: XYXY,
        *,
        jitter: Optional[int] = None,
        percentage_offset: float = 0.20,
        duration_range: Tuple[float, float] = (0.12, 0.22),
        micro_pause_range: Tuple[float, float] = (0.02, 0.06),
    ) -> None:
        if jitter is None:
            jitter = calculate_jitter(xyxy, percentage_offset=percentage_offset)
        sx, sy = self.center_from_xyxy(xyxy)
        if jitter and jitter > 0:
            sx += random.randint(-jitter, jitter)
            sy += random.randint(-jitter, jitter)
        self.move_to(sx, sy, duration=random.uniform(*duration_range))
        time.sleep(random.uniform(*micro_pause_range))

    def mouse_down(
        self,
        x: int,
        y: int,
        *,
        button: str = "left",
        use_organic_move: bool = True,
        jitter: int = 2,
    ) -> None:
        tx, ty = int(x), int(y)
        if jitter and jitter > 0:
            tx += random.randint(-jitter, jitter)
            ty += random.randint(-jitter, jitter)
        if use_organic_move:
            self.move_to(tx, ty, duration=random.uniform(0.10, 0.20))
            time.sleep(random.uniform(0.02, 0.06))
        else:
            self.move_to(tx, ty, duration=0.0)
        pyautogui.mouseDown(x=tx, y=ty, button=button)

    def mouse_up(self, x: int, y: int, *, button: str = "left") -> None:
        pyautogui.mouseUp(x=int(x), y=int(y), button=button)

    def hold(self, x: int, y: int, seconds: float, *, jitter: int = 2) -> None:
        self.mouse_down(x, y, jitter=jitter)
        try:
            time.sleep(max(0.0, float(seconds)))
        finally:
            self.mouse_up(x, y)
