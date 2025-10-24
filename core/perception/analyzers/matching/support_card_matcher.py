from __future__ import annotations

from typing import Any, Iterable, List, Optional, Sequence

from core.perception.analyzers.matching.base import (
    PreparedTemplate,
    TemplateEntry,
    TemplateMatch,
    TemplateMatcherBase,
)
from core.utils.img import to_bgr


class SupportCardMatcher(TemplateMatcherBase):
    def __init__(
        self,
        templates: Iterable[TemplateEntry],
        *,
        tm_weight: float = 0.7,
        hash_weight: float = 0.2,
        hist_weight: float = 0.1,
        tm_edge_weight: float = 0.30,
        ms_min_scale: float = 0.60,
        ms_max_scale: float = 1.40,
        ms_steps: int = 9,
        min_confidence: float = 0.0,
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
        self.min_confidence = float(min_confidence)
        self._templates: List[PreparedTemplate] = []
        self.set_templates(templates)

    def set_templates(self, templates: Iterable[TemplateEntry]) -> None:
        self._templates = self.prepare_templates(templates)

    @property
    def templates(self) -> List[PreparedTemplate]:
        return list(self._templates)

    def match(
        self,
        card_img: Any,
        *,
        candidates: Optional[Sequence[str]] = None,
    ) -> List[TemplateMatch]:
        if not self._templates:
            return []
        region_bgr = to_bgr(card_img)
        region = self._prepare_region(region_bgr)
        return self._match_region(region, self._templates, candidates=candidates)

    def best_match(
        self,
        card_img: Any,
        *,
        candidates: Optional[Sequence[str]] = None,
    ) -> Optional[TemplateMatch]:
        matches = self.match(card_img, candidates=candidates)
        if not matches:
            return None
        top = matches[0]
        if self.min_confidence > 0.0 and top.score < self.min_confidence:
            return None
        return top
