from __future__ import annotations
from typing import Tuple, Union
from PIL import Image


def xyxy_int(xyxy) -> Tuple[int, int, int, int]:
    """Round and cast an XYXY box to ints."""
    x1, y1, x2, y2 = xyxy
    return int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2))


def crop_pil(
    img: Image.Image, xyxy, pad: Union[int, Tuple[int, int]] = 0
) -> Image.Image:
    """
    Safe crop for PIL images with optional integer padding.
    Pads/clamps inside image bounds and guarantees non-empty crop.
    """
    W, H = img.size
    x1, y1, x2, y2 = xyxy_int(xyxy)
    if isinstance(pad, int):
        px, py = pad, pad
    else:
        px, py = pad
    x1 = max(0, x1 - px)
    y1 = max(0, y1 - py)
    x2 = min(W, x2 + px)
    y2 = min(H, y2 + py)
    if x2 <= x1:
        x2 = min(W, x1 + 1)
    if y2 <= y1:
        y2 = min(H, y1 + 1)
    return img.crop((x1, y1, x2, y2))


def xyxy_wh(
    xyxy: Tuple[float, float, float, float],
    *,
    as_int: bool = True,
    clamp_non_negative: bool = True,
) -> Tuple[int, int] | Tuple[float, float]:
    """
    Return (width, height) for an (x1, y1, x2, y2) box.

    Args:
        xyxy: (x1, y1, x2, y2), typically detector output in local/screen coords.
        as_int: If True (default), round to ints; else return floats.
        clamp_non_negative: If True (default), clamp negatives to 0.

    Notes:
        Assumes the common convention where width = x2 - x1 and height = y2 - y1.
        If your coordinates are inclusive, adjust upstream as needed.
    """
    x1, y1, x2, y2 = xyxy
    w = x2 - x1
    h = y2 - y1
    if clamp_non_negative:
        w = max(0.0, w)
        h = max(0.0, h)
    if as_int:
        return int(round(w)), int(round(h))
    return w, h


def calculate_jitter(xyxy: Tuple[float, float, float, float], percentage_offset=0.25):
    w, h = xyxy_wh(xyxy)
    min_side = min(w, h)
    return int(percentage_offset * min_side)
