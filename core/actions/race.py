# core/actions/race.py
from __future__ import annotations

import random
import time
from core.controllers.android import ScrcpyController
from core.perception.yolo.interface import IDetector
from core.utils.waiter import Waiter
from typing import Dict, List, Optional, Tuple
from core.utils.race_index import RaceIndex

from PIL import Image

from core.controllers.base import IController
from core.perception.analyzers.badge import BADGE_PRIORITY, BADGE_PRIORITY_REVERSE, _badge_label
from core.perception.is_button_active import ActiveButtonClassifier
from core.settings import Settings
from core.types import DetectionDict
from core.utils.geometry import crop_pil
from core.utils.logger import logger_uma
from core.utils.text import _normalize_ocr, fuzzy_ratio
from core.utils.yolo_objects import collect, find, bottom_most, inside
from core.utils.pointer import smart_scroll_small
from core.utils.abort import abort_requested

class ConsecutiveRaceRefused(Exception):
    """Raised when a consecutive-race penalty is detected and settings forbid accepting it."""
    pass

class RaceFlow:
    """
    Clean, modular Race flow:
      - Self-contained: can start from Lobby and drive to Raceday, run, and exit.
      - One Waiter instance (no ad-hoc loops for waiting).
      - YOLO helpers & pointer utilities are reused.
      - OCR is used only when texts=... is provided.
    """

    def __init__(self, ctrl: IController, ocr, yolo_engine: IDetector, waiter: Waiter) -> None:
        self.ctrl = ctrl
        self.ocr = ocr
        self.yolo_engine = yolo_engine
        self.waiter = waiter

    def _ensure_in_raceday(self, *, reason: str | None = None, from_raceday = False) -> bool:
        """
        Idempotent. If we're still in the Lobby, click the lobby 'RACES' tile (or the
        'race_race_day' entry) to enter Raceday; tolerate the consecutive OK popup.
        """
        # Quick probe: do we already see race squares?
        try:
            img, dets = self._collect("race_nav_probe")
            squares = find(dets, "race_square")
            if squares:
                return True
        except Exception:
            # If detection fails for any reason, try to navigate anyway.
            pass
        if reason:
            logger_uma.debug(f"Looking for race buttons: {reason}")
        # Try to enter race screen from lobby (idempotent)
        clicked = self.waiter.click_when(
            classes=("lobby_races", "race_race_day"),
            prefer_bottom=True,
            timeout_s=1.5,
            tag="race_nav_from_lobby",
        )
        if clicked:
            logger_uma.debug("Clicked 'RACES'. Fast-probing for squares vs penalty popup…")
            # Fast race: as soon as 'race_square' is seen, bail out; otherwise opportunistically click OK.
            t0 = time.time()
            MAX_WAIT = 1.6   # upper bound; typical exit << 1.0s
            while (time.time() - t0) < MAX_WAIT:
                if abort_requested():
                    logger_uma.info("[race] Abort requested during nav to Raceday.")
                    return False
                # 1) If squares are already visible → done
                if self.waiter.seen(classes=("race_square",), tag="race_nav_seen_squares"):
                    return True
                # 2) If consecutive-race penalty popup is present → honor settings
                if self.waiter.seen(
                    classes=("button_green",),
                    texts=("OK",),
                    tag="race_nav_penalty_seen"
                ):
                    # from_raceday forces to accept consecutive, there is no another option
                    if not Settings.ACCEPT_CONSECUTIVE_RACE and not from_raceday:
                        logger_uma.info("[race] Consecutive race detected and refused by settings.")
                        raise ConsecutiveRaceRefused("Consecutive race not accepted by settings.")
                    # Accept the penalty promptly (single shot, no wait)
                    self.waiter.click_when(
                        classes=("button_green",),
                        texts=("OK",),
                        prefer_bottom=False,
                        allow_greedy_click=False,
                        timeout_s=0.5,
                        tag="race_nav_penalty_ok_click"
                    )
                    logger_uma.debug("Consecutive race. Accepted penalization per settings.")

                time.sleep(0.12)
            # If loop expires, do one last probe:
            if self.waiter.seen(classes=("race_square",), tag="race_nav_seen_final"):
                return True
            return False
        return False
    # --------------------------
    # Internal helpers
    # --------------------------
    def _collect(self, tag: str) -> Tuple[Image.Image, List[DetectionDict]]:
        return collect(self.yolo_engine, imgsz=self.waiter.cfg.imgsz, conf=self.waiter.cfg.conf, iou=self.waiter.cfg.iou, tag=tag)

    def _pick_view_results_button(self) -> Optional[DetectionDict]:
        """Among white buttons, choose the one that OCR-matches 'VIEW RESULTS' best."""
        img, dets = self._collect("race_view_btn")
        whites = find(dets, "button_white")
        if not whites:
            return None

        best_d, best_s = None, 0.0
        for d in whites:
            txt = (self.ocr.text(crop_pil(img, d["xyxy"])) or "").strip()
            score = max(fuzzy_ratio(txt, "VIEW RESULTS"), fuzzy_ratio(txt, "VIEW RESULT"))
            if score > best_s and score > 0.01:
                best_d, best_s = d, score
        return best_d

    def _pick_race_square(
        self,
        *,
        prioritize_g1: bool,
        is_g1_goal: bool,
        desired_race_name: Optional[str] = None,
        max_scrolls: int = 3,
        date_key: Optional[str] = None,
    ) -> Tuple[Optional[DetectionDict], bool]:
        """
        Try to find a clickable race card:
          - consider 'race_square'
          - valid if it has >= 2 'race_star'
          - badge via color→OCR fallback
          - prioritize first G1 if requested; else EX>G1>G2>G3>OP (tie: topmost)
          - if desired_race_name is provided → do a one-way forward search for that name;
            if not found after scrolling up to max_scrolls, return (None, True) without fallback.

        """
        MINIMUM_RACE_OCR_MATCH = 0.85
        MIN_STARS = 2
        moved_cursor = False
        did_scroll = False
        first_top_xyxy = None

        best_non_g1: Optional[DetectionDict] = None
        best_rank: int = -1
        best_y: float = 1e9
        best_named: Optional[Tuple[DetectionDict, float]] = None  # (det, score)

        # Pre-compute the expected card titles and required rank for the desired race
        expected_cards: List[Tuple[str, str]] = []
        desired_order: int = 1
        seek_title: Optional[str] = None
        seek_rank: Optional[str] = None
        if desired_race_name:
            logger_uma.debug(f"Racing with desired_race_name={desired_race_name}")
            if date_key:
                e = RaceIndex.entry_for_name_on_date(desired_race_name, date_key)
                if e:
                    seek_title = str(e.get("display_title") or "").strip()
                    seek_rank  = str(e.get("rank") or "").strip().upper() or "UNK"
                    desired_order = int(e.get("order", 1)) if str(e.get("order", 1)).isdigit() else 1
                    expected_cards = [(seek_title, seek_rank)]
                    logger_uma.info("[race] Seeking '%s' on %s → title='%s', rank=%s, order=%d",
                                    desired_race_name, date_key, seek_title, seek_rank, desired_order)
            if not expected_cards:
                # fallback: not date-bound, use all occurrences
                expected_cards = RaceIndex.expected_titles_for_race(desired_race_name)
                logger_uma.info("[race] Seeking '%s' (no date binding) with titles: %s",
                                desired_race_name, [t for t, _ in expected_cards])
            if not expected_cards:
                # ultimate fallback to literal text
                expected_cards = [(desired_race_name.strip(), "UNK")]
                logger_uma.warning("[race] Dataset has no entries for '%s'; falling back to literal name.",
                                   desired_race_name)

        # collision tracking (how many times we’ve already seen the same display_title)
        seen_title_counts: Dict[str, int] = {}

        for scroll_j in range(max_scrolls + 1):
            game_img, dets = self._collect("race_pick")
            squares = find(dets, "race_square")
            if squares:
                # top→bottom

                squares.sort(key=lambda d: ((d["xyxy"][1] + d["xyxy"][3]) / 2.0))
                if first_top_xyxy is None:
                    first_top_xyxy = tuple(squares[0]["xyxy"])

                stars = find(dets, "race_star")
                badges = find(dets, "race_badge")

                if len(squares) == 1 and scroll_j == 0:
                    # Only one available race, doesn't matter star, choose it (e.g. Haru Urara Arima Kinen or Goal race without race aptitude due to lack of good sparks)
                    sq = squares[0]
                    need_click = True
                    if (not did_scroll) and first_top_xyxy is not None and tuple(sq["xyxy"]) == first_top_xyxy:
                        need_click = False
                    return sq, need_click
                
                # --- Optional: desired race search using dataset-built card title (right-of-badge OCR) ---
                if desired_race_name:
                    found_order = False
                    # Local best on this page — helps avoid scrolling past a good match
                    page_best: Optional[Tuple[DetectionDict, float]] = None
                    for idx_on_page, sq in enumerate(squares):
                        # minimum quality gate: at least 2 stars inside the square
                        s_cnt = sum(1 for st in stars if inside(st["xyxy"], sq["xyxy"], pad=3))
                        # if s_cnt < MIN_STARS:  # No stars in  desired race
                        #     continue

                        # badge (for rank validation) + OCR area: from badge right edge to square end
                        badge_det = next((b for b in badges if inside(b["xyxy"], sq["xyxy"], pad=3)), None)
                        badge_label = "UNK"
                        right_of_badge_xyxy = None
                        if badge_det is not None:
                            badge_label = _badge_label(self.ocr, game_img, badge_det["xyxy"])
                            bx1, by1, bx2, by2 = badge_det["xyxy"]
                            sx1, sy1, sx2, sy2 = sq["xyxy"]
                            badge_height = abs(by2 - by1)
                            padding = int(badge_height * 0.6)
                            right_of_badge_xyxy = (
                                bx2 + 1,
                                sy1 + padding,
                                sx2 - 6,
                                by2 + padding
                            )
                        else:
                            # conservative crop: right 70% of the square
                            sx1, sy1, sx2, sy2 = sq["xyxy"]
                            w = sx2 - sx1
                            right_of_badge_xyxy = (sx1 + int(0.30 * w), sy1 + 2, sx2 - 6, sy2 - 2)

                        try:
                            crop = crop_pil(game_img, right_of_badge_xyxy, pad=0)
                            txt = (self.ocr.text(crop) or "").strip()
                        except Exception:
                            txt = ""

                        best_score_here = 0

                        txt_split = txt.split(" ")
                        # try to look for 'perfect' match:
                        if len(expected_cards) == 1 and len(txt_split) >= 4:
                            expected_title, expected_rank = expected_cards[0]
                            txt_like_built = f"{txt_split[0]} {txt_split[1]} {txt_split[2]} {txt_split[3].strip()}".upper()

                            if (
                                badge_label.upper() == expected_rank.upper()
                                and txt_like_built == expected_title.upper()
                            ):
                                # Perfect match
                                best_score_here = 2
                        
                        if best_score_here == 0:
                            def clean_race_name(st):
                                n_txt = (
                                    st
                                    .upper()
                                    .replace("RIGHT", "")
                                    .replace("TURT", "TURF")
                                    .replace("DIRF", "DIRT")
                                    .replace("LEFT", "")
                                    .replace("INNER", "")
                                    .replace("1NNER", "")
                                    .replace("OUTER", "")
                                    .replace("/", "")
                                    .strip()  # TODO: handle right | left | etc
                                )
                                n_txt = _normalize_ocr(n_txt)
                                return n_txt
                            txt = clean_race_name(txt)

                            # If not 'perfect match' try fuzzy heuristic
                            # score against any of the expected cards; boost if badge matches rank
                            for expected_title, expected_rank in expected_cards:
                                expected_title_n = clean_race_name(expected_title)
                                s = fuzzy_ratio(txt, expected_title_n.upper())
                                if expected_rank in ("G1","G2","G3","OP","EX"):
                                    if badge_label.upper() == expected_rank.upper():
                                        s += 0.10  # reward correct badge
                                    elif badge_label != "UNK":
                                        s -= 0.20  # penalty for wrong badge
                                best_score_here = max(best_score_here, s)
                                logger_uma.debug(f"Score: {s} for 'txt'={txt} vs expected_title_n='{expected_title_n}'")

                        if best_named is None or best_score_here > best_named[1]:
                            best_named = (sq, best_score_here)
                        if (page_best is None) or (best_score_here > page_best[1]):
                            page_best = (sq, best_score_here)

                        # --- collision/order handling ---
                        # If we have a date-bound target with a known display_title, use order gating.
                        if seek_title:
                            # consider it a match only if title is close enough and badge ok
                            if best_score_here >= MINIMUM_RACE_OCR_MATCH:
                                cnt = seen_title_counts.get(seek_title, 0) + 1
                                seen_title_counts[seek_title] = cnt
                                logger_uma.info("[race] '%s' candidate #%d on page (idx=%d, score=%.2f, badge=%s, desired_order=%d)",
                                                seek_title, cnt, idx_on_page, best_score_here, badge_label, desired_order)
                                if cnt == desired_order:
                                    # pick this one — it is the N-th appearance of the title
                                    pick = sq
                                    ymid = (pick["xyxy"][1] + pick["xyxy"][3]) / 2.0
                                    need_click = True
                                    if (not did_scroll) and first_top_xyxy is not None and tuple(pick["xyxy"]) == first_top_xyxy:
                                        need_click = False
                                    logger_uma.info("[race] picked desired '%s' at required order=%d (y=%.1f)",
                                                    desired_race_name, desired_order, ymid)
                                    found_order = True
                                    return pick, need_click

                    # lock if we are reasonably sure on current page
                    if found_order and page_best and page_best[1] >= MINIMUM_RACE_OCR_MATCH:
                        pick = page_best[0]
                        ymid = (pick["xyxy"][1] + pick["xyxy"][3]) / 2.0
                        logger_uma.info("[race] picked desired '%s' by card-title (score=%.2f) at y=%.1f",
                                        desired_race_name, page_best[1], ymid)
                        need_click = True
                        if (not did_scroll) and first_top_xyxy is not None and tuple(pick["xyxy"]) == first_top_xyxy:
                            need_click = False
                        return pick, need_click
                else:
                    for sq in squares:
                        s_cnt = sum(1 for st in stars if inside(st["xyxy"], sq["xyxy"], pad=3))
                        if s_cnt < MIN_STARS:
                            logger_uma.debug(f"Not enough stars, found: {s_cnt}")
                            continue

                        badge_det = next((b for b in badges if inside(b["xyxy"], sq["xyxy"], pad=3)), None)
                        label = "UNK"
                        if badge_det is not None:
                            label = _badge_label(self.ocr, game_img, badge_det["xyxy"])
                        rank = BADGE_PRIORITY.get(label, 0)
                        ymid = (sq["xyxy"][1] + sq["xyxy"][3]) / 2.0

                        if prioritize_g1 or is_g1_goal:
                            if label == "G1":
                                logger_uma.info("[race] picked G1 with 2★ at y=%.1f", ymid)
                                need_click = True
                                if (not did_scroll) and first_top_xyxy is not None and tuple(sq["xyxy"]) == first_top_xyxy:
                                    need_click = False
                                return sq, need_click
                            # if not is_g1_goal:
                            #     if rank > best_rank or (rank == best_rank and ymid < best_y):
                            #         best_non_g1, best_rank, best_y = sq, rank, ymid
                        else:
                            if is_g1_goal:
                                continue
                            if best_non_g1 is None:
                                best_non_g1, best_rank, best_y = sq, rank, ymid
                            else:
                                if (rank > best_rank) or (rank == best_rank and ymid < best_y):
                                    best_non_g1, best_rank, best_y = sq, rank, ymid

            if best_non_g1 is not None:
                logger_uma.info(
                    f"[race] Picked best race found, rank={BADGE_PRIORITY_REVERSE[best_rank]}"
                    
                )
                need_click = True
                if (not did_scroll) and first_top_xyxy is not None and tuple(best_non_g1["xyxy"]) == first_top_xyxy:
                    need_click = False
                return best_non_g1, need_click

            if squares and not moved_cursor:
                self.ctrl.move_xyxy_center(squares[0]["xyxy"])
                time.sleep(0.10)
                moved_cursor = True

            # probe next batch
            smart_scroll_small(self.ctrl, steps_pc=4)
            did_scroll = True
            time.sleep(0.35)

        if best_non_g1 is not None:
            # end-of-scroll fallback is always a click
            return best_non_g1, True
        return None, True

    # --------------------------
    # Public API
    # --------------------------
    def lobby(self) -> bool:
        """
        Handles the lobby where 'View Results' (white) and 'Race' (green) appear.
        Uses the unified Waiter API; no external polling loops.
        """
        # Try resolving 'View Results' and whether it is active
        view_btn = self._pick_view_results_button()
        if view_btn is None:
            # try again just in case
            time.sleep(1.5)
            view_btn = self._pick_view_results_button()

        is_view_active = False
        if view_btn is not None:
            clf = ActiveButtonClassifier.load(Settings.IS_BUTTON_ACTIVE_CLF_PATH)
            img, _ = self._collect("race_lobby_active")
            crop = crop_pil(img, view_btn["xyxy"])
            try:
                p = float(clf.predict_proba(crop))
                is_view_active = (p >= 0.51)
                logger_uma.debug("[race] View Results active probability: %.3f", p)
            except Exception:
                is_view_active = False

        if is_view_active and view_btn is not None:
            # Tap 'View Results' a couple times to clear residual screens
            self.ctrl.click_xyxy_center(view_btn["xyxy"], clicks=random.randint(1, 2))
            time.sleep(random.uniform(1.6, 2.4))
            self.ctrl.click_xyxy_center(view_btn["xyxy"], clicks=random.randint(2, 3))
            time.sleep(random.uniform(0.3, 0.5))
        else:
            # Click green 'RACE' (prefer bottom-most; OCR disambiguation if needed)
            self.waiter.click_when(
                classes=("button_green",),
                texts=("RACE",),
                prefer_bottom=True,
                timeout_s=3,
                tag="race_lobby_race_click",
            )
            time.sleep(3)
            # Reactive second confirmation. Click as soon as popup appears,
            # or bail early if the pre-race lobby appears or skip buttons show up.
            t0 = time.time()
            while (time.time() - t0) < 12.0:
                # If the confirmation 'RACE' appears, click it immediately.
                if self.waiter.try_click_once(
                    classes=("button_green",),
                    texts=("RACE",),
                    allow_greedy_click=False,
                    prefer_bottom=False,
                    tag="race_lobby_race_confirm_try",
                ):
                    time.sleep(0.12)
                # If we already transitioned into race (skip buttons), stop waiting.
                if self.waiter.seen(classes=("button_skip",), tag="race_lobby_seen_skip"):
                    break
                time.sleep(0.5)

            # Greedy skip: keep pressing while present; stop as soon as 'CLOSE' or 'NEXT' shows.
            closed_early = False
            t0 = time.time()
            while (time.time() - t0) < 12.0:
                # Early-exit conditions:
                #  - close available → click once and stop
                if self.waiter.try_click_once(
                    classes=("button_white",),
                    texts=("CLOSE",),
                    prefer_bottom=False,
                    allow_greedy_click=False,
                    tag="race_trophy_try_close",
                ):
                    closed_early = True
                    break
                #  - next visible → stop skipping; later logic will handle NEXT
                if self.waiter.seen(classes=("button_green",), tag="race_skip_probe_next"):
                    break

                # Otherwise try to click a skip on this frame.
                if self.waiter.try_click_once(classes=("button_skip",), prefer_bottom=True, tag="race_skip_try"):
                    img, dets = self._collect("race_skip_followup")
                    sk = bottom_most(find(dets, "button_skip"))
                    if sk:
                        self.ctrl.click_xyxy_center(sk["xyxy"], clicks=random.randint(3, 5))
                    continue
                time.sleep(0.12)

            if not closed_early:
                logger_uma.debug("[race] Looking for CLOSE button.")
                self.waiter.click_when(
                    classes=("button_white",),
                    texts=("CLOSE",),
                    prefer_bottom=False,
                    allow_greedy_click=False,
                    timeout_s=3,
                    tag="race_trophy",
                )

        # Check if we loss

        clicked_try_again = False
        if Settings.TRY_AGAIN_ON_FAILED_GOAL:
            # Reactive micro-window: try to click 'TRY AGAIN' quickly; otherwise don't pay a 2s timeout.
            t0 = time.time()
            while (time.time() - t0) < 2.0:
                if self.waiter.try_click_once(
                    classes=("button_green",),
                    texts=("TRY AGAIN",),
                    prefer_bottom=False,
                    allow_greedy_click=False,
                    forbid_texts=("RACE", "NEXT"),
                    tag="race_try_again_try",
                ):
                    clicked_try_again = True
                    break
                time.sleep(0.12)

        if clicked_try_again:
            logger_uma.debug("[race] Lost the race, trying again.")
            time.sleep(3)
            return self.lobby()

        else:
            # After the race/UI flow → 'NEXT' / 'OK' / 'PROCEED'
            logger_uma.debug("[race] Looking for button_green 'Next' button. Shown after race.")
            self.waiter.click_when(
                classes=("button_green",),
                texts=("NEXT", ),
                prefer_bottom=True,
                timeout_s=1.6,
                clicks=1,
                tag="race_after_flow_next",
            )

            # 'Next' special
            logger_uma.debug("[race] Looking for race_after_next special button. When Pyramid")
            
            self.waiter.click_when(
                classes=("race_after_next",),
                texts=("NEXT", ),
                prefer_bottom=True,
                timeout_s=6.0,
                clicks=random.randint(2, 4),
                tag="race_after",
            )

            # Optional: Confirm 'Next'. TODO understand when to use
            # self.waiter.click_when(
            #     classes=("button_green",),
            #     texts=("NEXT", ),
            #     prefer_bottom=False,
            #     allow_greedy_click=False,
            #     timeout_s=2.0,
            #     tag="race_after",
            # )

            logger_uma.info("[race] RaceDay flow finished.")
            return True
    # --------------------------
    # Strategy selector (End / Late / Pace / Front)
    # --------------------------
    def set_strategy(self, select_style: str, *, timeout_s: float = 2.0) -> bool:
        """
        Pick a running style inside the 'Change Strategy' modal, then press Confirm.
        `select_style` must be one of: 'end', 'late', 'pace', 'front' (case-insensitive).
        Returns True if both clicks (style + confirm) were performed.
        """
        game_img, dets = self._collect("change_style")
        elements = find(dets, "button_change")
        if elements and len(elements) == 1:
            button_change = elements[0]
            self.ctrl.click_xyxy_center(button_change["xyxy"], clicks=1)
            time.sleep(0.5)
        else:
            return False
        select_style = (select_style or "").strip().lower()
        STYLE_ORDER = ["end", "late", "pace", "front"]  # left → right in the modal
        if select_style not in STYLE_ORDER:
            logger_uma.warning("[race] Unknown select_style=%r; defaulting to 'pace'", select_style)
            select_style = "front"

        # Read current modal
        img, dets = self._collect("change_style_modal")
        whites = find(dets, "button_white") or []
        greens = find(dets, "button_green") or []
        if not whites:
            logger_uma.error("[race] set_strategy: no white buttons detected.")
            return False

        # Confirm button: pick bottom-most green if present
        confirm_btn = bottom_most(greens)

        # Cancel button: bottom-most white (y center biggest)
        def y_center(d): 
            x1, y1, x2, y2 = d["xyxy"] 
            return 0.5 * (y1 + y2)
        cancel_btn = max(whites, key=y_center)

        # Candidate style buttons = white buttons above the confirm/cancel row
        style_btns = [d for d in whites if d is not cancel_btn and y_center(d) < (y_center(cancel_btn) - 10)]
        if not style_btns:
            # fall back: all whites except the bottom-most
            style_btns = [d for d in whites if d is not cancel_btn]

        # Sort left → right by x center
        style_btns.sort(key=lambda d: (0.5 * (d["xyxy"][0] + d["xyxy"][2])))

        # We *expect* the order to be End, Late, Pace, Front (when all present).
        # If fewer are present, try OCR to map; otherwise rely on left-right order.
        idx_map = {name: i for i, name in enumerate(STYLE_ORDER)}

        chosen = None
        if len(style_btns) >= 4:
            chosen = style_btns[idx_map[select_style]]
        else:
            # OCR fallback for robustness on partial layouts
            def read_label(btn):
                x1, y1, x2, y2 = btn["xyxy"]
                # shrink a bit to avoid borders
                shrink = max(2, int(min(x2-x1, y2-y1) * 0.10))
                roi = (x1 + shrink, y1 + shrink, x2 - shrink, y2 - shrink)
                try:
                    t = (self.ocr.text(crop_pil(img, roi)) or "").strip().lower()
                except Exception:
                    t = ""
                return t

            best_btn, best_sc = None, 0.0
            for b in style_btns:
                t = read_label(b)
                # be permissive: compare against canonical label
                sc = fuzzy_ratio(t, select_style)
                if sc > best_sc:
                    best_sc, best_btn = sc, b
            # accept if somewhat confident; else fall back to order
            if best_btn is not None and best_sc >= 0.45:
                chosen = best_btn
            else:
                # fallback to the closest expected index available
                target_idx = idx_map[select_style]
                chosen = style_btns[min(target_idx, len(style_btns)-1)]

        # Click selected style
        self.ctrl.click_xyxy_center(chosen["xyxy"], clicks=1)
        time.sleep(0.15)

        # Click Confirm
        if confirm_btn is None:
            # try waiter on text if green wasn't detected
            clicked = self.waiter.click_when(
                classes=("button_green",),
                texts=("CONFIRM",),
                prefer_bottom=True,
                timeout_s=timeout_s,
                tag="race_style_confirm_text",
            )
            return bool(clicked)
        else:
            self.ctrl.click_xyxy_center(confirm_btn["xyxy"], clicks=1)
            time.sleep(0.15)
            return True

    def run(
        self,
        *,
        prioritize_g1: bool = False,
        is_g1_goal: bool = False,
        desired_race_name: Optional[str] = None,
        date_key: Optional[str] = None,
        select_style = None,
        ensure_navigation: bool = True,
        from_raceday: bool = False,
        reason: str | None = None,
    ) -> bool:
        """
        End-to-end race-day routine. If called from Lobby, set ensure_navigation=True
        (default) and we will enter the Raceday list ourselves. This allows running
        RaceFlow without involving LobbyFlow/Agent orchestration.
        Behavior when consecutive-race penalty is detected and settings forbid it:
          - if from_raceday == True → raise ConsecutiveRaceRefused
          - else → return False (let caller continue with its skip logic)
        """
        logger_uma.info(
            "[race] RaceDay begin (prioritize_g1=%s, is_g1_goal=%s)%s",
            prioritize_g1,
            is_g1_goal,
            f" | reason='{reason}'" if reason else "",
        )
        if ensure_navigation:
            try:
                _ = self._ensure_in_raceday(reason=reason, from_raceday=from_raceday)
            except ConsecutiveRaceRefused:
                logger_uma.info("[race] Returning False due to refused consecutive race (non-Raceday caller).")
                return False

        time.sleep(2)
        # 1) Pick race card; scroll if needed
        square, need_click = self._pick_race_square(
            prioritize_g1=prioritize_g1,
            is_g1_goal=is_g1_goal,
            desired_race_name=desired_race_name,
            max_scrolls=3,
            date_key=date_key
        )
        if square is None:
            
            logger_uma.debug("race square not found")
            return False

        # 2) Click the race square
        if need_click:
            self.ctrl.click_xyxy_center(square["xyxy"], clicks=1)
            time.sleep(0.2)

        # 3) Click green 'RACE' on the list (prefer bottom-most; OCR 'RACE' if needed)
        if not self.waiter.click_when(
            classes=("button_green",),
            texts=("RACE",),
            prefer_bottom=True,
            timeout_s=1,
            tag="race_list_race",
        ):
            logger_uma.warning("[race] couldn't find green 'Race' button (list).")
            return False

        # Time to popup to grow, so we don't missclassify a mini button in the animation
        time.sleep(0.7)
        # Reactive confirm of the popup (if/when it appears). Bail out if pre-race lobby is already visible.
        t0 = time.time()
        while (time.time() - t0) < 4.0:
            if abort_requested():
                logger_uma.info("[race] Abort requested before popup confirm.")
                return False
            if self.waiter.seen(classes=("button_change",), tag="race_pre_lobby_seen_early"):
                break
            if self.waiter.try_click_once(
                classes=("button_green",),
                texts=("RACE",),
                prefer_bottom=True,
                tag="race_popup_confirm_try",
            ):
                # Give a short beat for the transition; continue probing.
                time.sleep(0.2)
                break
            time.sleep(0.1)

        # 4) Wait until the pre-race lobby is actually on screen (key: 'button_change')
        time.sleep(7)
        t0 = time.time()
        max_wait = 14.0
        while (time.time() - t0) < max_wait:
            if abort_requested():
                logger_uma.info("[race] Abort requested while waiting for pre-race lobby.")
                return False
            if self.waiter.seen(classes=("button_change",), tag="race_pre_lobby_gate"):
                break
            time.sleep(0.15)

        # 5) Optional: set strategy as soon as the Change button is available (no extra sleeps)
        if select_style and self.waiter.seen(classes=("button_change",), tag="race_pre_lobby_ready"):
            logger_uma.debug(f"Setting style: {select_style}")
            self.set_strategy(select_style)
            time.sleep(3)  # wait for white buttons to dissapear

        # 6) Proceed with the result/lobby handling pipeline
        return self.lobby()
