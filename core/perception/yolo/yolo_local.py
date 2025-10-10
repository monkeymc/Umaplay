# core/perception/yolo/yolo_local.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from PIL import Image, ImageDraw

from ultralytics import YOLO

from core.perception.yolo.interface import IDetector
from core.controllers.base import IController, RegionXYWH
from core.controllers.steam import SteamController
from core.settings import Settings
from core.types import DetectionDict
from core.utils.img import pil_to_bgr
from core.utils.logger import logger_uma


class LocalYOLOEngine(IDetector):
    """
    Ultralytics-backed detector. Keeps API parity with the interface and mirrors
    your previous helpers, but encapsulated in a class.
    """

    def __init__(
        self,
        ctrl: Optional[IController] = None,
        *,
        weights: Optional[str] = None,
        use_gpu: Optional[bool] = None,
    ):
        self.ctrl = ctrl
        self.weights_path = str(weights or Settings.YOLO_WEIGHTS)
        self.use_gpu = Settings.USE_GPU if use_gpu is None else bool(use_gpu)

        logger_uma.info(f"Loading YOLO weights from: {self.weights_path}")
        self.model = YOLO(self.weights_path)
        if self.use_gpu:
            try:
                self.model.to("cuda:0")
            except Exception as e:
                logger_uma.error(f"Couldn't set YOLO model to CUDA: {e}")

    # ---------- internals ----------
    @staticmethod
    def _extract_dets(res, conf_min: float = 0.25) -> List[DetectionDict]:
        boxes = getattr(res, "boxes", None)
        if boxes is None or len(boxes) == 0:
            return []

        names = (
            res.names
            if isinstance(res.names, dict)
            else {i: n for i, n in enumerate(res.names)}
        )
        xyxy = boxes.xyxy.cpu().numpy()
        cls = boxes.cls.cpu().numpy().astype(int)
        conf = boxes.conf.cpu().numpy()

        out: List[DetectionDict] = []
        for i in range(len(cls)):
            if conf[i] < conf_min:
                continue
            out.append(
                {
                    "idx": i,
                    "name": names.get(int(cls[i]), str(cls[i])),
                    "conf": float(conf[i]),
                    "xyxy": tuple(map(float, xyxy[i])),
                }
            )
        return out

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

    # ---------- public API ----------
    def detect_bgr(
        self,
        bgr: np.ndarray,
        *,
        imgsz: Optional[int] = None,
        conf: Optional[float] = None,
        iou: Optional[float] = None,
        original_pil_img=None,
        tag="general",
    ) -> Tuple[Dict[str, Any], List[DetectionDict]]:
        imgsz = imgsz if imgsz is not None else Settings.YOLO_IMGSZ
        conf = conf if conf is not None else Settings.YOLO_CONF
        iou = iou if iou is not None else Settings.YOLO_IOU

        res_list = self.model.predict(
            source=bgr, imgsz=imgsz, conf=conf, iou=iou, verbose=False
        )
        result = res_list[0]
        dets = self._extract_dets(result, conf_min=conf)

        if original_pil_img is not None:
            self._maybe_store_debug(
                original_pil_img,
                dets,
                tag=tag,
                thr=Settings.STORE_FOR_TRAINING_THRESHOLD,
            )

        meta = {"names": result.names, "imgsz": imgsz, "conf": conf, "iou": iou}
        return meta, dets

    def detect_pil(
        self,
        pil_img: Image.Image,
        *,
        imgsz: Optional[int] = None,
        conf: Optional[float] = None,
        iou: Optional[float] = None,
        tag="general",
    ) -> Tuple[Dict[str, Any], List[DetectionDict]]:
        bgr = pil_to_bgr(pil_img)

        meta, dets = self.detect_bgr(bgr, imgsz=imgsz, conf=conf, iou=iou)
        self._maybe_store_debug(
            pil_img, dets, tag=tag, thr=Settings.STORE_FOR_TRAINING_THRESHOLD
        )
        return meta, dets

    def recognize(
        self,
        *,
        region: Optional[RegionXYWH] = None,
        imgsz: Optional[int] = None,
        conf: Optional[float] = None,
        iou: Optional[float] = None,
        tag: str = "general",
    ) -> Tuple[Image.Image, Dict[str, Any], List[DetectionDict]]:
        if self.ctrl is None:
            raise RuntimeError(
                "LocalYOLOEngine.recognize() requires a controller injected in the constructor."
            )

        if isinstance(self.ctrl, SteamController):
            img = self.ctrl.screenshot_left_half()
        else:
            img = self.ctrl.screenshot(region=region)

        meta, dets = self.detect_pil(img, imgsz=imgsz, conf=conf, iou=iou)
        return img, meta, dets
