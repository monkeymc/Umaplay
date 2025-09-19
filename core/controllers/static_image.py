
from PIL import Image
class StaticImageController:
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