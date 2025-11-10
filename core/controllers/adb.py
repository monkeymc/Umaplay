from __future__ import annotations

import io
import random
import re
import subprocess
import time
from typing import Optional, Tuple, Union

from PIL import Image

from core.controllers.base import IController, RegionXYWH
from core.types import XYXY


class ADBController(IController):
    """Controller that interacts with Android devices via ADB commands."""

    def __init__(
        self,
        device: Optional[str] = None,
        *,
        screen_width: Optional[int] = None,
        screen_height: Optional[int] = None,
        auto_connect: bool = True,
    ) -> None:
        super().__init__(window_title="", capture_client_only=False)
        self.device = (device or "").strip() or None
        self._screen_width = screen_width
        self._screen_height = screen_height

        if auto_connect and self.device:
            self._auto_connect_device(self.device)

        if self._screen_width is None or self._screen_height is None:
            self._detect_screen_size()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _adb_command(self, *args: str, text: bool = True) -> subprocess.CompletedProcess:
        cmd = ["adb"]
        if self.device:
            cmd.extend(["-s", self.device])
        cmd.extend(args)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=text,
                timeout=10,
                check=False,
            )
        except FileNotFoundError as exc:  # pragma: no cover - adb missing
            raise RuntimeError(
                "ADB executable not found. Install Android Platform Tools and ensure 'adb' is on PATH."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"ADB command timed out: {' '.join(cmd)}") from exc

        if result.returncode != 0:
            stderr = result.stderr if text else result.stderr.decode("utf-8", errors="ignore")
            raise RuntimeError(f"ADB command failed ({' '.join(cmd)}): {stderr.strip()}")

        return result

    def _auto_connect_device(self, device: str) -> None:
        try:
            listing = subprocess.run(
                ["adb", "devices"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except Exception:
            return

        if listing.returncode == 0 and device in listing.stdout:
            return

        try:
            subprocess.run(
                ["adb", "connect", device],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            time.sleep(0.5)
        except Exception:
            pass

    def _detect_screen_size(self) -> None:
        try:
            result = self._adb_command("shell", "wm", "size")
            for line in result.stdout.splitlines():
                if "size:" in line.lower() and "x" in line:
                    payload = line.split("size:")[-1].strip()
                    width_str, height_str = payload.split("x", 1)
                    self._screen_width = int(width_str.strip())
                    self._screen_height = int(height_str.strip())
                    return
        except Exception:
            pass

        try:
            result = self._adb_command("shell", "dumpsys", "display")
            match = re.search(r"init=(\d+)x(\d+)", result.stdout)
            if match:
                self._screen_width = int(match.group(1))
                self._screen_height = int(match.group(2))
                return
        except Exception:
            pass

        self._screen_width = self._screen_width or 1920
        self._screen_height = self._screen_height or 1080

    def _list_devices(self) -> list[str]:
        try:
            result = subprocess.run(
                ["adb", "devices"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode != 0:
                return []
            lines = result.stdout.strip().splitlines()[1:]
            return [line.split()[0] for line in lines if "device" in line and "offline" not in line]
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Abstract overrides
    # ------------------------------------------------------------------
    def _find_window(self):  # pragma: no cover - not applicable
        return None

    def _get_hwnd(self) -> Optional[int]:  # pragma: no cover - not applicable
        return None

    def _client_bbox_screen_xywh(self) -> Optional[RegionXYWH]:
        if self._screen_width and self._screen_height:
            return (0, 0, self._screen_width, self._screen_height)
        return None

    def focus(self) -> bool:
        devices = self._list_devices()
        if not devices:
            return False
        if not self.device:
            return True
        prefix = self.device.split(":", 1)[0]
        return any(dev == self.device or dev.startswith(prefix) for dev in devices)

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
        end_hold_range: Tuple[float, float] = (0.05, 0.12),
    ) -> bool:
        if not (self._screen_width and self._screen_height):
            return False

        width, height = self._screen_width, self._screen_height
        use_xyxy = isinstance(delta_or_xyxy, (tuple, list)) and len(delta_or_xyxy) == 4
        if use_xyxy:
            x1, y1, x2, y2 = map(float, delta_or_xyxy)  # type: ignore[arg-type]
            cx, cy = self.center_from_xyxy((x1, y1, x2, y2))
            pixels = max(min_px, int(abs(y2 - y1)))
            scroll_down = default_down
        else:
            cx, cy = width // 2, height // 2
            delta = int(delta_or_xyxy)
            scroll_down = delta < 0
            pixels = max(min_px, abs(delta))

        if invert:
            scroll_down = not scroll_down

        def _clamp_y(y: int) -> int:
            return max(10, min(height - 10, y))

        for _ in range(max(1, int(steps))):
            half = pixels // 2
            if scroll_down:
                y_start = _clamp_y(cy + half)
                y_end = _clamp_y(cy - half)
            else:
                y_start = _clamp_y(cy - half)
                y_end = _clamp_y(cy + half)

            jitter_val = int(jitter)
            xj = cx + (random.randint(-jitter_val, jitter_val) if jitter_val else 0)
            y0j = y_start + (random.randint(-jitter_val, jitter_val) if jitter_val else 0)
            y1j = y_end + (random.randint(-jitter_val, jitter_val) if jitter_val else 0)

            duration_ms = int(random.uniform(*duration_range) * 1000)
            self._adb_command(
                "shell",
                "input",
                "swipe",
                str(max(0, min(width - 1, int(xj)))),
                str(max(0, min(height - 1, int(y0j)))),
                str(max(0, min(width - 1, int(xj)))),
                str(max(0, min(height - 1, int(y1j)))),
                str(max(1, duration_ms)),
            )

            time.sleep(random.uniform(*end_hold_range))
            time.sleep(random.uniform(*pause_range))

        return True

    # ------------------------------------------------------------------
    # Capture & input overrides
    # ------------------------------------------------------------------
    def screenshot(self, region: Optional[RegionXYWH] = None) -> Image.Image:
        result = self._adb_command("exec-out", "screencap", "-p", text=False)
        img = Image.open(io.BytesIO(result.stdout))
        if img.mode != "RGB":
            img = img.convert("RGB")

        self._screen_width = img.width
        self._screen_height = img.height

        if region is not None:
            left, top, width, height = region
            img = img.crop((left, top, left + width, top + height))
            self._last_origin = (left, top)
            self._last_bbox = (left, top, width, height)
        else:
            self._last_origin = (0, 0)
            self._last_bbox = (0, 0, img.width, img.height)

        return img

    def move_to(self, x: int, y: int, duration: float = 0.15) -> None:  # pragma: no cover - no-op
        time.sleep(max(0.0, duration))

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
        tx = int(x)
        ty = int(y)
        if jitter and jitter > 0:
            tx += random.randint(-jitter, jitter)
            ty += random.randint(-jitter, jitter)

        if self._screen_width and self._screen_height:
            tx = max(0, min(self._screen_width - 1, tx))
            ty = max(0, min(self._screen_height - 1, ty))

        if use_organic_move:
            time.sleep(random.uniform(0.12, 0.22))
            time.sleep(random.uniform(0.03, 0.08))

        for _ in range(max(1, clicks)):
            self._adb_command("shell", "input", "tap", str(tx), str(ty))
            if clicks > 1:
                time.sleep(max(0.05, duration))

    def mouse_down(
        self,
        x: int,
        y: int,
        *,
        button: str = "left",
        use_organic_move: bool = True,
        jitter: int = 2,
    ) -> None:
        self.click(x, y, clicks=1, duration=0.1, use_organic_move=use_organic_move, jitter=jitter)

    def mouse_up(self, x: int, y: int, *, button: str = "left") -> None:  # pragma: no cover - no-op
        return None

    def hold(self, x: int, y: int, seconds: float, *, jitter: int = 2) -> None:
        tx = int(x)
        ty = int(y)
        if jitter and jitter > 0:
            tx += random.randint(-jitter, jitter)
            ty += random.randint(-jitter, jitter)

        if self._screen_width and self._screen_height:
            tx = max(0, min(self._screen_width - 1, tx))
            ty = max(0, min(self._screen_height - 1, ty))

        duration_ms = int(max(0.05, seconds) * 1000)
        self._adb_command(
            "shell",
            "input",
            "swipe",
            str(tx),
            str(ty),
            str(tx),
            str(ty),
            str(max(1, duration_ms)),
        )
