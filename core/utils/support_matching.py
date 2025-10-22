from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

import cv2
import numpy as np

from core.perception.analyzers.matching.support_card_matcher import (
    SupportCardMatcher,
    TemplateEntry,
)
from core.settings import DEFAULT_SUPPORT_PRIORITY, Settings
from core.utils.event_processor import find_event_image_path
from core.utils.img import to_bgr
from core.utils.logger import logger_uma

SupportDeckEntry = Dict[str, Union[str, int]]
SupportPriority = Dict[str, Union[float, bool]]

_MATCHER_CACHE: Dict[Tuple[Tuple[str, str, str], ...], SupportCardMatcher] = {}


def _deck_key(deck: Iterable[SupportDeckEntry]) -> Tuple[Tuple[str, str, str], ...]:
    pairs: List[Tuple[str, str, str]] = []
    for card in deck:
        if not card:
            continue
        name = str(card.get("name", "") or "").strip()
        rarity = str(card.get("rarity", "") or "").strip()
        attribute = str(card.get("attribute", "") or "").strip()
        if not name:
            continue
        pairs.append((name, rarity, attribute))
    return tuple(pairs)


def _build_templates(deck_key: Tuple[Tuple[str, str, str], ...]) -> List[TemplateEntry]:
    templates: List[TemplateEntry] = []
    for name, rarity, attribute in deck_key:
        img_path = find_event_image_path("support_icon_training", name, rarity, attribute)
        if not img_path:
            logger_uma.debug(
                "[support_match] Missing asset for %s (%s/%s)", name, rarity, attribute
            )
            continue
        templates.append(
            TemplateEntry(
                name=name,
                path=str(img_path),
                metadata={
                    "name": name,
                    "rarity": rarity,
                    "attribute": attribute,
                },
            )
        )
    return templates


def get_support_matcher(
    deck: Iterable[SupportDeckEntry],
    *,
    min_confidence: float = 0.70,
) -> Optional[SupportCardMatcher]:
    deck_key = _deck_key(deck)
    if not deck_key:
        return None

    cached = _MATCHER_CACHE.get(deck_key)
    if cached is not None:
        return cached

    templates = _build_templates(deck_key)
    if not templates:
        return None

    matcher = SupportCardMatcher(templates, min_confidence=min_confidence)
    _MATCHER_CACHE[deck_key] = matcher
    logger_uma.info(
        "[support_match] Prepared matcher with %d templates", len(templates)
    )
    return matcher


def get_runtime_support_matcher(*, min_confidence: float = 0.70) -> Optional[SupportCardMatcher]:
    return get_support_matcher(Settings.SUPPORT_DECK, min_confidence=min_confidence)


def get_card_priority(name: str, rarity: str, attribute: str) -> SupportPriority:
    return Settings.SUPPORT_CARD_PRIORITIES.get(
        (name, rarity, attribute),
        Settings.default_support_priority(),
    )


def match_support_crop(
    crop_bgr: np.ndarray,
    *,
    matcher: Optional[SupportCardMatcher] = None,
    min_confidence: float = 0.70,
) -> Optional[Dict[str, Any]]:
    if crop_bgr is None or crop_bgr.size == 0:
        return None

    if matcher is None:
        matcher = get_runtime_support_matcher(min_confidence=min_confidence)
    if matcher is None:
        return None

    try:
        match = matcher.best_match(crop_bgr)
    except Exception as exc:
        logger_uma.debug("[support_match] matcher.best_match failed: %s", exc)
        return None

    if not match:
        return None

    meta = match.metadata or {}
    name = str(meta.get("name", "") or match.name)
    rarity = str(meta.get("rarity", "") or "")
    attribute = str(meta.get("attribute", "") or "")

    return {
        "name": name,
        "rarity": rarity,
        "attribute": attribute,
        "score": float(match.score),
        "tm_score": float(match.tm_score),
        "hash_score": float(match.hash_score),
        "hist_score": float(match.hist_score),
        "path": match.path,
    }


def classify_support_image(
    image: Union[str, np.ndarray],
    *,
    deck: Optional[Iterable[SupportDeckEntry]] = None,
    min_confidence: float = 0.70,
) -> Optional[Dict[str, Any]]:
    crop_bgr = to_bgr(image)
    matcher = get_support_matcher(deck or Settings.SUPPORT_DECK, min_confidence=min_confidence)
    if matcher is None:
        return None
    return match_support_crop(crop_bgr, matcher=matcher)
