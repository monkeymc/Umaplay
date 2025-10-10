# app.py
from __future__ import annotations

import base64
import hashlib
import io
from typing import Any, Dict, List, Literal, Optional, Tuple
from pathlib import Path

import cv2
import numpy as np
import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, validator

# Local OCR implementation (host has Paddle installed)
from core.perception.ocr.ocr_local import LocalOCREngine
from core.perception.yolo.yolo_local import LocalYOLOEngine
from PIL import Image, ImageOps
from core.settings import Settings

app = FastAPI()
engine = LocalOCREngine()  # load once; keeps models on CPU/GPU as configured

# run: uvicorn server.main_inference:app --host 0.0.0.0 --port 8001


@app.get("/health")
def health():
    return {"ok": True, "cuda": torch.cuda.is_available()}


# -------- OCR endpoint --------
class OCRRequest(BaseModel):
    mode: Literal["raw", "text", "digits", "batch_text", "batch_digits"] = Field(
        ..., description="OCR operation"
    )
    img: Optional[str] = Field(
        None, description="Base64-encoded single image (PNG/JPEG)"
    )
    imgs: Optional[List[str]] = Field(
        None, description="Base64-encoded images for batch ops"
    )
    joiner: str = " "
    min_conf: float = 0.2

    @validator("min_conf")
    def _clip_min_conf(cls, v: float) -> float:
        # keep a sane range
        return max(0.0, min(1.0, float(v)))


def _decode_b64_to_bgr(b64: str) -> Tuple[np.ndarray, Image.Image]:
    """
    Decode a base64-encoded image (optionally a data: URI) and return:
      • bgr: NumPy array in 3-channel BGR (uint8), suitable for OpenCV.
      • pil: PIL.Image in RGB, EXIF-orientation corrected.
    """
    try:
        # Allow 'data:image/png;base64,...' and stray whitespace/newlines
        if "base64," in b64:
            b64 = b64.split("base64,", 1)[1]
        b64 = b64.strip()

        try:
            raw = base64.b64decode(b64, validate=True)
        except Exception:
            # Some encoders insert newlines or lack padding; be permissive as a fallback.
            raw = base64.b64decode(b64, validate=False)

        # Decode with PIL first to retain EXIF and correct orientation, then force RGB.
        bio = io.BytesIO(raw)
        pil_img = Image.open(bio)
        pil_img = ImageOps.exif_transpose(pil_img).convert("RGB")

        # Convert to BGR for OpenCV consumers (guaranteed 3 channels).
        rgb = np.array(pil_img)  # H×W×3, uint8
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        return bgr, pil_img
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid base64 image: {e}") from e


@app.post("/ocr")
def ocr(req: OCRRequest) -> Dict[str, Any]:
    try:
        if req.mode in ("raw", "text", "digits"):
            if not req.img:
                raise HTTPException(
                    status_code=400, detail="Field 'img' is required for this mode."
                )
            img, pil_img = _decode_b64_to_bgr(req.img)
            if req.mode == "raw":
                data = engine.raw(img)
            elif req.mode == "text":
                data = engine.text(img, joiner=req.joiner, min_conf=req.min_conf)
            else:
                data = engine.digits(img)
            sha = hashlib.sha256(img.tobytes()).hexdigest()[:12]
            return {"mode": req.mode, "data": data, "meta": {"checksum": sha}}

        elif req.mode in ("batch_text", "batch_digits"):
            if not req.imgs:
                raise HTTPException(
                    status_code=400, detail="Field 'imgs' is required for this mode."
                )
            imgs = [_decode_b64_to_bgr(b) for b in req.imgs]
            if req.mode == "batch_text":
                data = engine.batch_text(imgs, joiner=req.joiner, min_conf=req.min_conf)
            else:
                data = engine.batch_digits(imgs)
            return {"mode": req.mode, "data": data}

        else:
            raise HTTPException(status_code=400, detail="Unsupported mode.")
    except HTTPException:
        raise
    except Exception as e:
        # Keep a short message; logs on server should have the stacktrace
        raise HTTPException(status_code=500, detail=f"OCR failure: {e}")


# Instantiate one YOLO engine for the service (no controller needed here)
yolo_engine = LocalYOLOEngine(ctrl=None)
yolo_engine_nav = LocalYOLOEngine(ctrl=None, weights=Settings.YOLO_WEIGHTS_NAV)


class YoloRequest(BaseModel):
    img: str = Field(..., description="Base64-encoded PNG/JPEG image (BGR compatible)")
    imgsz: int = Field(832, ge=64, le=3072)
    conf: float = Field(0.66, ge=0.0, le=1.0)
    iou: float = Field(0.45, ge=0.0, le=1.0)
    weights_path: Optional[str] = None


@app.post("/yolo")
def yolo_detect(req: YoloRequest):
    try:
        # Normalize incoming weights selection (string) and compare against server's NAV path
        w_in = req.weights_path or ""
        try:
            w_str = str(w_in)
        except Exception:
            w_str = ""
        try:
            nav_str = str(Settings.YOLO_WEIGHTS_NAV)
            nav_match = (w_str == nav_str) or (Path(w_str).name == Path(nav_str).name)
        except Exception:
            nav_match = False

        yolo_engine_req = yolo_engine_nav if nav_match else yolo_engine
        bgr, pil_img = _decode_b64_to_bgr(req.img)
        meta, dets = yolo_engine_req.detect_bgr(
            bgr,
            imgsz=req.imgsz,
            conf=req.conf,
            iou=req.iou,
            original_pil_img=pil_img,
            tag="yolo_endpoint",
        )
        # tiny debug: checksum of raw BGR bytes
        sha = hashlib.sha256(bgr.tobytes()).hexdigest()[:12]
        meta.update(
            {
                "shape": tuple(int(x) for x in bgr.shape),
                "checksum": sha,
                "weights": w_str,
                "ultralytics": getattr(
                    type(yolo_engine_req.model), "__module__", "ultralytics"
                ),
            }
        )
        return {"meta": meta, "dets": dets}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"YOLO failure: {e}")
