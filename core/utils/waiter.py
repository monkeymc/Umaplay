# core/utils/waiter.py
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from PIL import Image

from core.controllers.base import IController
from core.perception.ocr.interface import OCRInterface
from core.perception.yolo.interface import IDetector
from core.utils.geometry import crop_pil
from core.utils.logger import logger_uma
from core.utils.text import fuzzy_contains, fuzzy_ratio
from core.utils.yolo_objects import filter_by_classes as det_filter

DetectionDict = dict
XYXY = Tuple[float, float, float, float]


@dataclass(frozen=True)
class PollConfig:
    """
    Base polling config for a Waiter. You construct this once and reuse.
    Public API only overrides timeout/interval/tag per call.
    """
    imgsz: int = 832
    conf: float = 0.51
    iou: float = 0.45
    poll_interval_s: float = 0.25
    timeout_s: float = 4.0
    tag: str = "waiter"


class Waiter:
    """
    Unified waiter that waits for UI objects and clicks as soon as the target is
    confidently resolved. Only ONE public API: `click_when`.

    Cascade per poll:
      1) If exactly one candidate: click it (no OCR) — unless it matches a forbidden text.
      2) If multiple and prefer_bottom: click bottom-most — unless forbidden.
         If forbidden, try the next bottom-most, etc.
      3) Else if texts provided and OCR available: OCR candidates and click best
         positive match (ignoring any that match forbidden texts).
      4) Else: keep polling until resolved or timeout.
    """

    def __init__(self, ctrl: IController, ocr: Optional[OCRInterface], 
    yolo_engine: IDetector, config: PollConfig):
        self.ctrl = ctrl
        self.ocr = ocr
        self.yolo_engine = yolo_engine
        self.cfg = config

    # ---------------------------
    # Public API
    # ---------------------------

    def click_when(
        self,
        *,
        classes: Sequence[str],
        texts: Optional[Sequence[str]] = None,
        threshold: float = 0.68,
        prefer_bottom: bool = False,
        timeout_s: Optional[float] = None,
        poll_interval_s: Optional[float] = None,
        tag: Optional[str] = None,
        clicks: int = 1,
        allow_greedy_click: bool = True,
        # NEW: text exceptions
        forbid_texts: Optional[Sequence[str]] = None,
        forbid_threshold: float = 0.65,
    ) -> bool:
        """
        Wait until an object of `classes` appears and click it using the cascade.

        Parameters (new)
        ----------------
        forbid_texts:
            A list of phrases that, if matched (fuzzy) by the candidate’s OCR text,
            will prevent clicking that candidate.
        forbid_threshold:
            Fuzzy ratio threshold for a phrase to be considered a match in `forbid_texts`.

        Returns True if clicked; False if timed out.
        """
        if not classes:
            raise ValueError("Waiter.click_when: 'classes' must be a non-empty sequence.")

        timeout = self._pick(timeout_s, self.cfg.timeout_s)
        interval = self._pick(poll_interval_s, self.cfg.poll_interval_s)
        tag = tag or self.cfg.tag

        # Normalize inputs
        texts = self._norm_seq(texts)
        forbid_texts = self._norm_seq(forbid_texts)

        t0 = time.time()
        while True:
            img, dets = self._snap(tag=tag)
            cand = det_filter(dets, classes)

            if cand:
                # 1) Single candidate fast path (with optional forbid check)
                if len(cand) == 1 and allow_greedy_click:
                    pick = cand[0]
                    if self._is_forbidden(img, pick, forbid_texts, forbid_threshold):
                        # Skip this candidate; keep polling for a better state.
                        logger_uma.debug("[waiter] single candidate rejected by forbid_texts (tag=%s)", tag)
                    else:
                        self.ctrl.click_xyxy_center(pick["xyxy"], clicks=clicks)
                        return True

                # 2) Bottom-most preference (try from bottom to top; skip forbiddens)
                if prefer_bottom and allow_greedy_click:
                    ordered = sorted(cand, key=lambda d: (d["xyxy"][1] + d["xyxy"][3]) * 0.5, reverse=True)
                    chosen = None
                    for d in ordered:
                        if not self._is_forbidden(img, d, forbid_texts, forbid_threshold):
                            chosen = d
                            break
                    if chosen is not None:
                        self.ctrl.click_xyxy_center(chosen["xyxy"], clicks=clicks)
                        return True
                    # All bottom candidates forbidden → continue polling.

                # 3) OCR disambiguation by positive `texts` (ignoring forbiddens)
                if texts and self.ocr:
                    pick = self._pick_by_text(img, cand, texts, threshold, forbid_texts, forbid_threshold)
                    if pick is not None:
                        self.ctrl.click_xyxy_center(pick["xyxy"], clicks=clicks)
                        return True
                    # If OCR didn't reach threshold or all candidates were forbidden, continue polling.

            if (time.time() - t0) >= timeout:
                if tag not in ["agent_unknown_advance",]:
                    logger_uma.debug("[waiter] timeout after %.2fs (tag=%s)", timeout, tag)
                return False

            time.sleep(interval)

    def seen(
        self,
        *,
        classes: Optional[Sequence[str]] = None,
        texts: Optional[Sequence[str]] = None,
        tag: Optional[str] = None,
        conf_min: float = 0.0,
        threshold: float = 0.58,
    ) -> bool:
        """
        Snapshot once and return True if:
          • ANY detection of the provided `classes` exists (when `texts` is not given), or
          • ANY detection of the provided `classes` OCR-matches ANY of `texts` (fuzzy),
            if `texts` is provided. If `classes` is None, OCR is applied to all detections.

        No waiting/polling, no clicks.
        """
        img, dets = self._snap(tag=tag or (self.cfg.tag + "_seen"))

        # Filter by classes when provided
        candidates = det_filter(dets, classes, conf_min=conf_min) if classes else list(dets)

        # Fast path: just checking for presence of classes
        if not texts:
            return bool(candidates)

        # OCR path: fuzzy match any target text on any candidate bbox
        texts = [t for t in (texts or []) if (t or "").strip()]
        if not texts:
            return bool(candidates)

        for d in candidates:
            try:
                roi = d.get("xyxy")
                if not roi:
                    continue
                crop = crop_pil(img, roi, pad=0)
                txt = (self.ocr.text(crop) or "").strip()
                if not txt:
                    continue
                for target in texts:
                    if fuzzy_contains(txt, target, threshold=threshold):
                        return True
            except Exception:
                # Be conservative; failure to OCR this box shouldn't stop others
                continue
        return False

    def try_click_once(
        self,
        *,
        classes: Sequence[str],
        texts: Optional[Sequence[str]] = None,
        threshold: float = 0.68,
        prefer_bottom: bool = False,
        tag: Optional[str] = None,
        clicks: int = 1,
        allow_greedy_click: bool = True,
        forbid_texts: Optional[Sequence[str]] = None,
        forbid_threshold: float = 0.65,
    ) -> bool:
        """
        Single snapshot best-effort click using the same cascade as `click_when`,
        but WITHOUT polling/waiting. Returns True if a click was performed.
        """
        if not classes:
            return False
        img, dets = self._snap(tag=tag or (self.cfg.tag + "_try"))
        cand = det_filter(dets, classes)
        texts = self._norm_seq(texts)
        forbid_texts = self._norm_seq(forbid_texts)

        if not cand:
            return False

        # 1) Single candidate fast path
        if len(cand) == 1 and allow_greedy_click:
            pick = cand[0]
            if not self._is_forbidden(img, pick, forbid_texts, forbid_threshold):
                self.ctrl.click_xyxy_center(pick["xyxy"], clicks=clicks)
                return True

        # 2) Bottom-most preference
        if prefer_bottom and allow_greedy_click:
            ordered = sorted(cand, key=lambda d: (d["xyxy"][1] + d["xyxy"][3]) * 0.5, reverse=True)
            for d in ordered:
                if not self._is_forbidden(img, d, forbid_texts, forbid_threshold):
                    self.ctrl.click_xyxy_center(d["xyxy"], clicks=clicks)
                    return True

        # 3) OCR disambiguation
        if texts and self.ocr:
            pick = self._pick_by_text(img, cand, texts, threshold, forbid_texts, forbid_threshold)
            if pick is not None:
                self.ctrl.click_xyxy_center(pick["xyxy"], clicks=clicks)
                return True

        return False

    # ---------------------------
    # Internals
    # ---------------------------

    def _snap(self, *, tag: str) -> Tuple[Image.Image, List[DetectionDict]]:
        img, _, dets = self.yolo_engine.recognize(
            imgsz=self.cfg.imgsz, conf=self.cfg.conf, iou=self.cfg.iou, tag=tag
        )
        return img, dets

    def _is_forbidden(
        self,
        img: Image.Image,
        det: DetectionDict,
        forbid_texts: Optional[List[str]],
        forbid_threshold: float,
    ) -> bool:
        """
        OCR just this candidate and check against forbidden phrases.
        Cheap: only runs when we are about to click (single/bottom-most),
        or while disambiguating by text.
        """
        if not forbid_texts or not self.ocr:
            return False
        crop = crop_pil(img, det["xyxy"], pad=0)
        txt = (self.ocr.text(crop) or "").strip().lower()
        if not txt:
            return False
        for ft in forbid_texts:
            if fuzzy_ratio(txt, ft) >= forbid_threshold:
                return True
        return False

    def _pick_by_text(
        self,
        img: Image.Image,
        cand: List[DetectionDict],
        texts: Sequence[str],
        threshold: float,
        forbid_texts: Optional[List[str]] = None,
        forbid_threshold: float = 0.65,
    ) -> Optional[DetectionDict]:
        """
        OCR candidates and pick the one whose text best matches any of `texts`,
        ignoring any candidate that matches `forbid_texts`.
        Returns None if no candidate reaches `threshold`.
        """
        texts = self._norm_seq(texts)
        if not texts or not self.ocr:
            return None

        best_d, best_s = None, 0.0
        for d in cand:
            crop = crop_pil(img, d["xyxy"], pad=0)
            txt = (self.ocr.text(crop) or "").strip()
            if not txt:
                continue
            # Skip forbidden
            if forbid_texts and any(fuzzy_ratio(txt.lower(), ft) >= forbid_threshold for ft in forbid_texts):
                continue
            txt_split = txt.split(" ")
            for t in texts:
                for t_split in txt_split:
                    if t.upper() == t_split.upper():
                        # Direct match
                        s = 0.95
                        if s > best_s:
                            best_d, best_s = d, s

            s = max(fuzzy_ratio(txt, t) for t in texts)
            if s > best_s:
                best_d, best_s = d, s

        if best_d is not None and best_s >= threshold:
            return best_d
        return None

    @staticmethod
    def _pick(value, default):
        return default if value is None else value

    @staticmethod
    def _norm_seq(seq: Optional[Sequence[str]]) -> Optional[List[str]]:
        if not seq:
            return None
        out = [s.strip().lower() for s in seq if s and str(s).strip()]
        return out or None
