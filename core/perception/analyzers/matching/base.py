from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# OpenCV is optional for remote-only clients. Guard runtime access so module import works without it.
try:  # pragma: no cover - exercised indirectly
    import cv2 as _cv2
except ImportError:  # pragma: no cover - fallback path for remote clients without OpenCV
    _cv2 = None  # type: ignore[assignment]
import numpy as np
from PIL import Image
from imagehash import hex_to_hash, phash

from core.utils.img import to_bgr
from core.utils.logger import logger_uma


def _require_cv2() -> Any:
    if _cv2 is None:
        raise RuntimeError(
            "OpenCV is required for local template matching. Install 'opencv-python' or enable remote processing."
        )
    return _cv2


@dataclass(frozen=True)
class TemplateEntry:
    """Source definition for a template that will be prepared for matching."""

    name: str
    path: Optional[str] = None
    image: Optional[np.ndarray] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PreparedTemplate:
    name: str
    path: str
    bgr: np.ndarray
    gray: np.ndarray
    edges: np.ndarray
    hist: np.ndarray
    hash: Any
    metadata: Dict[str, Any]
    mask: Optional[np.ndarray] = None


@dataclass
class RegionFeatures:
    bgr: np.ndarray
    gray: np.ndarray
    edges: np.ndarray
    hist: np.ndarray
    hash: Any
    shape: Tuple[int, int]


@dataclass
class TemplateMatch:
    name: str
    score: float
    tm_score: float
    hash_score: float
    hist_score: float
    path: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class TemplateMatcherBase:
    """Shared multiscale template-matching helper with histogram and hash fusion."""

    def __init__(
        self,
        *,
        tm_weight: float = 0.7,
        hash_weight: float = 0.2,
        hist_weight: float = 0.1,
        tm_edge_weight: float = 0.30,
        ms_min_scale: float = 0.60,
        ms_max_scale: float = 1.40,
        ms_steps: int = 9,
    ) -> None:
        self.tm_weight = float(tm_weight)
        self.hash_weight = float(hash_weight)
        self.hist_weight = float(hist_weight)
        total = max(self.tm_weight + self.hash_weight + self.hist_weight, 1e-9)
        self.tm_weight /= total
        self.hash_weight /= total
        self.hist_weight /= total
        self.tm_edge_weight = float(max(0.0, min(1.0, tm_edge_weight)))
        self.tm_gray_weight = 1.0 - self.tm_edge_weight
        self.ms_min_scale = float(ms_min_scale)
        self.ms_max_scale = float(ms_max_scale)
        self.ms_steps = int(max(1, ms_steps))

    def _prepare_entry(self, entry: TemplateEntry) -> Optional[PreparedTemplate]:
        cv2 = _require_cv2()
        try:
            # Load template preserving alpha if present to build a portrait mask
            tmpl_bgr: np.ndarray
            tmpl_mask: Optional[np.ndarray] = None

            # Load image preserving alpha channel for mask extraction
            if entry.image is not None:
                pil = entry.image if isinstance(entry.image, Image.Image) else Image.fromarray(entry.image)
            elif entry.path:
                pil = Image.open(entry.path)
            else:
                raise ValueError("TemplateEntry requires either image or path")

            # Convert to RGBA to extract alpha mask, then use to_bgr for consistent color handling
            pil_rgba = pil.convert("RGBA")
            rgba_arr = np.array(pil_rgba)
            alpha = rgba_arr[:, :, 3]
            tmpl_mask = (alpha > 10).astype(np.uint8) * 255 if alpha.size > 0 else None

            # Use to_bgr for consistent color conversion (handles PIL RGB → BGR correctly)
            tmpl_bgr = to_bgr(pil_rgba)

            tmpl_bgr = np.ascontiguousarray(tmpl_bgr)
            tmpl_gray, tmpl_edges = self.prepare_gray_edges(tmpl_bgr)

            metadata = dict(entry.metadata or {})
            hash_hex = metadata.pop("hash_hex", None)

            # For template hash, neutralize the outside-of-mask region to the masked mean to reduce background bias
            if tmpl_mask is not None and tmpl_mask.size:
                mask_bool = tmpl_mask > 0
                rgb_for_hash = cv2.cvtColor(tmpl_bgr, cv2.COLOR_BGR2RGB)
                if mask_bool.any():
                    mean_pix = rgb_for_hash[mask_bool].mean(axis=0).astype(np.uint8)
                    rgb_hash = rgb_for_hash.copy()
                    rgb_hash[~mask_bool] = mean_pix
                else:
                    rgb_hash = rgb_for_hash
                pil_for_hash = Image.fromarray(rgb_hash)
            else:
                pil_for_hash = Image.fromarray(cv2.cvtColor(tmpl_bgr, cv2.COLOR_BGR2RGB))

            if hash_hex is not None:
                tmpl_hash = hex_to_hash(str(hash_hex))
            else:
                tmpl_hash = phash(pil_for_hash)

            tmpl_hist = self._histogram(tmpl_bgr, mask=tmpl_mask)

            return PreparedTemplate(
                name=entry.name,
                path=str(entry.path or metadata.get("path", "")),
                bgr=tmpl_bgr,
                gray=tmpl_gray,
                edges=tmpl_edges,
                hist=tmpl_hist,
                hash=tmpl_hash,
                metadata=metadata,
                mask=tmpl_mask,
            )
        except Exception as exc:
            logger_uma.debug(
                "[template_matcher] Failed to prepare template '%s': %s",
                entry.name,
                exc,
            )
            return None

    def _prepare_region(self, region_bgr: np.ndarray) -> RegionFeatures:
        cv2 = _require_cv2()
        # Ensure canonical BGR regardless of source (RGB/BGRA/PIL)
        region_bgr = to_bgr(region_bgr)
        region_bgr = np.ascontiguousarray(region_bgr)

        reg_gray, reg_edges = self.prepare_gray_edges(region_bgr)
        reg_hist = self._histogram(region_bgr)

        # Perceptual hash over normalized BGR region
        reg_hash = phash(Image.fromarray(cv2.cvtColor(region_bgr, cv2.COLOR_BGR2RGB)))
        h, w = region_bgr.shape[:2]
        return RegionFeatures(
            bgr=region_bgr,
            gray=reg_gray,
            edges=reg_edges,
            hist=reg_hist,
            hash=reg_hash,
            shape=(h, w),
        )

    def _match_region(
        self,
        region: RegionFeatures,
        templates: Sequence[PreparedTemplate],
        *,
        candidates: Optional[Sequence[str]] = None,
    ) -> List[TemplateMatch]:
        allowed = set(candidates) if candidates else None
        matches: List[TemplateMatch] = []
        for tmpl in templates:
            if allowed and tmpl.name not in allowed:
                continue
            match = self._score_template(region, tmpl)
            matches.append(match)
        matches.sort(key=lambda m: m.score, reverse=True)
        return matches

    def _score_template(
        self,
        region: RegionFeatures,
        template: PreparedTemplate,
    ) -> TemplateMatch:
        tm_score = self._template_score(
            region.gray,
            region.edges,
            template.gray,
            template.edges,
            region.shape,
            template.mask,
        )
        hash_score = self._hash_score(region.hash, template.hash)
        hist_score = self._hist_compare(region.hist, template.hist)
        final_score = (
            self.tm_weight * tm_score
            + self.hash_weight * hash_score
            + self.hist_weight * hist_score
        )
        return TemplateMatch(
            name=template.name,
            score=float(final_score),
            tm_score=float(tm_score),
            hash_score=float(hash_score),
            hist_score=float(hist_score),
            path=template.path,
            metadata=template.metadata,
        )

    def _template_score(
        self,
        region_gray: np.ndarray,
        region_edges: np.ndarray,
        template_gray: np.ndarray,
        template_edges: np.ndarray,
        region_shape: Tuple[int, int],
        template_mask: Optional[np.ndarray] = None,
    ) -> float:
        cv2 = _require_cv2()
        try:
            reg_h, reg_w = region_shape
            if reg_h < 4 or reg_w < 4:
                return 0.0
            best = 0.0
            tmpl_gray = template_gray
            tmpl_edges = template_edges
            tmpl_h, tmpl_w = tmpl_gray.shape[:2]
            if tmpl_h <= 0 or tmpl_w <= 0:
                return 0.0

            min_scale = min(self.ms_min_scale, self.ms_max_scale)
            max_scale = max(self.ms_min_scale, self.ms_max_scale)

            scale_limit = min(reg_h / float(tmpl_h), reg_w / float(tmpl_w))
            if scale_limit <= 0.0:
                return 0.0

            max_scale = min(max_scale, scale_limit)
            min_scale = min(min_scale, max_scale)
            if min_scale <= 0.0:
                min_scale = max_scale

            for scale in np.linspace(min_scale, max_scale, self.ms_steps):
                th = max(1, int(round(tmpl_gray.shape[0] * scale)))
                tw = max(1, int(round(tmpl_gray.shape[1] * scale)))
                if th > reg_h or tw > reg_w:
                    continue
                resized_gray = cv2.resize(tmpl_gray, (tw, th), interpolation=cv2.INTER_AREA)
                resized_edges = cv2.resize(tmpl_edges, (tw, th), interpolation=cv2.INTER_AREA)
                if template_mask is not None and template_mask.size:
                    m = cv2.resize(template_mask, (tw, th), interpolation=cv2.INTER_NEAREST)
                    if m.dtype != np.uint8:
                        m = m.astype(np.uint8)
                else:
                    m = None

                # Use masked CCORR_NORMED (OpenCV >=4.2 supports mask)
                try:
                    res_gray = cv2.matchTemplate(
                        region_gray, resized_gray, cv2.TM_CCORR_NORMED, mask=m
                    )
                    sc_gray = float(res_gray.max()) if res_gray.size else 0.0
                except cv2.error:
                    # Fallback: unmasked
                    res_gray = cv2.matchTemplate(region_gray, resized_gray, cv2.TM_CCOEFF_NORMED)
                    sc_gray = float(res_gray.max()) if res_gray.size else 0.0

                try:
                    res_edges = cv2.matchTemplate(
                        region_edges, resized_edges, cv2.TM_CCORR_NORMED, mask=m
                    )
                    sc_edges = float(res_edges.max()) if res_edges.size else 0.0
                except cv2.error:
                    res_edges = cv2.matchTemplate(region_edges, resized_edges, cv2.TM_CCOEFF_NORMED)
                    sc_edges = float(res_edges.max()) if res_edges.size else 0.0

                fused = self.tm_gray_weight * sc_gray + self.tm_edge_weight * sc_edges
                if fused > best:
                    best = fused
            return float(best)
        except Exception:
            return 0.0

    @staticmethod
    def prepare_gray_edges(img_bgr: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        cv2 = _require_cv2()
        if img_bgr is None or img_bgr.size == 0:
            return np.zeros((1, 1), dtype=np.uint8), np.zeros((1, 1), dtype=np.uint8)
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        gray_array = np.asarray(gray, dtype=np.uint8)
        v = np.median(gray_array)
        lower = int(max(0, 0.66 * v))
        upper = int(min(255, 1.33 * v + 20))
        edges = cv2.Canny(gray, lower, upper)
        return gray, edges


    @staticmethod
    def _histogram(bgr: np.ndarray, mask: Optional[np.ndarray] = None) -> np.ndarray:
        cv2 = _require_cv2()
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        # 2D histogram on H and S; mask restricts to portrait when available
        hist = cv2.calcHist([hsv], [0, 1], mask, [180, 256], [0, 180, 0, 256])
        cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
        return hist

    @staticmethod
    def _hist_compare(h1: np.ndarray, h2: np.ndarray) -> float:
        cv2 = _require_cv2()
        if h1 is None or h2 is None:
            return 0.0
        sim = cv2.compareHist(h1, h2, cv2.HISTCMP_CORREL)
        return float(max(-1.0, min(1.0, sim))) * 0.5 + 0.5

    @staticmethod
    def _hash_score(a: Any, b: Any) -> float:
        try:
            dist = a - b
            return max(0.0, 1.0 - (float(dist) / 64.0))
        except Exception:
            return 0.0

    def prepare_templates(self, entries: Iterable[TemplateEntry]) -> List[PreparedTemplate]:
        """Helper used by subclasses to precompute template cache."""

        prepared: List[PreparedTemplate] = []
        for entry in entries:
            tmpl = self._prepare_entry(entry)
            if tmpl is not None:
                prepared.append(tmpl)
        return prepared
