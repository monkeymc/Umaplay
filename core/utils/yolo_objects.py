# core/utils/yolo_objects.py
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from PIL import Image
from core.controllers.base import IController
from core.perception.yolo.interface import IDetector
from core.types import XYXY, DetectionDict

def collect(yolo_engine: IDetector, *, imgsz=832, conf=0.51, iou=0.45, tag="general") -> Tuple[Image.Image, List[DetectionDict]]:
    img, _, dets = yolo_engine.recognize(imgsz=imgsz, conf=conf, iou=iou, tag=tag)
    return img, dets

# ---------- Basic geometry helpers ----------

def center(xyxy: XYXY) -> Tuple[float, float]:
    x1, y1, x2, y2 = xyxy
    return (0.5 * (x1 + x2), 0.5 * (y1 + y2))

def center_x(xyxy: XYXY) -> float:
    x1, _, x2, _ = xyxy
    return 0.5 * (x1 + x2)

def center_y(xyxy: XYXY) -> float:
    _, y1, _, y2 = xyxy
    return 0.5 * (y1 + y2)

def bbox_area(xyxy: XYXY) -> float:
    x1, y1, x2, y2 = xyxy
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)

def inside(inner: XYXY, outer: XYXY, pad: int = 0) -> bool:
    ix1, iy1, ix2, iy2 = inner
    ox1, oy1, ox2, oy2 = outer
    return (ix1 >= ox1 - pad and iy1 >= oy1 - pad and ix2 <= ox2 + pad and iy2 <= oy2 + pad)


# ---------- Detection filters & finders ----------

def find(dets: List[DetectionDict], name: str | Sequence[str], *, conf_min: float = 0.0) -> List[DetectionDict]:
    """
    Return detections whose `name` is in the provided name(s) and conf >= conf_min.
    `name` may be a single string or a list/tuple of names.
    """
    names: set[str] = {name} if isinstance(name, str) else set(str(n) for n in name)
    out: List[DetectionDict] = []
    for d in dets:
        if str(d.get("name")) in names:
            c = float(d.get("conf", 1.0))
            if c >= conf_min:
                out.append(d)
    return out

def filter_by_classes(dets: List[DetectionDict], classes: Sequence[str], *, conf_min: float = 0.0) -> List[DetectionDict]:
    return find(dets, classes, conf_min=conf_min)

def bottom_most(dets: List[DetectionDict]) -> Optional[DetectionDict]:
    if not dets:
        return None
    # prefer larger center-Y (lower on screen); tie-break by left-most (smaller center-X)
    return max(dets, key=lambda d: (center_y(d["xyxy"]), -center_x(d["xyxy"])))


def yolo_signature(dets: List[DetectionDict]) -> List[Tuple[str, int, int]]:
    """
    Summarize the scene for early-stop:
    [(name, cx_8px, cy_8px), ...] sorted.
    """
    sig = []
    for d in dets:
        name = str(d.get("name"))
        x1, y1, x2, y2 = d.get("xyxy", (0, 0, 0, 0))
        cx = int((x1 + x2) / 2) // 8
        cy = int((y1 + y2) / 2) // 8
        sig.append((name, cx, cy))
    sig.sort()
    return sig
