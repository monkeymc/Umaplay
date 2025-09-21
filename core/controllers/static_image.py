
from typing import Optional, Tuple, Union
from PIL import Image
from core.types import XYXY
from core.utils.logger import logger_uma

from core.controllers.base import IController
class StaticImageController(IController):
    def __init__(self, pil_img: Image.Image):
        self._img = pil_img.convert("RGB")
        self.window_title = "JupyterStaticImage"
        self.capture_client_only = True
        self._last_origin = (0, 0)
        self._last_bbox = (0, 0, self._img.width, self._img.height)
    def focus(self) -> bool:
        return True
    def screenshot(self, region=None) -> Image.Image:
        return self._img
    
    def _client_bbox_screen_xywh(self):
        logger_uma.debug("Clicked")

    def _find_window(self):
        logger_uma.debug("Find Window")
    
    def _get_hwnd(self) -> Optional[int]:
        logger_uma.debug("_get_hwnd")

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
        logger_uma.debug("scroll")