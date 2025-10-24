# app.py
from __future__ import annotations

import base64
import io
from typing import Any, Dict, List, Literal, Optional, Tuple
from pathlib import Path

import cv2
import numpy as np
import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, validator
import time
from collections import OrderedDict
import hashlib

# Local OCR implementation (host has Paddle installed)
from core.perception.ocr.ocr_local import LocalOCREngine
from core.perception.yolo.yolo_local import LocalYOLOEngine
from PIL import Image, ImageOps
from core.settings import Settings
from core.perception.analyzers.matching.base import (
    PreparedTemplate,
    TemplateEntry,
    TemplateMatch,
    TemplateMatcherBase,
)

app = FastAPI()
engine = LocalOCREngine()  # load once; keeps models on CPU/GPU as configured

# run: uvicorn server.main_inference:app --host 0.0.0.0 --port 8001


@app.get("/health")
def health():
    return {
        "ok": True,
        "cuda": torch.cuda.is_available(),
        "template_cache": {
            "size": len(_TEMPLATE_CACHE),
            "hits": _TEMPLATE_CACHE_STATS["hits"],
            "misses": _TEMPLATE_CACHE_STATS["misses"],
        },
    }


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
    agent: Optional[str] = Field(None, description="Caller agent identifier for debug storage")
    tag: Optional[str] = Field(None, description="Detection tag used for debug capture folders")


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
        default_agent = (
            Settings.AGENT_NAME_NAV if nav_match else Settings.AGENT_NAME_URA
        )
        agent_name = (req.agent or default_agent or "").strip()
        default_tag = "yolo_endpoint"
        tag_name = (req.tag or default_tag or "").strip() or default_tag

        bgr, pil_img = _decode_b64_to_bgr(req.img)
        meta, dets = yolo_engine_req.detect_bgr(
            bgr,
            imgsz=req.imgsz,
            conf=req.conf,
            iou=req.iou,
            original_pil_img=pil_img,
            tag=tag_name,
            agent=agent_name,
        )
        # tiny debug: checksum of raw BGR bytes
        sha = hashlib.sha256(bgr.tobytes()).hexdigest()[:12]
        meta.update(
            {
                "shape": tuple(int(x) for x in bgr.shape),
                "checksum": sha,
                "weights": w_str,
                "agent": agent_name,
                "tag": tag_name,
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


class RegionPayload(BaseModel):
    img: str = Field(..., description="Base64-encoded region image (PNG/JPEG)")
    meta: Dict[str, Any] = Field(default_factory=dict)


class TemplateMatchOptions(BaseModel):
    tm_weight: float = 0.7
    hash_weight: float = 0.2
    hist_weight: float = 0.1
    tm_edge_weight: float = 0.30
    ms_min_scale: float = 0.60
    ms_max_scale: float = 1.40
    ms_steps: int = Field(9, ge=1, le=25)

    @validator("tm_weight", "hash_weight", "hist_weight", pre=True)
    def _ensure_float(cls, v: Any) -> float:
        return float(v)

    @validator("tm_edge_weight", "ms_min_scale", "ms_max_scale", pre=True)
    def _ensure_ratio(cls, v: Any) -> float:
        return float(v)


class TemplateDescriptor(BaseModel):
    id: str = Field(..., description="Logical identifier for the template")
    path: Optional[str] = Field(
        None, description="Filesystem path to template image available on server"
    )
    img: Optional[str] = Field(
        None, description="Inline base64 template override if path not provided"
    )
    hash_hex: Optional[str] = Field(None, description="Optional precomputed perceptual hash")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    name: Optional[str] = Field(None, description="Display name override for this template")
    public_path: Optional[str] = Field(
        None, description="Public asset path used by remote clients for reference"
    )
    size: Optional[Tuple[int, int]] = Field(
        None, description="Width/height of the template, if known"
    )


class TemplateMatchRequest(BaseModel):
    mode: Literal["support_cards", "race_banners", "generic"] = "generic"
    region: RegionPayload
    templates: List[TemplateDescriptor]
    options: Optional[TemplateMatchOptions] = None
    agent: Optional[str] = Field(
        None, description="Optional agent identifier for logging/debug captures"
    )

    @validator("templates")
    def _non_empty_templates(cls, v: List[TemplateDescriptor]) -> List[TemplateDescriptor]:
        if not v:
            raise ValueError("At least one template descriptor is required")
        return v


_TEMPLATE_CACHE: "OrderedDict[str, PreparedTemplate]" = OrderedDict()
_TEMPLATE_CACHE_STATS: Dict[str, int] = {"hits": 0, "misses": 0}
_TEMPLATE_CACHE_MAX = 256


def _template_cache_key(mode: str, descriptor: TemplateDescriptor) -> str:
    parts = [mode or "", descriptor.id]
    if descriptor.path:
        parts.append(f"path:{descriptor.path}")
    if descriptor.hash_hex:
        parts.append(f"hash:{descriptor.hash_hex}")
    if descriptor.img:
        digest = hashlib.sha256(descriptor.img.encode("utf-8")).hexdigest()[:16]
        parts.append(f"img:{digest}")
    return "|".join(parts)


def _pop_cache_if_needed() -> None:
    while len(_TEMPLATE_CACHE) > _TEMPLATE_CACHE_MAX:
        _TEMPLATE_CACHE.popitem(last=False)


def _decode_template_image(b64_img: Optional[str]) -> Optional[np.ndarray]:
    if not b64_img:
        return None
    bgr, _ = _decode_b64_to_bgr(b64_img)
    return bgr


def _prepare_template(
    matcher: TemplateMatcherBase,
    mode: str,
    descriptor: TemplateDescriptor,
) -> PreparedTemplate:
    key = _template_cache_key(mode, descriptor)
    cached = _TEMPLATE_CACHE.get(key)
    if cached is not None:
        _TEMPLATE_CACHE_STATS["hits"] += 1
        _TEMPLATE_CACHE.move_to_end(key)
        return cached

    image = _decode_template_image(descriptor.img)
    metadata = dict(descriptor.metadata or {})
    if descriptor.hash_hex and "hash_hex" not in metadata:
        metadata["hash_hex"] = descriptor.hash_hex
    if descriptor.name and "name" not in metadata:
        metadata["name"] = descriptor.name
    if descriptor.public_path and "public_path" not in metadata:
        metadata["public_path"] = descriptor.public_path
    if descriptor.size and "size" not in metadata:
        metadata["size"] = list(descriptor.size)

    # Resolve path: if public_path is provided, map it to server's local asset structure
    resolved_path = descriptor.path
    if descriptor.public_path and not image:
        # public_path format: /race/G2/All Comers-Y2-9-2.png
        # Map to server's web/public/ structure
        public_rel = descriptor.public_path.lstrip("/")
        resolved_path = str(Settings.ROOT_DIR / "web" / "public" / public_rel)

    entry = TemplateEntry(
        name=descriptor.id,
        path=resolved_path,
        image=image,
        metadata=metadata,
    )

    prepared = matcher._prepare_entry(entry)
    if prepared is None:
        raise HTTPException(
            status_code=404,
            detail=f"Template '{descriptor.id}' could not be loaded (path={resolved_path}, public_path={descriptor.public_path})",
        )

    _TEMPLATE_CACHE_STATS["misses"] += 1
    _TEMPLATE_CACHE[key] = prepared
    _pop_cache_if_needed()
    return prepared


@app.post("/template-match")
def template_match(req: TemplateMatchRequest) -> Dict[str, Any]:
    start = time.perf_counter()
    try:
        region_bgr, _ = _decode_b64_to_bgr(req.region.img)
        options = req.options or TemplateMatchOptions(ms_steps=9)
        matcher = TemplateMatcherBase(
            tm_weight=options.tm_weight,
            hash_weight=options.hash_weight,
            hist_weight=options.hist_weight,
            tm_edge_weight=options.tm_edge_weight,
            ms_min_scale=options.ms_min_scale,
            ms_max_scale=options.ms_max_scale,
            ms_steps=options.ms_steps,
        )

        region_features = matcher._prepare_region(region_bgr)

        prepared_templates: List[PreparedTemplate] = []
        for descriptor in req.templates:
            prepared = _prepare_template(matcher, req.mode, descriptor)
            prepared_templates.append(prepared)

        if not prepared_templates:
            raise HTTPException(status_code=404, detail="No templates available for matching")

        matches: List[TemplateMatch] = matcher._match_region(region_features, prepared_templates)

        elapsed_ms = (time.perf_counter() - start) * 1000.0
        cache_snapshot = {
            "size": len(_TEMPLATE_CACHE),
            "hits": _TEMPLATE_CACHE_STATS["hits"],
            "misses": _TEMPLATE_CACHE_STATS["misses"],
        }

        return {
            "meta": {
                "mode": req.mode,
                "agent": req.agent,
                "elapsed_ms": elapsed_ms,
                "templates_considered": len(prepared_templates),
                "cache": cache_snapshot,
            },
            "matches": [
                {
                    "id": m.name,
                    "score": m.score,
                    "tm_score": m.tm_score,
                    "hash_score": m.hash_score,
                    "hist_score": m.hist_score,
                    "metadata": m.metadata,
                }
                for m in matches
            ],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Template matching failure: {e}")
