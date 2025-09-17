# app.py
from __future__ import annotations

import base64
import hashlib
from typing import Any, Dict, List, Literal, Optional

import cv2
import numpy as np
import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, validator

# Local OCR implementation (host has Paddle installed)
from core.perception.ocr.ocr_local import LocalOCREngine
from core.perception.yolo.yolo_local import LocalYOLOEngine

app = FastAPI()
engine = LocalOCREngine()  # load once; keeps models on CPU/GPU as configured


@app.get("/health")
def health():
    return {"ok": True, "cuda": torch.cuda.is_available()}


# -------- OCR endpoint --------
class OCRRequest(BaseModel):
    mode: Literal["raw", "text", "digits", "batch_text", "batch_digits"] = Field(..., description="OCR operation")
    img: Optional[str] = Field(None, description="Base64-encoded single image (PNG/JPEG)")
    imgs: Optional[List[str]] = Field(None, description="Base64-encoded images for batch ops")
    joiner: str = " "
    min_conf: float = 0.2

    @validator("min_conf")
    def _clip_min_conf(cls, v: float) -> float:
        # keep a sane range
        return max(0.0, min(1.0, float(v)))



def _decode_b64_to_bgr(b64: str) -> np.ndarray:
    try:
        raw = base64.b64decode(b64, validate=True)
        arr = np.frombuffer(raw, dtype=np.uint8)
        # Force 3-channel BGR to avoid BGRA or grayscale surprises.
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("cv2.imdecode failed")
        return img
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid base64 image: {e}") from e


@app.post("/ocr")
def ocr(req: OCRRequest) -> Dict[str, Any]:
    try:
        if req.mode in ("raw", "text", "digits"):
            if not req.img:
                raise HTTPException(status_code=400, detail="Field 'img' is required for this mode.")
            img = _decode_b64_to_bgr(req.img)
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
                raise HTTPException(status_code=400, detail="Field 'imgs' is required for this mode.")
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

class YoloRequest(BaseModel):
    img: str = Field(..., description="Base64-encoded PNG/JPEG image (BGR compatible)")
    imgsz: int = Field(640, ge=64, le=3072)
    conf: float = Field(0.25, ge=0.0, le=1.0)
    iou: float = Field(0.45, ge=0.0, le=1.0)

@app.post("/yolo")
def yolo_detect(req: YoloRequest):
    try:
        bgr = _decode_b64_to_bgr(req.img)
        meta, dets = yolo_engine.detect_bgr(bgr, imgsz=req.imgsz, conf=req.conf, iou=req.iou)
         # tiny debug: checksum of raw BGR bytes
        sha = hashlib.sha256(bgr.tobytes()).hexdigest()[:12]
        meta.update({
            "shape": tuple(int(x) for x in bgr.shape),
            "checksum": sha,
            "weights": getattr(yolo_engine, "weights_path", "unknown"),
            "ultralytics": getattr(type(yolo_engine.model), "__module__", "ultralytics"),
        })
        return {"meta": meta, "dets": dets}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"YOLO failure: {e}")