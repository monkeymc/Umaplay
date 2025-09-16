# core/utils/img.py
from __future__ import annotations
from typing import Any, Iterable

import cv2
import numpy as np
from PIL import Image


def pil_to_bgr(pil_im: Image.Image) -> np.ndarray:
    """Convert a PIL RGB image to an OpenCV BGR array."""
    return cv2.cvtColor(np.array(pil_im), cv2.COLOR_RGB2BGR)


def bgr_to_pil(bgr: np.ndarray) -> Image.Image:
    """Convert an OpenCV BGR array to a PIL RGB image."""
    return Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))


def shrink(im_bgr: np.ndarray, max_w: int = 800) -> np.ndarray:
    """Shrink BGR image to a max width while preserving aspect ratio."""
    h, w = im_bgr.shape[:2]
    if w <= max_w:
        return im_bgr
    scale = max_w / float(w)
    return cv2.resize(
        im_bgr,
        (int(w * scale), int(h * scale)),
        interpolation=cv2.INTER_AREA,
    )

def to_bgr(img: Any) -> np.ndarray:
    """
    Accept a file path, PIL.Image, or numpy array (RGB/BGR/RGBA/BGRA/GRAY) and
    return a BGR uint8 array.
    """
    if isinstance(img, str):
        arr = cv2.imread(img, cv2.IMREAD_COLOR)
        if arr is None:
            raise FileNotFoundError(f"Could not read image: {img}")
        return arr

    if isinstance(img, Image.Image):
        arr = np.array(img)
    elif isinstance(img, np.ndarray):
        arr = img
    else:
        raise TypeError(f"Unsupported image type: {type(img)}")

    if arr.ndim == 2:
        return cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)

    if arr.ndim == 3 and arr.shape[2] == 4:
        # Try RGBA→BGR first; if that fails assume BGRA
        try:
            return cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
        except cv2.error:
            return cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)

    if arr.ndim == 3 and arr.shape[2] == 3:
        # Try RGB→BGR; if it fails we assume it's already BGR
        try:
            return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        except cv2.error:
            return arr

    raise ValueError(f"Unrecognized image array shape: {arr.shape}")

def draw_overlay(img_bgr: np.ndarray, items: Iterable) -> np.ndarray:
    """Draw light-weight boxes for visualization."""
    out = img_bgr.copy()
    for box, txt, score in items:
        try:
            pts = np.array(box, dtype=np.int32).reshape(-1, 1, 2)
            cv2.polylines(out, [pts], True, (0, 255, 0), 1)
        except Exception:
            # Skip malformed boxes; keep going
            continue
    return out
