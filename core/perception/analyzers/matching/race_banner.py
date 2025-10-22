# core/perception/analyzers/race_banner.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np
from PIL import Image
from imagehash import hex_to_hash, phash

from core.perception.analyzers.matching.base import (
    PreparedTemplate,
)
from core.perception.analyzers.matching.base import TemplateMatch, TemplateMatcherBase
from core.perception.analyzers.matching.support_card_matcher import TemplateEntry
from core.utils.img import to_bgr
from core.utils.logger import logger_uma
from core.utils.race_index import RaceIndex, canonicalize_race_name


@dataclass
class BannerMatch:
    name: str
    score: float
    tm_score: float
    hash_score: float
    hist_score: float
    path: str


class RaceBannerMatcher(TemplateMatcherBase):
    """Helper that scores race cards against stored banner templates."""

    def __init__(
        self,
        *,
        roi: Tuple[float, float, float, float] = (0.05, 0.55, 0.08, 0.92),
        tm_weight: float = 0.7,
        hash_weight: float = 0.2,
        hist_weight: float = 0.1,
        # New: fusion and multiscale controls for template matching
        tm_edge_weight: float = 0.30,
        ms_min_scale: float = 0.60,
        ms_max_scale: float = 1.40,
        ms_steps: int = 9,
    ) -> None:
        super().__init__(
            tm_weight=tm_weight,
            hash_weight=hash_weight,
            hist_weight=hist_weight,
            tm_edge_weight=tm_edge_weight,
            ms_min_scale=ms_min_scale,
            ms_max_scale=ms_max_scale,
            ms_steps=ms_steps,
        )
        self.default_roi = roi
        self._cache: Dict[str, PreparedTemplate] = {}

    def best_match(
        self,
        card_img,
        candidates: Optional[Sequence[str]] = None,
    ) -> Optional[BannerMatch]:
        matches = self.match(card_img, candidates=candidates)
        return matches[0] if matches else None

    def match(
        self,
        card_img,
        candidates: Optional[Sequence[str]] = None,
    ) -> List[BannerMatch]:
        banner_region = to_bgr(card_img)
        cropped = self._extract_roi(banner_region, self.default_roi)
        region = self._prepare_region(cropped)

        names = list(candidates) if candidates else [meta["name"] for meta in RaceIndex.all_banner_templates().values()]

        prepared_templates: List[PreparedTemplate] = []
        for race_name in names:
            tmpl = self._resolve_template(race_name)
            if tmpl is not None:
                prepared_templates.append(tmpl)

        template_matches: List[TemplateMatch] = super()._match_region(
            region,
            prepared_templates,
            candidates=names if candidates else None,
        )

        matches = [
            BannerMatch(
                name=m.name,
                score=m.score,
                tm_score=m.tm_score,
                hash_score=m.hash_score,
                hist_score=m.hist_score,
                path=m.path,
            )
            for m in template_matches
        ]

        if len(matches) >= 2 and (matches[0].score - matches[1].score) < 0.05:
            logger_uma.info(
                "[race_banner] Ambiguous banner match: top='%s'(%.3f) vs second='%s'(%.3f)",
                matches[0].name,
                matches[0].score,
                matches[1].name,
                matches[1].score,
            )

        return matches

    def _resolve_template(self, race_name: str) -> Optional[PreparedTemplate]:
        canon = canonicalize_race_name(race_name)
        if not canon:
            return None
        if canon in self._cache:
            return self._cache[canon]

        meta = RaceIndex.banner_template(race_name)
        if not meta:
            return None

        try:
            entry = TemplateEntry(
                name=meta["name"],
                path=meta["path"],
                metadata={
                    "hash_hex": meta.get("hash_hex"),
                    "canonical": canon,
                },
            )
            prepared = self._prepare_entry(entry)
            if prepared is None:
                return None
            self._cache[canon] = prepared
            return prepared
        except Exception as e:
            logger_uma.debug("[race_banner] Failed to load template '%s': %s", race_name, e)
            return None

    @staticmethod
    def _extract_roi(
        bgr: np.ndarray, roi: Tuple[float, float, float, float]
    ) -> np.ndarray:
        top, bottom, left, right = roi
        h, w = bgr.shape[:2]
        y1 = max(0, min(h, int(round(h * top))))
        y2 = max(y1 + 1, min(h, int(round(h * bottom))))
        x1 = max(0, min(w, int(round(w * left))))
        x2 = max(x1 + 1, min(w, int(round(w * right))))
        return bgr[y1:y2, x1:x2]

    @staticmethod
    def prepare_gray_edges(img_bgr: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Backward compatibility shim for legacy call sites."""
        return TemplateMatcherBase.prepare_gray_edges(img_bgr)
