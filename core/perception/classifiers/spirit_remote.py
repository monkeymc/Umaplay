from __future__ import annotations

import base64
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
import requests
from PIL import Image

from core.utils.img import to_bgr
from core.utils.logger import logger_uma


def _prepare_bgr3(img: Any) -> np.ndarray:
    if isinstance(img, Image.Image):
        bgr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    elif isinstance(img, np.ndarray):
        bgr = img
    else:
        bgr = to_bgr(img)

    if bgr.ndim == 2:
        bgr = cv2.cvtColor(bgr, cv2.COLOR_GRAY2BGR)
    elif bgr.shape[2] == 4:
        bgr = cv2.cvtColor(bgr, cv2.COLOR_BGRA2BGR)
    return bgr


def _encode_image_to_base64(img: Any, fmt: str = ".png") -> str:
    bgr = _prepare_bgr3(img)
    ok, buf = cv2.imencode(fmt, bgr)
    if not ok:
        raise ValueError("Failed to encode image for spirit classification")
    return base64.b64encode(buf.tobytes()).decode("ascii")


class RemoteUnityCupSpiritClassifier:
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
        self._classes: List[str] = []
        self._img_size: Optional[Tuple[int, int]] = None

    def _post(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/classify/spirit"
        response = self.session.post(url, json=payload, timeout=self.timeout)
        try:
            response.raise_for_status()
        except Exception:
            logger_uma.exception(
                "Remote spirit classifier request failed: %s %s",
                response.status_code,
                response.text[:2000],
            )
            raise
        data = response.json()
        classes = data.get("classes")
        if isinstance(classes, list):
            self._classes = [str(c) for c in classes]
        img_size_raw = data.get("img_size")
        if isinstance(img_size_raw, (list, tuple)) and len(img_size_raw) == 2:
            try:
                self._img_size = (int(img_size_raw[0]), int(img_size_raw[1]))
            except Exception:
                pass
        return data

    def _classify(self, img: Any, threshold: float) -> Dict[str, Any]:
        img64 = _encode_image_to_base64(img)
        return self._post({"img": img64, "threshold": float(threshold)})

    def predict(self, img: Any) -> Dict[str, Any]:
        return self._classify(img, threshold=0.0)

    def predict_label(self, img: Any, threshold: float = 0.0) -> str:
        result = self._classify(img, threshold=threshold)
        label = str(result.get("pred_label", "unknown"))
        confidence = float(result.get("confidence", 0.0))
        if threshold > 0.0 and confidence < threshold:
            return "unknown"
        return label

    def classes_list(self) -> List[str]:
        return list(self._classes)

    @property
    def img_size(self) -> Optional[Tuple[int, int]]:
        return self._img_size
