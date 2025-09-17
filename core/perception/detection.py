# core/perception/detection.py

from typing import List, Tuple, Optional

from PIL import Image, ImageDraw

from core.controllers.base import IController, RegionXYWH
from core.controllers.steam import SteamController
from core.settings import Settings
from core.types import DetectionDict

import numpy as np
from ultralytics import YOLO

from core.utils.img import pil_to_bgr
from core.utils.logger import logger_uma

# Lazily-initialized global (keeps call sites simple)
_YOLO_MODEL: Optional[YOLO] = None


def get_model(weights=None) -> YOLO:
    """Return a ready YOLO model (load lazily on first use)."""
    global _YOLO_MODEL
    if _YOLO_MODEL is not None:
        return _YOLO_MODEL

    weights_path = str(weights or Settings.YOLO_WEIGHTS)
    logger_uma.info(f"Loading YOLO weights from: {weights_path}")
    _YOLO_MODEL = YOLO(weights_path)

    if Settings.USE_GPU:
        try:
            _YOLO_MODEL.to("cuda:0")
        except Exception as e:
            logger_uma.error(f"Couldn't set YOLO model to CUDA: {e}")
    return _YOLO_MODEL


def extract_dets(res, conf_min: float = 0.25) -> List[DetectionDict]:
    """
    Flatten a single Ultralytics `Results` into a list of normalized dicts:
    {name, conf, xyxy, idx}. Filters by conf_min.
    """
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


def detect_on_bgr(
    bgr: np.ndarray,
    *,
    imgsz: Optional[int] = None,
    conf: Optional[float] = None,
    iou: Optional[float] = None,
) -> Tuple[object, List[DetectionDict]]:
    """
    Run YOLO on an OpenCV BGR image and return:
      (yolo_result, det_list[DetectionDict])

    Controller-specific capture is intentionally NOT here; call this from your
    SteamController helper (e.g., controller grabs an image, then passes BGR here).
    """
    # Defaults from Settings unless explicitly overridden
    imgsz = imgsz if imgsz is not None else Settings.YOLO_IMGSZ
    conf = conf if conf is not None else Settings.YOLO_CONF
    iou = iou if iou is not None else Settings.YOLO_IOU

    model = get_model()
    res_list = model.predict(source=bgr, imgsz=imgsz, conf=conf, iou=iou, verbose=False)
    result = res_list[0]
    dets = extract_dets(result, conf_min=conf)

    return result, dets


def detect_on_pil(
    pil_img: Image.Image,
    *,
    imgsz: Optional[int] = None,
    conf: Optional[float] = None,
    iou: Optional[float] = None,
) -> Tuple[object, List[DetectionDict]]:
    """
    Run YOLO on a PIL Image and return:
      (yolo_result, det_list[DetectionDict])
    """
    bgr = pil_to_bgr(pil_img)
    return detect_on_bgr(bgr, imgsz=imgsz, conf=conf, iou=iou)


def recognize(
    ctrl: IController,
    *,
    region: Optional[RegionXYWH] = None,
    imgsz: Optional[int] = None,
    conf: Optional[float] = None,
    iou: Optional[float] = None,
    tag: str = "general",
) -> Tuple[Image.Image, object, List[DetectionDict]]:
    """
    Capture via controller and run YOLO detection.
    Returns (image, yolo_result, dets).
    """
    if isinstance(ctrl, SteamController):
        img = ctrl.screenshot_left_half()
    else:
        img = ctrl.screenshot(region=region)

    result, dets = detect_on_pil(img, imgsz=imgsz, conf=conf, iou=iou)
    _maybe_store_debug(img, dets, tag=tag, thr=Settings.STORE_FOR_TRAINING_THRESHOLD)
    return img, result, dets


def _maybe_store_debug(
    pil_img: Image.Image,
    dets: List[DetectionDict],
    *,
    tag: str,
    thr: float,
) -> None:
    """Optional training dumps, kept here to keep controllers clean."""
    import os
    import time
    from core.utils.logger import logger_uma

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

        ts = time.strftime("%Y%m%d-%H%M%S") + f"_{int((time.time() % 1) * 1000):03d}"

        ov = pil_img.copy()
        draw = ImageDraw.Draw(ov)
        conf_line = "0"
        for d in lows:
            x1, y1, x2, y2 = [int(v) for v in d.get("xyxy", (0, 0, 0, 0))]
            name = str(d.get("name", "?"))
            conf = float(d.get("conf", 0.0))
            conf_line = f"{conf:.2f}"

            draw.rectangle([x1, y1, x2, y2], outline=(255, 0, 0), width=2)
            name_line = name
            pad, gap = 3, 2
            try:
                nb = draw.textbbox((0, 0), name_line)
                cb = draw.textbbox((0, 0), conf_line)
                w1, h1 = nb[2] - nb[0], nb[3] - nb[1]
                w2, h2 = cb[2] - cb[0], cb[3] - cb[1]
            except Exception:
                w1 = int(draw.textlength(name_line))
                h1 = 12
                w2 = int(draw.textlength(conf_line))
                h2 = 12
            tw = max(w1, w2)
            th = h1 + gap + h2
            total_h = th + 2 * pad
            by1 = y1 - total_h - 2 if (y1 - total_h - 2) >= 0 else (y1 + 2)
            bx2 = x1 + tw + 2 * pad
            draw.rectangle([x1, by1, bx2, by1 + total_h], fill=(255, 0, 0))
            draw.text((x1 + pad, by1 + pad), name_line, fill=(255, 255, 255))
            draw.text((x1 + pad, by1 + pad + h1 + gap), conf_line, fill=(255, 255, 255))

        raw_path = out_dir_raw / f"{tag}_{ts}_{conf_line}.png"
        pil_img.save(raw_path)
        ov_path = out_dir_overlay / f"{tag}_{ts}_{conf_line}.png"
        ov.save(ov_path)
        logger_uma.debug("saved low-conf training debug -> %s | %s", raw_path, ov_path)
    except Exception as e:
        from core.utils.logger import logger_uma

        logger_uma.debug("failed saving training debug: %s", e)
