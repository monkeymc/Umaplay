from __future__ import annotations

import base64
import io
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

import numpy as np
import requests
from PIL import Image

from core.settings import Settings
from core.utils.logger import logger_uma


def _ensure_bgr_array(img: Any) -> np.ndarray:
    """Return a 3-channel uint8 BGR array from np.ndarray, PIL image, or path."""
    if isinstance(img, np.ndarray):
        arr = img
    elif isinstance(img, Image.Image):
        arr = np.array(img.convert("RGB"))[:, :, ::-1]
    elif isinstance(img, str):
        with Image.open(img) as im:
            arr = np.array(im.convert("RGB"))[:, :, ::-1]
    else:
        raise TypeError(f"Unsupported image type: {type(img)}")

    if arr.ndim == 2:
        arr = np.stack([arr, arr, arr], axis=-1)
    if arr.ndim != 3 or arr.shape[2] not in (3, 4):
        raise ValueError(f"Unrecognized image array shape: {arr.shape}")
    if arr.shape[2] == 4:
        arr = arr[:, :, :3]
    if arr.dtype != np.uint8:
        arr = arr.astype(np.uint8, copy=False)
    return arr


def _encode_bgr_to_base64_png(bgr: np.ndarray) -> str:
    rgb = bgr[:, :, ::-1]
    image = Image.fromarray(rgb)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


@dataclass
class RemoteTemplateDescriptor:
    id: str
    path: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    hash_hex: Optional[str] = None
    img: Optional[str] = None


@dataclass
class RemoteTemplateMatch:
    name: str
    score: float
    tm_score: float
    hash_score: float
    hist_score: float
    metadata: Dict[str, Any]
    path: str = ""


_DEFAULT_OPTIONS: Dict[str, float] = {
    "tm_weight": 0.7,
    "hash_weight": 0.2,
    "hist_weight": 0.1,
    "tm_edge_weight": 0.30,
    "ms_min_scale": 0.60,
    "ms_max_scale": 1.40,
    "ms_steps": 9,
}


class RemoteTemplateMatcherBase:
    MODE = "template_match"

    def __init__(
        self,
        templates: Iterable[Dict[str, Any]],
        *,
        min_confidence: float = 0.0,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        session: Optional[requests.Session] = None,
        options: Optional[Dict[str, float]] = None,
    ) -> None:
        self.base_url = (base_url or Settings.EXTERNAL_PROCESSOR_URL).rstrip("/")
        self.timeout = timeout if timeout is not None else Settings.TEMPLATE_MATCH_TIMEOUT
        self.session = session or requests.Session()
        self.min_confidence = float(min_confidence)
        merged = dict(_DEFAULT_OPTIONS)
        if options:
            merged.update({k: float(v) for k, v in options.items()})
        self._options = merged
        self.mode = self.MODE
        self._templates: List[RemoteTemplateDescriptor] = []
        self.set_templates(templates)

    def set_templates(self, templates: Iterable[Dict[str, Any]]) -> None:
        self._templates = [
            RemoteTemplateDescriptor(
                id=str(spec.get("id") or spec.get("name")),
                path=spec.get("path"),
                metadata=dict(spec.get("metadata") or {}),
                hash_hex=spec.get("hash_hex"),
                img=spec.get("img"),
            )
            for spec in templates
            if spec.get("id") or spec.get("name")
        ]

    @property
    def templates(self) -> List[RemoteTemplateDescriptor]:
        return list(self._templates)

    def match(
        self,
        card_img: Any,
        *,
        candidates: Optional[Sequence[str]] = None,
    ) -> List[RemoteTemplateMatch]:
        if not self._templates:
            return []

        try:
            region_bgr = _ensure_bgr_array(card_img)
        except Exception as exc:
            logger_uma.debug("[remote_template] Failed to prepare region: %s", exc)
            return []

        selected = self._select_templates(candidates)
        if not selected:
            return []

        payload = {
            "mode": self.mode,
            "agent": Settings.AGENT_NAME_NAV,
            "region": {
                "img": _encode_bgr_to_base64_png(region_bgr),
                "meta": {"shape": list(region_bgr.shape[:2])},
            },
            "templates": [
                {
                    "id": tmpl.id,
                    "path": tmpl.path,
                    "metadata": tmpl.metadata,
                    "hash_hex": tmpl.hash_hex,
                    "img": tmpl.img,
                }
                for tmpl in selected
            ],
            "options": self._options,
        }

        try:
            response = self.session.post(
                f"{self.base_url}/template-match",
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            logger_uma.debug("[remote_template] Request failed: %s", exc)
            return []

        matches = data.get("matches", []) or []
        out: List[RemoteTemplateMatch] = []
        for m in matches:
            meta = dict(m.get("metadata") or {})
            match = RemoteTemplateMatch(
                name=str(m.get("id") or meta.get("name") or ""),
                score=float(m.get("score", 0.0)),
                tm_score=float(m.get("tm_score", 0.0)),
                hash_score=float(m.get("hash_score", 0.0)),
                hist_score=float(m.get("hist_score", 0.0)),
                metadata=meta,
                path=str(m.get("path") or meta.get("path") or ""),
            )
            out.append(match)

        out.sort(key=lambda m: m.score, reverse=True)
        return out

    def best_match(
        self,
        card_img: Any,
        *,
        candidates: Optional[Sequence[str]] = None,
    ) -> Optional[RemoteTemplateMatch]:
        matches = self.match(card_img, candidates=candidates)
        if not matches:
            return None
        top = matches[0]
        if self.min_confidence > 0.0 and top.score < self.min_confidence:
            return None
        return top

    def _select_templates(
        self, candidates: Optional[Sequence[str]]
    ) -> List[RemoteTemplateDescriptor]:
        if not candidates:
            return list(self._templates)
        wanted = {str(c).strip() for c in candidates if c}
        selected = [
            tmpl
            for tmpl in self._templates
            if tmpl.id in wanted or tmpl.metadata.get("name") in wanted
        ]
        return selected or list(self._templates)


class RemoteSupportCardMatcher(RemoteTemplateMatcherBase):
    MODE = "support_cards"


class RemoteRaceBannerMatcher(RemoteTemplateMatcherBase):
    MODE = "race_banners"
