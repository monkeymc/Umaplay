# core/controllers/steam.py
import random
import time
from typing import Optional, Tuple, List

import pyautogui
import pygetwindow as gw
from PIL import ImageGrab, Image

# Requires pywin32
import win32con
import win32gui

from core.controllers.base import IController, RegionXYWH
from core.perception.detection import detect_on_pil
from core.settings import Settings
from core.types import DetectionDict
from core.utils.logger import logger_uma
from core.utils.geometry import calculate_jitter
from typing import List, Dict
import os, time
from PIL import ImageDraw

class SteamController(IController):
    """
    - focus(): restores & foregrounds the target window.
    - screenshot(): by default captures the window's *client area* only (much faster than full screen).
      Keeps track of the last capture origin so you can translate local coords -> screen coords.
    """

    def __init__(self, window_title: str = "Umamusume", capture_client_only: bool = True):
        self.window_title = window_title
        self.capture_client_only = capture_client_only
        self._last_origin: Tuple[int, int] = (0, 0)     # (left, top) of last screenshot in screen coords
        self._last_bbox:   Tuple[int, int, int, int] = (0, 0, 0, 0)  # (L, T, W, H)

    # --- window discovery ---

    def _find_window(self):
        wins = [w for w in gw.getWindowsWithTitle(self.window_title) if w.title.strip() == self.window_title]
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
                w.minimize(); time.sleep(0.1); w.restore(); time.sleep(0.2)

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
        if not hwnd or not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
            return None

        # Client rect is (0,0)-(w,h) in client coords
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

        Args:
            x, y: Screen coordinates to click.
            clicks: Number of clicks to perform.
            duration: Mouse move duration when not using organic move.
            use_organic_move: If True, use small random move duration and micro-sleep.
            jitter: ±pixels of random jitter added to the final target (default 0).
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
        jitter: int = None,  # None is AUTO if use_organic_move is True
        percentage_offset=0.2
    ) -> None:
        """
        Compute the center of an xyxy RECT **in last-screenshot/local coords**,
        translate it to SCREEN coords, and click there.

        Args:
            xyxy: (x1, y1, x2, y2) in *local* (last screenshot) coordinates.
            clicks: Number of clicks to perform.
            move_duration: Mouse move duration used when use_organic_move=False.
            use_organic_move: If True, use organic move in underlying click().
            jitter: ±pixels of random jitter applied around the center (default 2).
        """

        if jitter is None:
            jitter = calculate_jitter(xyxy, percentage_offset=percentage_offset)
        sx, sy = self.center_from_xyxy(xyxy)  # -> SCREEN coords
        self.click(
            sx, sy,
            clicks=clicks,
            duration=move_duration,
            use_organic_move=use_organic_move,
            jitter=jitter,
        )

    def scroll(self, amount: int) -> None:
        pyautogui.scroll(amount)

    def resolution(self) -> Tuple[int, int]:
        res = pyautogui.size()
        return res.width, res.height

    def move_xyxy_center(
        self,
        xyxy: tuple[float, float, float, float],
        *,
        jitter: Optional[int] = None,          # None -> auto via calculate_jitter
        percentage_offset: float = 0.20,       # how far from center auto-jitter may roam
        duration_range: tuple[float, float] = (0.12, 0.22),
        micro_pause_range: tuple[float, float] = (0.02, 0.06),
    ) -> None:
        """
        Move the cursor (no click) to the center of an xyxy RECT given in *last
        screenshot/local* coordinates. Applies small randomization to look natural.

        Args:
            xyxy: (x1, y1, x2, y2) in local coords (last screenshot space).
            jitter: ±pixels random offset; if None, auto-computed from box size.
            percentage_offset: size factor used for auto-jitter computation.
            duration_range: random move duration range for a natural feel.
            micro_pause_range: short pause after moving to mimic human motion.
        """
        if jitter is None:
            jitter = calculate_jitter(xyxy, percentage_offset=percentage_offset)

        sx, sy = self.center_from_xyxy(xyxy)  # convert local center -> screen coords
        if jitter and jitter > 0:
            sx += random.randint(-jitter, jitter)
            sy += random.randint(-jitter, jitter)

        self.move_to(sx, sy, duration=random.uniform(*duration_range))
        time.sleep(random.uniform(*micro_pause_range))

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

    # --- expose client bbox publicly ---
    def client_bbox(self) -> Optional[RegionXYWH]:
        """(left, top, width, height) of client area in screen coords, or None."""
        return self._client_bbox_screen_xywh()

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

    # helpers for YOLO boxes (xyxy in LAST screenshot space)
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
        tag = "general"
    ) -> Tuple[Image.Image, object, List[DetectionDict]]:
        """
        Capture the LEFT half of the client window and run YOLO on it.
        Returns:
            (left_img [PIL.Image], yolo_result, dets [List[DetectionDict]])
        Notes:
            - Thresholds default to Settings.* when None.
            - Uses the cached YOLO model inside core.perception.detection.
        """
        # --- helper: save debug if any detection is low-confidence ---
        def _maybe_save_lowconf_debug(pil_img, dets, tag: str, thr: float = 0.89):
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
                ts = time.strftime("%Y%m%d-%H%M%S") + f"_{int((time.time()%1)*1000):03d}"
                
                # overlay with low-conf boxes
                ov = pil_img.copy()
                draw = ImageDraw.Draw(ov)
                conf_line = '0'
                for d in lows:
                    x1, y1, x2, y2 = [int(v) for v in d.get("xyxy", (0,0,0,0))]
                    name = str(d.get("name","?"))
                    conf = float(d.get("conf", 0.0))
                    # box
                    draw.rectangle([x1, y1, x2, y2], outline=(255, 0, 0), width=2)
                    # two-line label: name (top) and confidence (below)
                    name_line = name
                    conf_line = f"{conf:.2f}"
                    pad, gap = 3, 2
                    try:
                        # Prefer accurate text metrics when available
                        nb = draw.textbbox((0, 0), name_line)
                        cb = draw.textbbox((0, 0), conf_line)
                        w1, h1 = nb[2] - nb[0], nb[3] - nb[1]
                        w2, h2 = cb[2] - cb[0], cb[3] - cb[1]
                    except Exception:
                        # Fallback: width via textlength, heuristic height
                        w1 = int(draw.textlength(name_line)); h1 = 12
                        w2 = int(draw.textlength(conf_line)); h2 = 12
                    tw = max(w1, w2)
                    th = h1 + gap + h2

                    # Place label above the box if there's room; otherwise just below the top edge
                    total_h = th + 2 * pad
                    if y1 - total_h - 2 >= 0:
                        by1 = y1 - total_h - 2
                    else:
                        by1 = y1 + 2
                    bx2 = x1 + tw + 2 * pad

                    draw.rectangle([x1, by1, bx2, by1 + total_h], fill=(255, 0, 0))
                    draw.text((x1 + pad, by1 + pad), name_line, fill=(255, 255, 255))
                    draw.text((x1 + pad, by1 + pad + h1 + gap), conf_line, fill=(255, 255, 255))
                
                # raw
                raw_path =  out_dir_raw / f"{tag}_{ts}_{conf_line}.png"
                pil_img.save(raw_path)
                ov_path = out_dir_overlay / f"{tag}_{ts}_{conf_line}.png"
                ov.save(ov_path)
                logger_uma.debug("[yolo] saved low-conf training debug -> %s | %s", raw_path, ov_path)
            except Exception as e:
                logger_uma.debug("failed saving training debug: %s", e)

        # Initial capture; we'll REUSE and REFRESH this across iterations
        left_img: Image.Image = self.screenshot_left_half()
        result, dets = detect_on_pil(left_img, imgsz=imgsz, conf=conf, iou=iou)

        if Settings.DEBUG:
            _maybe_save_lowconf_debug(left_img, dets, tag=tag, thr=Settings.STORE_FOR_TRAINING_THRESHOLD)
        return left_img, result, dets
    
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
