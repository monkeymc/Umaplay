# core/perception/yolo/interface.py
from __future__ import annotations
from typing import Any, Dict, List, Optional, Protocol, Tuple, runtime_checkable
from PIL import Image
from core.controllers.base import IController, RegionXYWH
from core.types import DetectionDict


@runtime_checkable
class IDetector(Protocol):
    """
    Interface for YOLO-like detectors. Implementations may run locally (Ultralytics)
    or remotely (HTTP microservice).
    """

    ctrl: Optional[IController]

    def detect_bgr(
        self,
        bgr: Any,
        *,
        imgsz: Optional[int] = None,
        conf: Optional[float] = None,
        iou: Optional[float] = None,
    ) -> Tuple[Dict[str, Any], List[DetectionDict]]:
        """Run detection on a BGR image and return (meta, dets)."""
        raise NotImplementedError

    def detect_pil(
        self,
        pil_img: Image.Image,
        *,
        imgsz: Optional[int] = None,
        conf: Optional[float] = None,
        iou: Optional[float] = None,
    ) -> Tuple[Dict[str, Any], List[DetectionDict]]:
        """Run detection on a PIL image and return (meta, dets)."""
        raise NotImplementedError

    def recognize(
        self,
        *,
        region: Optional[RegionXYWH] = None,
        imgsz: Optional[int] = None,
        conf: Optional[float] = None,
        iou: Optional[float] = None,
        tag: str = "general",
    ) -> Tuple[Image.Image, Dict[str, Any], List[DetectionDict]]:
        """
        Capture via controller and run detection.
        Returns (captured_image, meta, dets).
        """
        raise NotImplementedError
