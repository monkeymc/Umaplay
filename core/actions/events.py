# core/actions/events.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict, Any

from PIL import Image

from core.types import DetectionDict
from core.controllers.base import IController
from core.perception.ocr.interface import OCRInterface  # your interface type
from core.perception.yolo.interface import IDetector
from core.utils.logger import logger_uma
from core.utils.waiter import Waiter

# Event retriever (local-only, CPU) you packaged
from core.utils.event_processor import (
    Catalog,
    UserPrefs,
    Query,
    retrieve_best,
)

# -----------------------------
# Helpers
# -----------------------------

def _clamp_box(box: Tuple[float, float, float, float], w: int, h: int) -> Tuple[int, int, int, int]:
    x1, y1, x2, y2 = box
    x1 = max(0, min(int(x1), w - 1))
    y1 = max(0, min(int(y1), h - 1))
    x2 = max(0, min(int(x2), w - 1))
    y2 = max(0, min(int(y2), h - 1))
    if x2 <= x1:
        x2 = min(w - 1, x1 + 1)
    if y2 <= y1:
        y2 = min(h - 1, y1 + 1)
    return x1, y1, x2, y2


def _crop(img: Image.Image, box: Tuple[float, float, float, float]) -> Image.Image:
    W, H = img.size
    x1, y1, x2, y2 = _clamp_box(box, W, H)
    return img.crop((x1, y1, x2, y2))


def _sort_top_to_bottom(dets: List[DetectionDict]) -> List[DetectionDict]:
    return sorted(dets, key=lambda d: float(d["xyxy"][1]))


def _count_chain_steps(parsed: List[DetectionDict]) -> Optional[int]:
    steps = [d for d in parsed if d.get("name") == "event_chain"]
    return len(steps) if steps else None


def _pick_event_card(parsed: List[DetectionDict]) -> Optional[DetectionDict]:
    cards = [d for d in parsed if d.get("name") == "event_card"]
    if not cards:
        return None
    # highest confidence first
    cards.sort(key=lambda d: float(d.get("conf", 0.0)), reverse=True)
    return cards[0]


def _choices(parsed: List[DetectionDict], *, conf_min: float) -> List[DetectionDict]:
    return [
        d for d in parsed
        if d.get("name") == "event_choice" and float(d.get("conf", 0.0)) >= conf_min
    ]



def _extract_title_description_from_banner(
    ocr: OCRInterface,
    frame: Image.Image,
    card_box: Tuple[float, float, float, float],
) -> Tuple[str, str]:
    """
    The blue banner spans horizontally to the right of the portrait (event_card).
    The 'Support Card Event' header sits roughly in the top 30-40% of that banner,
    and the actual event title (we want) is below it (bigger white text).
    Strategy: crop the right-side band with slight vertical padding; OCR; pick the
    longest high-signal line from the lower half.
    """
    W, H = frame.size
    x1, y1, x2, y2 = card_box
    card_w = x2 - x1
    card_h = y2 - y1

    # Right-side blue banner crop
    pad_x = 0.05 * card_w
    vpad = 0.10 * card_h
    right = (
        x2 + pad_x,
        max(0.0, y1 - vpad),
        min(W - 1.0, x2 + 6.5 * card_w),
        min(H - 1.0, y2 + vpad),
    )
    banner = _crop(frame, right)

    # Split roughly: top zone (header), bottom zone (title)
    bw, bh = banner.size
    # If the portrait is nearly square, the header ribbon is typically shorter,
    # so use 30% for the header; if it's a taller vertical rectangle, use 40%.
    aspect = (card_h / max(card_w, 1e-6))  # h/w
    squareish = 0.85 <= aspect <= 1.15

    if squareish:
        split_y = int(0.30 * bh)
    else:
        split_y = int(0.40 * bh)

    title_zone = banner.crop((0, 0, bw, split_y))
    description_zone = banner.crop((0, split_y, bw, bh))

    title_text = ocr.text(title_zone)
    description_text = ocr.text(description_zone)

    return title_text, description_text

# -----------------------------
# EventFlow
# -----------------------------

@dataclass
class EventDecision:
    """What we matched and what we clicked."""
    matched_key: Optional[str]
    matched_key_step: Optional[str]
    pick_option: int
    clicked_box: Optional[Tuple[float, float, float, float]]
    debug: Dict[str, Any]


class EventFlow:
    """
    Encapsulates *Event* screen behavior:
      - Reads OCR title from the blue banner (right of the portrait).
      - Counts chain arrows to infer chain_step_hint.
      - Uses portrait crop (PIL) to help retrieval.
      - Resolves user/default preferences and clicks the selected option.
      - Falls back to top option on any inconsistency.
    """

    def __init__(
        self,
        ctrl: IController,
        ocr: OCRInterface,
        yolo_engine: IDetector,
        waiter: Waiter,
        catalog: Catalog,
        prefs: UserPrefs,
        *,
        conf_min_choice: float = 0.60,
        debug_visual: bool = False,
    ) -> None:
        self.ctrl = ctrl
        self.ocr = ocr
        self.yolo_engine = yolo_engine
        self.waiter = waiter
        self.catalog = catalog
        self.prefs = prefs
        self.conf_min_choice = conf_min_choice
        self.debug_visual = debug_visual

    # ----- public API -----

    def process_event_screen(
        self,
        frame: Image.Image,
        parsed_objects_screen: List[DetectionDict],
    ) -> EventDecision:
        """
        Main entry point when we're already on an Event screen.
        """
        debug: Dict[str, Any] = {}

        # 1) Collect detections
        card = _pick_event_card(parsed_objects_screen)
        chain_step_hint = _count_chain_steps(parsed_objects_screen)
        choices = _choices(parsed_objects_screen, conf_min=self.conf_min_choice)
        choices_sorted = _sort_top_to_bottom(choices)

        debug["chain_step_hint"] = chain_step_hint
        debug["num_choices"] = len(choices_sorted)
        debug["has_event_card"] = card is not None

        # 2) Extract OCR title from banner (right of portrait)
        ocr_title = ""
        ocr_description = ""
        if card is not None:
            ocr_title, ocr_description = _extract_title_description_from_banner(self.ocr, frame, tuple(card["xyxy"]))
        else:
            # fallback heuristic: try to OCR a central horizontal band (less reliable)
            W, H = frame.size
            band = _crop(frame, (int(0.10 * W), int(0.30 * H), int(0.90 * W), int(0.55 * H)))
            ocr_title = self.ocr.text(band)
            ocr_title = ocr_title[0] if isinstance(ocr_title, list) and ocr_title else ""

        debug["ocr_title"] = ocr_title
        debug["ocr_description"] = ocr_description

        # 3) Build query for retriever
        type_hint = None
        if "support" in ocr_title.lower():
            type_hint = "support"
        elif "trainee" in ocr_title.lower():
            type_hint = "trainee"
        portrait_img: Optional[Image.Image] = None
        if card is not None:
            portrait_img = _crop(frame, tuple(card["xyxy"]))

        # Description holds the most important part
        ocr_query = ocr_description or ocr_title or ""
        q = Query(
            ocr_title=ocr_query,
            type_hint=type_hint,
            name_hint=None,             # not available at runtime (deck-agnostic)
            rarity_hint=None,           # not available; portrait helps instead
            chain_step_hint=chain_step_hint,
            portrait_image=portrait_img,  # <- PIL accepted by retriever (see diff)
        )

        # 4) Retrieve & rank
        cands = retrieve_best(self.catalog, q, top_k=3, min_score=0.8)
        if not cands:
            logger_uma.warning("[event] No candidates from retriever; falling back to top option.")
            return self._fallback_click_top(choices_sorted, debug)

        best = cands[0]
        debug["top_match"] = {
            "key": best.rec.key,
            "key_step": best.rec.key_step,
            "score": best.score,
            "text_sim": best.text_sim,
            "img_sim": best.img_sim,
            "bonus": best.hint_bonus,
        }

        # 5) Resolve preference
        pick = self.prefs.pick_for(best.rec)
        debug["pick_resolved"] = pick

        # 6) Validate number of options vs YOLO choices
        expected_n = len(best.rec.options or {})
        debug["expected_n_options"] = expected_n

        if expected_n <= 0:
            logger_uma.warning("[event] Matched event has no options in DB; fallback to top.")
            return self._fallback_click_top(choices_sorted, debug)

        if len(choices_sorted) != expected_n:
            logger_uma.warning(
                "[event] YOLO found %d choices but DB expects %d; fallback to top.",
                len(choices_sorted), expected_n
            )
            return self._fallback_click_top(choices_sorted, debug)

        if pick < 1 or pick > expected_n:
            logger_uma.warning("[event] Preference pick=%d out of range 1..%d; fallback to top.", pick, expected_n)
            return self._fallback_click_top(choices_sorted, debug)

        # 7) Click selected option (top-to-bottom order)
        target = choices_sorted[pick - 1]
        self.ctrl.click_xyxy_center(target["xyxy"], clicks=1)
        logger_uma.info(
            "[event] Clicked option #%d for %s (score=%.3f).",
            pick, best.rec.key_step, best.score
        )

        return EventDecision(
            matched_key=best.rec.key,
            matched_key_step=best.rec.key_step,
            pick_option=pick,
            clicked_box=tuple(target["xyxy"]),
            debug=debug,
        )

    # ----- internals -----

    def _fallback_click_top(
        self,
        choices_sorted: List[DetectionDict],
        debug: Dict[str, Any],
    ) -> EventDecision:
        if not choices_sorted:
            logger_uma.info("[event] No event_choice to click.")
            return EventDecision(
                matched_key=None,
                matched_key_step=None,
                pick_option=1,
                clicked_box=None,
                debug=debug,
            )

        top_choice = choices_sorted[0]
        self.ctrl.click_xyxy_center(top_choice["xyxy"], clicks=1)
        logger_uma.info("[event] Fallback: clicked top event_choice (conf=%.3f).", float(top_choice.get("conf", 0.0)))
        return EventDecision(
            matched_key=None,
            matched_key_step=None,
            pick_option=1,
            clicked_box=tuple(top_choice["xyxy"]),
            debug=debug,
        )
