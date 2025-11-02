# core/perception/yolo/yolo_remote.py
from __future__ import annotations

import base64
from typing import Any, Dict, List, Optional, Tuple
import cv2
import numpy as np
from PIL import Image
import requests

from core.perception.yolo.interface import IDetector
from core.controllers.base import IController, RegionXYWH
from core.controllers.steam import SteamController
from core.settings import Settings
from core.types import DetectionDict
from core.utils.img import pil_to_bgr, to_bgr
from core.utils.logger import logger_uma


def _encode_image_to_base64(img: Any, *, fmt: str = ".png") -> str:
    """
    Encode to base64 as a true 3-channel BGR PNG.
    - If PIL.Image: convert RGB->BGR.
    - If ndarray: assume it's already BGR (do NOT swap again).
    - Normalize grayscale/BGRA to BGR.
    """
    if isinstance(img, Image.Image):
        bgr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    elif isinstance(img, np.ndarray):
        bgr = img
    else:
        # last-resort fallback (path/bytes); OK to keep if you truly need it
        bgr = to_bgr(img)

    if bgr.ndim == 2:
        bgr = cv2.cvtColor(bgr, cv2.COLOR_GRAY2BGR)
    elif bgr.shape[2] == 4:
        bgr = cv2.cvtColor(bgr, cv2.COLOR_BGRA2BGR)

    ok, buf = cv2.imencode(fmt, bgr)
    if not ok:
        raise ValueError("Failed to encode image")
    return base64.b64encode(buf.tobytes()).decode("ascii")


class RemoteYOLOEngine(IDetector):
    """
    Lightweight client that calls a FastAPI /yolo service.
    No Ultralytics or CUDA required on the VM.
    """

    def __init__(
        self,
        ctrl: IController,
        base_url: str,
        *,
        timeout: float = 30.0,
        session: Optional[requests.Session] = None,
        weights: str | None = None,
    ):
        self.ctrl = ctrl
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()
        # Ensure JSON-serializable type (avoid WindowsPath issues)
        self.weights = str(weights) if weights is not None else None

    def _post(self, payload: Dict[str, any]) -> Dict[str, any]:
        r = self.session.post(
            f"{self.base_url}/yolo", json=payload, timeout=self.timeout
        )
        r.raise_for_status()
        return r.json()

    # ---------- public API ----------
    def detect_bgr(
        self,
        bgr: np.ndarray,
        *,
        imgsz: Optional[int] = None,
        conf: Optional[float] = None,
        iou: Optional[float] = None,
        tag: str = "general",
        agent: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], List[DetectionDict]]:
        imgsz = imgsz if imgsz is not None else Settings.YOLO_IMGSZ
        conf = conf if conf is not None else Settings.YOLO_CONF
        iou = iou if iou is not None else Settings.YOLO_IOU

        img64 = _encode_image_to_base64(bgr)
        data = self._post(
            {
                "img": img64,
                "imgsz": imgsz,
                "conf": conf,
                "iou": iou,
                "weights_path": self.weights,
                "tag": tag,
                "agent": agent,
            }
        )
        meta = data.get(
            "meta", {"backend": "remote", "imgsz": imgsz, "conf": conf, "iou": iou}
        )
        dets: List[DetectionDict] = data.get("dets", [])
        if tag:
            meta.setdefault("tag", tag)
        if agent:
            meta.setdefault("agent", agent)
        return meta, dets

    def detect_pil(
        self,
        pil_img: Image.Image,
        *,
        imgsz: Optional[int] = None,
        conf: Optional[float] = None,
        iou: Optional[float] = None,
        tag: str = "general",
        agent: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], List[DetectionDict]]:
        bgr = pil_to_bgr(pil_img)
        return self.detect_bgr(
            bgr,
            imgsz=imgsz,
            conf=conf,
            iou=iou,
            tag=tag,
            agent=agent,
        )

    @staticmethod
    def _maybe_store_debug(
        pil_img: Image.Image,
        dets: List[DetectionDict],
        *,
        tag: str,
        thr: float,
        agent: Optional[str] = None,
    ) -> None:
        import os, time

        if not Settings.STORE_FOR_TRAINING or not dets:
            return
        lows = [d for d in dets if float(d.get("conf", 0.0)) <= float(thr)]
        if not lows:
            return
        try:
            agent_segment = (agent or "").strip()
            base_dir = Settings.DEBUG_DIR / agent_segment if agent_segment else Settings.DEBUG_DIR
            out_dir_raw = base_dir / tag / "raw"
            os.makedirs(out_dir_raw, exist_ok=True)

            ts = (
                time.strftime("%Y%m%d-%H%M%S") + f"_{int((time.time() % 1) * 1000):03d}"
            )

            lowest = min(lows, key=lambda d: float(d.get("conf", 0.0)))
            conf_line = f"{float(lowest.get('conf', 0.0)):.2f}"
            raw_name = str(lowest.get("name", "unknown")).strip()
            class_segment = "".join(
                ch if ch.isalnum() or ch in "-_" else "-" for ch in raw_name
            ) or "unknown"

            raw_path = out_dir_raw / f"{tag}_{ts}_{class_segment}_{conf_line}.png"
            pil_img.save(raw_path)
            logger_uma.debug("saved low-conf training debug -> %s", raw_path)
        except Exception as e:
            logger_uma.debug("failed saving training debug: %s", e)

    def recognize(
        self,
        *,
        region: Optional[RegionXYWH] = None,
        imgsz: Optional[int] = None,
        conf: Optional[float] = None,
        iou: Optional[float] = None,
        tag: str = "general",
        agent: Optional[str] = None,
    ):
        if self.ctrl is None:
            raise RuntimeError(
                "RemoteYOLOEngine.recognize() requires a controller injected in the constructor."
            )

        if isinstance(self.ctrl, SteamController):
            img = self.ctrl.screenshot_left_half()
        else:
            img = self.ctrl.screenshot(region=region)

        meta, dets = self.detect_pil(
            img,
            imgsz=imgsz,
            conf=conf,
            iou=iou,
            tag=tag,
            agent=agent,
        )

        if not Settings.USE_EXTERNAL_PROCESSOR:
            # otherwise it is already saved in external processor
            self._maybe_store_debug(
                img,
                dets,
                tag=tag,
                thr=Settings.STORE_FOR_TRAINING_THRESHOLD,
                agent=agent,
            )

        return img, meta, dets
