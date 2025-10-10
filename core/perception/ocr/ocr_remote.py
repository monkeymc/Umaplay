# core/perception/ocr/ocr_remote.py
from __future__ import annotations

import base64
import hashlib
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
import requests
from core.perception.ocr.interface import OCRInterface
from core.utils.img import to_bgr  # if you prefer, you can inline conversion here
from core.utils.logger import logger_uma
from PIL import Image


def _prepare_bgr3(img: Any) -> np.ndarray:
    if isinstance(img, Image.Image):
        bgr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    elif isinstance(img, np.ndarray):
        bgr = img
    else:
        from core.utils.img import to_bgr

        bgr = to_bgr(img)
    if bgr.ndim == 2:
        bgr = cv2.cvtColor(bgr, cv2.COLOR_GRAY2BGR)
    elif bgr.shape[2] == 4:
        bgr = cv2.cvtColor(bgr, cv2.COLOR_BGRA2BGR)
    return bgr


def _encode_image_to_base64(img: Any, *, fmt: str = ".png") -> str:
    bgr = _prepare_bgr3(img)
    ok, buf = cv2.imencode(fmt, bgr)
    if not ok:
        raise ValueError("Failed to encode image")
    return base64.b64encode(buf.tobytes()).decode("ascii")


def _local_checksum(img: Any) -> str:
    bgr = _prepare_bgr3(img)
    return hashlib.sha256(bgr.tobytes()).hexdigest()[:12]


class RemoteOCREngine(OCRInterface):
    """
    HTTP client that calls a backend OCR service (FastAPI) at <base_url>/ocr.
    Keeps the same method signatures as the local engine.
    """

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 30.0,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()

    def _post(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/ocr"
        r = self.session.post(url, json=payload, timeout=self.timeout)
        try:
            r.raise_for_status()
        except Exception:
            logger_uma.exception(
                "RemoteOCR request failed: %s %s", r.status_code, r.text[:2000]
            )
            raise
        data = r.json()
        if "data" not in data:
            raise ValueError(f"Unexpected response shape: {data}")
        return data

    # ---- Methods ----
    def raw(self, img: Any) -> Dict[str, Any]:
        img64 = _encode_image_to_base64(img)
        return self._post({"mode": "raw", "img": img64})["data"]

    def text(self, img: Any, joiner: str = " ", min_conf: float = 0.2) -> str:
        img64 = _encode_image_to_base64(img)
        return self._post(
            {
                "mode": "text",
                "img": img64,
                "joiner": joiner,
                "min_conf": float(min_conf),
            }
        )["data"]

    def digits(self, img: Any) -> int:
        img64 = _encode_image_to_base64(img)
        return int(self._post({"mode": "digits", "img": img64})["data"])

    def batch_text(
        self, imgs: List[Any], *, joiner: str = " ", min_conf: float = 0.2
    ) -> List[str]:
        imgs64 = [_encode_image_to_base64(im) for im in imgs]
        return list(
            self._post(
                {
                    "mode": "batch_text",
                    "imgs": imgs64,
                    "joiner": joiner,
                    "min_conf": float(min_conf),
                }
            )["data"]
        )

    def batch_digits(self, imgs: List[Any]) -> List[str]:
        imgs64 = [_encode_image_to_base64(im) for im in imgs]
        return list(self._post({"mode": "batch_digits", "imgs": imgs64})["data"])
