# core/controllers/scrcpy.py
from __future__ import annotations

import os
import random
import time
from typing import Optional, Tuple, List, Dict, Union

import pyautogui
import pygetwindow as gw
from PIL import ImageGrab, Image, ImageDraw

# Requires pywin32
import win32con
import win32gui

from core.controllers.base import IController, RegionXYWH
from core.perception.detection import detect_on_pil
from core.settings import Settings
from core.types import XYXY, DetectionDict
from core.utils.logger import logger_uma
from core.utils.geometry import calculate_jitter


class ScrcpyController(IController):
    """
    Controller tailored for a scrcpy window (Android mirroring).
    - focus(): restores & foregrounds the target window.
    - screenshot(): captures the window client area (full), much faster than full screen.
    - recognize_objects_in_screen(): runs YOLO over the full client area (not just left half).
    - move_xyxy_center(), click_xyxy_center(): convenience helpers using last screenshot space.
    """

    def __init__(self, window_title: str = "23117RA68G", capture_client_only: bool = True):
        self.window_title = window_title
        self.capture_client_only = capture_client_only
        self._last_origin: Tuple[int, int] = (0, 0)           # (left, top) of last screenshot in screen coords
        self._last_bbox:   Tuple[int, int, int, int] = (0, 0, 0, 0)  # (L, T, W, H)

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
                w.minimize(); time.sleep(0.10); w.restore(); time.sleep(0.20)

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
        if not hwnd or not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
            return None

        try:
            left_top = win32gui.ClientToScreen(hwnd, (0, 0))
            right_bottom = win32gui.ClientToScreen(hwnd, win32gui.GetClientRect(hwnd)[2:])
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

    def move_to(self, x: int, y: int, duration: float = 0.15) -> None:
        pyautogui.moveTo(x, y, duration=duration)

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
        """
        Click at absolute SCREEN coordinates (x, y).
        """
        # final target with optional jitter
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
        xyxy: tuple[float, float, float, float],
        *,
        clicks: int = 1,
        move_duration: float = 0.08,
        use_organic_move: bool = True,
        jitter: Optional[int] = None,   # None -> auto via calculate_jitter
        percentage_offset: float = 0.20
    ) -> None:
        """
        Click the center of an xyxy RECT (given in *last screenshot* coordinates).
        """
        if jitter is None:
            jitter = calculate_jitter(xyxy, percentage_offset=percentage_offset)
        sx, sy = self.center_from_xyxy(xyxy)
        self.click(
            sx, sy,
            clicks=clicks,
            duration=move_duration,
            use_organic_move=use_organic_move,
            jitter=jitter,
        )

    def move_xyxy_center(
        self,
        xyxy: tuple[float, float, float, float],
        *,
        jitter: Optional[int] = None,          # None -> auto via calculate_jitter
        percentage_offset: float = 0.20,
        duration_range: tuple[float, float] = (0.12, 0.22),
        micro_pause_range: tuple[float, float] = (0.02, 0.06),
    ) -> None:
        """
        Move the cursor (no click) to the center of an xyxy RECT given in *last
        screenshot/local* coordinates. Applies small randomization to look natural.
        """
        if jitter is None:
            jitter = calculate_jitter(xyxy, percentage_offset=percentage_offset)

        sx, sy = self.center_from_xyxy(xyxy)  # local center -> screen coords
        if jitter and jitter > 0:
            sx += random.randint(-jitter, jitter)
            sy += random.randint(-jitter, jitter)

        self.move_to(sx, sy, duration=random.uniform(*duration_range))
        time.sleep(random.uniform(*micro_pause_range))

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
        end_hold_range: Tuple[float, float] = (0.05, 0.12),  # hold at end to kill inertia
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
            down = (delta < 0)
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
            xj  = cx + (random.randint(-j, j) if j else 0)
            y0j = y0 + (random.randint(-j, j) if j else 0)
            y1j = y1 + (random.randint(-j, j) if j else 0)

            # Drag with a short HOLD at the end to dampen kinetic scrolling
            self.move_to(xj, y0j, duration=random.uniform(0.05, 0.10))
            pyautogui.mouseDown(xj, y0j)
            self.move_to(xj, y1j, duration=random.uniform(*duration_range))
            time.sleep(random.uniform(*end_hold_range))   # <<< hold here
            pyautogui.mouseUp(xj, y1j)

            time.sleep(random.uniform(*pause_range))

    def resolution(self) -> Tuple[int, int]:
        res = pyautogui.size()
        return res.width, res.height

    # --- capture origin helpers for coordinate translation ---

    def capture_origin(self) -> Tuple[int, int]:
        """(left, top) in screen coords of the last screenshot."""
        return self._last_origin

    def capture_bbox(self) -> Tuple[int, int, int, int]:
        """(left, top, width, height) of the last screenshot."""
        return self._last_bbox

    def local_to_screen(self, x: int, y: int) -> Tuple[int, int]:
        """Translate a point in *last screenshot space* to absolute screen coords."""
        ox, oy = self._last_origin
        return ox + x, oy + y

    def to_center(self, box) -> tuple[int, int]:
        x, y, w, h = box
        ox, oy = self.capture_origin()
        return ox + x + w // 2, oy + y + h // 2

    def center_from_xyxy(self, xyxy: Tuple[float, float, float, float]) -> Tuple[int, int]:
        """Return center in *screen* coords for a local xyxy (from last screenshot)."""
        x1, y1, x2, y2 = xyxy
        cx_local = int(round((x1 + x2) / 2.0))
        cy_local = int(round((y1 + y2) / 2.0))
        ox, oy = self.capture_origin()
        return ox + cx_local, oy + cy_local

    # --- Perception helpers ---

    def recognize_objects_in_screen(
        self,
        *,
        imgsz: Optional[int] = None,
        conf: Optional[float] = None,
        iou: Optional[float] = None,
        tag: str = "general"
    ) -> Tuple[Image.Image, object, List[DetectionDict]]:
        """
        Capture the FULL client area (scrcpy window) and run YOLO on it.
        Returns:
            (img [PIL.Image], yolo_result, dets [List[DetectionDict]])
        Notes:
            - Thresholds default to Settings.* when None.
            - Uses the cached YOLO model inside core.perception.detection.
        """

        # --- helper: save debug if any detection is low-confidence ---
        def _maybe_save_lowconf_debug(pil_img: Image.Image, dets: List[DetectionDict], tag: str, thr: float = 0.89):
            if not Settings.STORE_FOR_TRAINING or not dets:
                return
            lows = [d for d in dets if float(d.get("conf", 0.0)) <= thr]
            if not lows:
                return
            try:
                out_dir = Settings.DEBUG_DIR / "training"
                out_dir_raw = out_dir / tag / "raw"
                out_dir_overlay = out_dir / tag / "overlay"
                os.makedirs(out_dir, exist_ok=True)
                os.makedirs(out_dir_raw, exist_ok=True)
                os.makedirs(out_dir_overlay, exist_ok=True)

                ts = time.strftime("%Y%m%d-%H%M%S") + f"_{int((time.time() % 1) * 1000):03d}"

                # overlay with low-conf boxes (two-line label: name + confidence)
                ov = pil_img.copy()
                draw = ImageDraw.Draw(ov)
                conf_line = "0"
                for d in lows:
                    x1, y1, x2, y2 = [int(v) for v in d.get("xyxy", (0, 0, 0, 0))]
                    name = str(d.get("name", "?"))
                    conf = float(d.get("conf", 0.0))
                    # box
                    draw.rectangle([x1, y1, x2, y2], outline=(255, 0, 0), width=2)
                    # two-line label
                    name_line = name
                    conf_line = f"{conf:.2f}"
                    pad, gap = 3, 2
                    try:
                        nb = draw.textbbox((0, 0), name_line)
                        cb = draw.textbbox((0, 0), conf_line)
                        w1, h1 = nb[2] - nb[0], nb[3] - nb[1]
                        w2, h2 = cb[2] - cb[0], cb[3] - cb[1]
                    except Exception:
                        w1 = int(draw.textlength(name_line)); h1 = 12
                        w2 = int(draw.textlength(conf_line)); h2 = 12
                    tw = max(w1, w2)
                    th = h1 + gap + h2
                    total_h = th + 2 * pad
                    # Prefer placing above the box; if no room, place just below top edge
                    if y1 - total_h - 2 >= 0:
                        by1 = y1 - total_h - 2
                    else:
                        by1 = y1 + 2
                    bx2 = x1 + tw + 2 * pad
                    draw.rectangle([x1, by1, bx2, by1 + total_h], fill=(255, 0, 0))
                    draw.text((x1 + pad, by1 + pad), name_line, fill=(255, 255, 255))
                    draw.text((x1 + pad, by1 + pad + h1 + gap), conf_line, fill=(255, 255, 255))

                raw_path = out_dir_raw / f"{tag}_{ts}_{conf_line}.png"
                pil_img.save(raw_path)
                ov_path = out_dir_overlay / f"{tag}_{ts}_{conf_line}.png"
                ov.save(ov_path)
                logger_uma.debug("saved low-conf training debug -> %s | %s", raw_path, ov_path)
            except Exception as e:
                logger_uma.debug("failed saving training debug: %s", e)

        # Capture FULL client area (not left half)
        img: Image.Image = self.screenshot()
        result, dets = detect_on_pil(img, imgsz=imgsz, conf=conf, iou=iou)

        _maybe_save_lowconf_debug(img, dets, tag=tag, thr=Settings.STORE_FOR_TRAINING_THRESHOLD)
        return img, result, dets


    def mouse_down(
        self,
        x: int,
        y: int,
        *,
        button: str = "left",
        use_organic_move: bool = True,
        jitter: int = 2,
    ) -> None:
        """
        Press and HOLD the mouse button at absolute screen coords.
        Caller must later invoke mouse_up(...) to release.
        """
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
        """Release a previously held mouse button at absolute screen coords."""
        pyautogui.mouseUp(x=int(x), y=int(y), button=button)

    # Aliases so higher-level game code can call whichever naming it expects
    def touch_down(self, x: int, y: int) -> None: self.mouse_down(x, y)
    def touch_up(self, x: int, y: int) -> None: self.mouse_up(x, y)
    def press_down(self, x: int, y: int) -> None: self.mouse_down(x, y)
    def press_up(self, x: int, y: int) -> None: self.mouse_up(x, y)
    def pointer_down(self, x: int, y: int) -> None: self.mouse_down(x, y)
    def pointer_up(self, x: int, y: int) -> None: self.mouse_up(x, y)

    def hold(self, x: int, y: int, seconds: float, *, jitter: int = 2) -> None:
        """
        Convenience: press, sleep, release at (x, y). Prefer using mouse_down/up
        directly when you need to poll while holding.
        """
        self.mouse_down(x, y, jitter=jitter)
        try:
            time.sleep(max(0.0, float(seconds)))
        finally:
            self.mouse_up(x, y)

    def hold_xyxy_center(
        self,
        xyxy: tuple[float, float, float, float],
        seconds: float,
        *,
        jitter: int = None,
        percentage_offset: float = 0.20,
    ) -> None:
        """
        Convenience: long-press the center of a local xyxy box for `seconds`.
        Useful for quick tests; real-time minigames should use mouse_down/up.
        """
        if jitter is None:
            jitter = calculate_jitter(xyxy, percentage_offset=percentage_offset)
        sx, sy = self.center_from_xyxy(xyxy)
        self.hold(sx, sy, seconds, jitter=jitter)
