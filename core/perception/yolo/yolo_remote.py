# core/perception/yolo/yolo_remote.py
from __future__ import annotations

import base64
from typing import Any, Dict, List, Optional, Tuple
import cv2
import numpy as np
from PIL import Image, ImageDraw
import requests
from PIL import Image

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
            }
        )
        meta = data.get(
            "meta", {"backend": "remote", "imgsz": imgsz, "conf": conf, "iou": iou}
        )
        dets: List[DetectionDict] = data.get("dets", [])
        return meta, dets

    def detect_pil(
        self,
        pil_img: Image.Image,
        *,
        imgsz: Optional[int] = None,
        conf: Optional[float] = None,
        iou: Optional[float] = None,
    ) -> Tuple[Dict[str, Any], List[DetectionDict]]:
        bgr = pil_to_bgr(pil_img)
        return self.detect_bgr(bgr, imgsz=imgsz, conf=conf, iou=iou)

    @staticmethod
    def _maybe_store_debug(
        pil_img: Image.Image,
        dets: List[DetectionDict],
        *,
        tag: str,
        thr: float,
    ) -> None:
        import os, time

        if not Settings.STORE_FOR_TRAINING or not dets:
            return
        lows = [d for d in dets if float(d.get("conf", 0.0)) <= float(thr)]
        if not lows:
            return
        try:
            out_dir = Settings.DEBUG_DIR / "training"
            out_dir_raw = out_dir / tag / "raw"
            out_dir_overlay = out_dir / tag / "overlay"
            os.makedirs(out_dir_raw, exist_ok=True)
            os.makedirs(out_dir_overlay, exist_ok=True)

            ts = (
                time.strftime("%Y%m%d-%H%M%S") + f"_{int((time.time() % 1) * 1000):03d}"
            )

            ov = pil_img.copy()
            draw = ImageDraw.Draw(ov)
            conf_line = "0"
            for d in lows:
                x1, y1, x2, y2 = [int(v) for v in d.get("xyxy", (0, 0, 0, 0))]
                name = str(d.get("name", "?"))
                conf = float(d.get("conf", 0.0))
                conf_line = f"{conf:.2f}"

                draw.rectangle([x1, y1, x2, y2], outline=(255, 0, 0), width=2)
                # tiny label box
                name_line = name
                pad, gap = 3, 2
                try:
                    nb = draw.textbbox((0, 0), name_line)
                    cb = draw.textbbox((0, 0), conf_line)
                    w1, h1 = nb[2] - nb[0], nb[3] - nb[1]
                    w2, h2 = cb[2] - cb[0], cb[3] - cb[1]
                except Exception:
                    w1 = w2 = int(draw.textlength(name_line))
                    h1 = h2 = 12
                tw = max(w1, w2)
                th = h1 + gap + h2
                total_h = th + 2 * pad
                by1 = y1 - total_h - 2 if (y1 - total_h - 2) >= 0 else (y1 + 2)
                bx2 = x1 + tw + 2 * pad
                draw.rectangle([x1, by1, bx2, by1 + total_h], fill=(255, 0, 0))
                draw.text((x1 + pad, by1 + pad), name_line, fill=(255, 255, 255))
                draw.text(
                    (x1 + pad, by1 + pad + h1 + gap), conf_line, fill=(255, 255, 255)
                )

            raw_path = out_dir_raw / f"{tag}_{ts}_{conf_line}.png"
            pil_img.save(raw_path)
            ov_path = out_dir_overlay / f"{tag}_{ts}_{conf_line}.png"
            ov.save(ov_path)
            logger_uma.debug(
                "saved low-conf training debug -> %s | %s", raw_path, ov_path
            )
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
    ):
        if isinstance(self.ctrl, SteamController):
            img = self.ctrl.screenshot_left_half()
        else:
            img = self.ctrl.screenshot(region=region)

        meta, dets = self.detect_pil(img, imgsz=imgsz, conf=conf, iou=iou)

        if not Settings.USE_EXTERNAL_PROCESSOR:
            # otherwise it is already saved in external processor
            self._maybe_store_debug(
                img, dets, tag=tag, thr=Settings.STORE_FOR_TRAINING_THRESHOLD
            )
        return img, meta, dets
