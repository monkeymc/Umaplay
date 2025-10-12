# core/perception/analyzers/race_banner.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import cv2
import numpy as np
from PIL import Image
from imagehash import hex_to_hash, phash

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


class RaceBannerMatcher:
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
        self.default_roi = roi
        self.tm_weight = float(tm_weight)
        self.hash_weight = float(hash_weight)
        self.hist_weight = float(hist_weight)
        total = max(self.tm_weight + self.hash_weight + self.hist_weight, 1e-9)
        self.tm_weight /= total
        self.hash_weight /= total
        self.hist_weight /= total
        self._cache: Dict[str, Dict[str, object]] = {}
        # Store multiscale/edge parameters
        self.tm_edge_weight = float(max(0.0, min(1.0, tm_edge_weight)))
        self.tm_gray_weight = 1.0 - self.tm_edge_weight
        self.ms_min_scale = float(ms_min_scale)
        self.ms_max_scale = float(ms_max_scale)
        self.ms_steps = int(max(1, ms_steps))

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

        pil_region = Image.fromarray(cv2.cvtColor(banner_region, cv2.COLOR_BGR2RGB))
        region_hash = phash(pil_region)
        region_hist = self._histogram(banner_region)

        names = list(candidates) if candidates else [meta["name"] for meta in RaceIndex.all_banner_templates().values()]

        matches: List[BannerMatch] = []
        for race_name in names:
            meta = self._resolve_template(race_name)
            if not meta:
                continue

            tmpl_bgr = meta["bgr"]
            tmpl_hash = meta["hash"]
            tmpl_hist = meta["hist"]

            tm_score = self._template_score(banner_region, tmpl_bgr)
            hash_score = self._hash_score(region_hash, tmpl_hash)
            hist_score = self._hist_compare(region_hist, tmpl_hist)

            final_score = (
                self.tm_weight * tm_score
                + self.hash_weight * hash_score
                + self.hist_weight * hist_score
            )

            matches.append(
                BannerMatch(
                    name=meta["name"],
                    score=float(final_score),
                    tm_score=float(tm_score),
                    hash_score=float(hash_score),
                    hist_score=float(hist_score),
                    path=meta["path"],
                )
            )

        matches.sort(key=lambda m: m.score, reverse=True)

        if len(matches) >= 2 and (matches[0].score - matches[1].score) < 0.05:
            logger_uma.info(
                "[race_banner] Ambiguous banner match: top='%s'(%.3f) vs second='%s'(%.3f)",
                matches[0].name,
                matches[0].score,
                matches[1].name,
                matches[1].score,
            )

        return matches

    def _resolve_template(self, race_name: str) -> Optional[Dict[str, object]]:
        canon = canonicalize_race_name(race_name)
        if not canon:
            return None
        if canon in self._cache:
            return self._cache[canon]

        meta = RaceIndex.banner_template(race_name)
        if not meta:
            return None

        try:
            tmpl_bgr = to_bgr(meta["path"])
            # Precompute grayscale and edges for faster matching
            tmpl_gray, tmpl_edges = self.prepare_gray_edges(tmpl_bgr)
            tmpl_hash = hex_to_hash(str(meta["hash_hex"]))
            tmpl_hist = self._histogram(tmpl_bgr)
            stored = {
                "name": meta["name"],
                "path": meta["path"],
                "bgr": tmpl_bgr,
                "gray": tmpl_gray,
                "edges": tmpl_edges,
                "hash": tmpl_hash,
                "hist": tmpl_hist,
            }
            self._cache[canon] = stored
            return stored
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
    def _histogram(bgr: np.ndarray) -> np.ndarray:
        hist = cv2.calcHist([bgr], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
        cv2.normalize(hist, hist)
        return hist

    @staticmethod
    def _hist_compare(h1: np.ndarray, h2: np.ndarray) -> float:
        if h1 is None or h2 is None:
            return 0.0
        sim = cv2.compareHist(h1, h2, cv2.HISTCMP_CORREL)
        return float(max(-1.0, min(1.0, sim))) * 0.5 + 0.5

    @staticmethod
    def _hash_score(a, b) -> float:
        try:
            dist = a - b
            return max(0.0, 1.0 - (float(dist) / 64.0))
        except Exception:
            return 0.0

    @staticmethod
    def prepare_gray_edges(img_bgr: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Return (gray, edges) with light denoise to stabilize matching."""
        if img_bgr is None or img_bgr.size == 0:
            return np.zeros((1, 1), dtype=np.uint8), np.zeros((1, 1), dtype=np.uint8)
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        # Ensure gray is properly typed as numpy array for median calculation
        gray_array = np.asarray(gray, dtype=np.uint8)
        v = np.median(gray_array)
        lower = int(max(0, 0.66 * v))
        upper = int(min(255, 1.33 * v + 20))
        edges = cv2.Canny(gray, lower, upper)
        return gray, edges

    def _template_score(self, region: np.ndarray, template: np.ndarray) -> float:
        """Multi-scale template matching with gray/edge fusion.
        Returns the best score across scales using TM_CCOEFF_NORMED."""
        try:
            if region is None or template is None:
                return 0.0
            rh, rw = region.shape[:2]
            if rh < 4 or rw < 4:
                return 0.0

            # Prepare once
            reg_gray, reg_edges = self.prepare_gray_edges(region)
            tmpl_gray, tmpl_edges = self.prepare_gray_edges(template)

            # Iterate scales, but skip sizes larger than region
            min_s = min(self.ms_min_scale, self.ms_max_scale)
            max_s = max(self.ms_min_scale, self.ms_max_scale)
            best = 0.0
            for s in np.linspace(min_s, max_s, self.ms_steps):
                th = max(1, int(round(tmpl_gray.shape[0] * s)))
                tw = max(1, int(round(tmpl_gray.shape[1] * s)))
                if th > rh or tw > rw:
                    continue
                t_gray = cv2.resize(tmpl_gray, (tw, th), interpolation=cv2.INTER_AREA)
                t_edges = cv2.resize(tmpl_edges, (tw, th), interpolation=cv2.INTER_AREA)

                # Gray correlation
                res_g = cv2.matchTemplate(reg_gray, t_gray, cv2.TM_CCOEFF_NORMED)
                sc_g = float(res_g.max()) if res_g.size else 0.0
                # Edge correlation (robust to color/lighting)
                res_e = cv2.matchTemplate(reg_edges, t_edges, cv2.TM_CCOEFF_NORMED)
                sc_e = float(res_e.max()) if res_e.size else 0.0

                fused = self.tm_gray_weight * sc_g + self.tm_edge_weight * sc_e
                if fused > best:
                    best = fused
            return float(best)
        except Exception:
            return 0.0
