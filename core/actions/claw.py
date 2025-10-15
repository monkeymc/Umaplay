# core/actions/claw.py
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageDraw

from core.controllers.base import IController
from core.perception.yolo.interface import IDetector
from core.settings import Settings
from core.utils.logger import logger_uma
from core.utils.yolo_objects import collect, find as det_find
from core.utils.abort import abort_requested

# Optional fallback for mouse hold if the controller lacks mouse_down/up
try:
    import pyautogui as _pg
except Exception:  # pragma: no cover
    _pg = None

Detection = Dict[str, object]
XYXY = Tuple[float, float, float, float]


# ---------------------------
# Small bbox helpers
# ---------------------------


def _center(xyxy: XYXY) -> Tuple[float, float]:
    x1, y1, x2, y2 = xyxy
    return (x1 + x2) * 0.5, (y1 + y2) * 0.5


def _wh(xyxy: XYXY) -> Tuple[float, float]:
    x1, y1, x2, y2 = xyxy
    return max(1.0, x2 - x1), max(1.0, y2 - y1)


def _ltr_sort(dets: List[Detection]) -> List[Detection]:
    return sorted(dets, key=lambda d: _center(d["xyxy"])[0])


def _iou(a: XYXY, b: XYXY) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0.0:
        return 0.0
    area_a = max(1.0, (ax2 - ax1) * (ay2 - ay1))
    area_b = max(1.0, (bx2 - bx1) * (by2 - by1))
    return inter / (area_a + area_b - inter)


# ---------------------------
# Config
# ---------------------------


@dataclass
class ClawConfig:
    # YOLO thresholds forwarded to captures
    imgsz: int = 832
    conf: float = 0.55
    iou: float = 0.45

    # Plushie selection constraints
    tall_ratio_min: float = 1.05  # H/W must be ≥ this to be “vertical”
    max_plushie_width_vs_claw: float = 0.80  # plushie_w ≤ 0.80 × claw_w
    thin_ratio_vs_claw: float = (
        0.50  # “great” = plushie_w ≤ 0.50 × claw_w (locks forever)
    )

    # Alignment / timing
    # IMPORTANT: right bias defaults to the SAME fraction as tolerance
    align_tol_frac_of_claw: float = -0.55  # tolerance band = 0.20 × claw_w
    right_bias_frac_of_claw: float = -0.55  # bias the target = +0.20 × claw_w
    max_hold_s: float = 6.5  # hard stop
    poll_interval_s: float = 0.015  # ~60 FPS
    # Prediction to compensate capture+inference latency
    latency_comp_s: float = 0.12  # seconds to look ahead when checking release
    ema_alpha: float = 0.60  # smoothing for velocity EMA
    max_pred_px: float = 120.0  # clamp prediction jump per check (safety)
    stickiness_frames: int = (
        5  # keep chosen stable this many polls before reconsidering
    )

    # Strategy
    reconsider_until_seen: int = 2  # allow early target re-picks until this many seen
    prefer_taller_margin: float = 0.10  # +10% ratio to switch when still reconsidering

    # Anti-stall safety
    min_dx_to_consider_moving_px: float = 0.7
    stall_release_after_s: float = 0.80
    rail_release_at_frac_of_width: float = 0.85

    # Near-button filtering
    near_button_iou_thr: float = 0.10
    near_button_center_px: float = 40.0

    # Debug
    debug_every_n_polls: int = 2  # save every Nth poll frame
    debug_dir_name: str = "claw_test"


class ClawGame:
    """
    Claw micro-logic:
      1) Press & hold the action button (screen coords via controller).
      2) Poll detections, track claw & plushies.
      3) Release when claw center reaches (target_center + right_bias) within tolerance.
         - If a “great” thin target is found (width ≤ thin_ratio_vs_claw × claw_w), LOCK it.
         - Ignore “last plushie” fallback once locked.
      4) Robust fallbacks: stall, rail, last-visible (only if not locked).

    Debug frames are saved to <Settings.DEBUG_DIR>/claw_test/ (or ./debug/claw_test).
    """

    def __init__(
        self,
        ctrl: IController,
        yolo_engine: IDetector,
        cfg: Optional[ClawConfig] = None,
    ) -> None:
        self.ctrl = ctrl
        self.yolo_engine = yolo_engine
        self.cfg = cfg or ClawConfig()
        self._dbg_counter = 0
        # Build debug directory once
        base = getattr(Settings, "DEBUG_DIR", None)
        base = Path(base) if base else Path("debug")
        self._dbg_dir = base / self.cfg.debug_dir_name
        os.makedirs(self._dbg_dir, exist_ok=True)

    # ---------------------------
    # Low-level press/hold helpers
    # ---------------------------

    def _down(self, x_screen: int, y_screen: int) -> None:
        for attr in ("mouse_down", "touch_down", "press_down", "pointer_down"):
            if hasattr(self.ctrl, attr):
                getattr(self.ctrl, attr)(x_screen, y_screen)
                return
        if _pg is not None:
            try:
                _pg.mouseDown(x=x_screen, y=y_screen)
                return
            except Exception:
                pass
        self.ctrl.move_to(x_screen, y_screen)
        logger_uma.warning("[claw] No down() available; degraded (no true hold).")

    def _up(self, x_screen: int, y_screen: int) -> None:
        for attr in ("mouse_up", "touch_up", "press_up", "pointer_up"):
            if hasattr(self.ctrl, attr):
                getattr(self.ctrl, attr)(x_screen, y_screen)
                return
        if _pg is not None:
            try:
                _pg.mouseUp(x=x_screen, y=y_screen)
                return
            except Exception:
                pass

    # ---------------------------
    # Selection & filtering
    # ---------------------------

    def _exclude_near_button(
        self, plushies: List[Detection], btn_xyxy: XYXY
    ) -> List[Detection]:
        bx1, by1, bx2, by2 = btn_xyxy
        bcx, bcy = (bx1 + bx2) * 0.5, (by1 + by2) * 0.5
        out: List[Detection] = []
        for d in plushies:
            x1, y1, x2, y2 = d["xyxy"]
            cx, cy = (x1 + x2) * 0.5, (y1 + y2) * 0.5
            if _iou(d["xyxy"], btn_xyxy) > self.cfg.near_button_iou_thr:
                continue
            if (
                abs(cx - bcx) < self.cfg.near_button_center_px
                and abs(cy - bcy) < self.cfg.near_button_center_px
            ):
                continue
            out.append(d)
        return out

    def _filter_viable(
        self, plushies: List[Detection], claw_xyxy: XYXY
    ) -> List[Detection]:
        """Keep plushies that are vertical enough and not wider than the claw."""
        cw, _ = _wh(claw_xyxy)
        good: List[Detection] = []
        for p in plushies:
            pw, ph = _wh(p["xyxy"])
            if (
                (ph / pw) >= self.cfg.tall_ratio_min
                and pw <= self.cfg.max_plushie_width_vs_claw * cw
            ):
                good.append(p)
        return _ltr_sort(good)

    def _choose_best_target(
        self,
        candidates: List[Detection],
        claw_xyxy: XYXY,
        min_x_gate: float,
        seen_count: int,
        locked: Optional[Detection],
    ) -> Optional[Detection]:
        """
        If we already locked a thin target, keep it.
        Else pick the first viable ahead of the claw (>= gate). While still exploring,
        allow switching to a clearly taller one (+prefer_taller_margin).
        """
        if locked is not None:
            return locked

        if not candidates:
            return None

        cx_claw, _ = _center(claw_xyxy)
        gate = max(min_x_gate, cx_claw)
        ahead = [p for p in candidates if _center(p["xyxy"])[0] >= gate]
        if not ahead:
            return None

        choice = ahead[0]
        if seen_count < self.cfg.reconsider_until_seen and len(ahead) >= 2:
            w0, h0 = _wh(choice["xyxy"])
            r0 = h0 / w0 if w0 > 0 else 0.0
            for p in ahead[1:]:
                w1, h1 = _wh(p["xyxy"])
                r1 = h1 / w1 if w1 > 0 else 0.0
                if r1 >= r0 + self.cfg.prefer_taller_margin:
                    choice, r0 = p, r1
        return choice

    # ---------------------------
    # Debug helpers
    # ---------------------------

    def _save_debug(
        self,
        pil_img: Image.Image,
        *,
        btn: Optional[Detection] = None,
        claw: Optional[Detection] = None,
        plushies: Optional[List[Detection]] = None,
        viable: Optional[List[Detection]] = None,
        chosen: Optional[Detection] = None,
        locked: Optional[Detection] = None,
        notes: str = "",
        suffix: str = "",
        cx_claw: Optional[float] = None,
        cx_pred: Optional[float] = None,
        target_x: Optional[float] = None,
        release_x: Optional[float] = None,
    ) -> None:
        """Draws colored boxes and saves a frame to the debug directory."""
        try:
            img = pil_img.copy()
            draw = ImageDraw.Draw(img)

            def _rect(xyxy, color, width=3):
                x1, y1, x2, y2 = [int(v) for v in xyxy]
                draw.rectangle([x1, y1, x2, y2], outline=color, width=width)

            # Button (yellow)
            if btn:
                _rect(btn["xyxy"], (255, 215, 0), 3)

            # Claw (blue)
            if claw:
                _rect(claw["xyxy"], (65, 105, 225), 3)

            # All plushies (light red)
            if plushies:
                for d in plushies:
                    _rect(d["xyxy"], (255, 99, 71), 2)

            # Viable (green)
            if viable:
                for d in viable:
                    _rect(d["xyxy"], (50, 205, 50), 3)

            # Locked (thick green)
            if locked:
                _rect(locked["xyxy"], (0, 255, 0), 5)

            # Chosen target (thick red)
            if chosen:
                _rect(chosen["xyxy"], (255, 0, 0), 5)

            # Lines for numeric reasoning (predictions / thresholds)
            def _vline(x, color, w=2):
                if x is None:
                    return
                X = int(x)
                draw.line([(X, 0), (X, img.height)], fill=color, width=w)

            _vline(cx_claw, (135, 206, 250), 2)  # light blue: current claw center
            _vline(cx_pred, (30, 144, 255), 2)  # dodger blue: predicted claw center
            _vline(target_x, (255, 165, 0), 2)  # orange: biased target x
            _vline(release_x, (124, 252, 0), 2)  # lawn green: release threshold

            if notes:
                draw.text((10, 10), notes, fill=(255, 255, 255))

            fname = (
                f"claw_{self._dbg_counter:03d}{('_' + suffix) if suffix else ''}.png"
            )
            img.save(self._dbg_dir / fname)
        except Exception as e:
            logger_uma.debug("[claw] debug save failed: %s", e)
        finally:
            self._dbg_counter += 1

    # ---------------------------
    # Main loop
    # ---------------------------

    def play_once(self, *, tag_prefix: str = "claw", try_idx: int = 1) -> bool:
        """
        1) Snapshot → find button & claw (local coords).
        2) Press & hold at button (screen coords).
        3) Poll YOLO, track claw + plushies, compensate inference latency, and
        release when the *predicted* claw center reaches the (biased) target
        within tolerance. Never switch away from a locked “thin” target.
        4) Robust fallbacks (stall / rail). "Last plushie" fallback only if we never
        locked or chose a target.
        """
        # -------------------- initial capture --------------------
        img, dets = collect(
            self.yolo_engine,
            imgsz=self.cfg.imgsz,
            conf=self.cfg.conf,
            iou=self.cfg.iou,
            tag=f"{tag_prefix}_init",
        )
        btns = det_find(dets, "button_claw_action")
        claws = det_find(dets, "claw")
        if not btns or not claws:
            logger_uma.warning("[claw] Missing button or claw on screen.")
            return False

        btn = _ltr_sort(btns)[0]
        claw_xyxy = claws[0]["xyxy"]

        # Press & hold at the button (convert local → SCREEN coords via controller).
        bx_screen, by_screen = self.ctrl.center_from_xyxy(btn["xyxy"])
        self._down(bx_screen, by_screen)
        t0 = time.time()

        # -------------------- state --------------------
        seen_plushies: List[Detection] = []
        min_target_x = _center(claw_xyxy)[
            0
        ]  # Never consider targets left of the starting claw X
        last_cx = min_target_x
        last_move_ts = t0
        last_ts = t0
        vx_ema = 0.0  # EMA of horizontal velocity (px/s)
        loop_dt_ema = (
            self.cfg.latency_comp_s
        )  # EMA of loop latency (sec), seeds with cfg

        locked_best: Optional[Detection] = None  # Width ≤ thin_ratio_vs_claw × claw_w
        chosen: Optional[Detection] = (
            None  # Current candidate (can change until locked)
        )
        sticky_left = 0  # Avoid rapid flicker (frames)

        # Try-aware tuning: later tries release a bit earlier
        # - more look-ahead, bigger tolerance, slightly smaller right-bias
        try_idx = max(1, min(3, int(try_idx)))
        lookahead_scale = {1: 1.00, 2: 1.25, 3: 1.50}[try_idx]
        tol_scale = {1: 1.00, 2: 1.10, 3: 1.20}[try_idx]
        bias_scale = {1: 1.00, 2: 0.90, 3: 0.80}[try_idx]

        # Rail safety (if controller exposes client bbox)
        rail_right_limit: Optional[float] = None

        # First debug frame
        self._save_debug(
            img,
            btn=btn,
            claw=claws[0],
            plushies=det_find(dets, "claw_plushie"),
            notes=f"INIT (try={try_idx})",
            suffix="init",
        )

        # -------------------- main loop --------------------
        poll_idx = 0
        try:
            while True:
                if abort_requested():
                    logger_uma.info("[claw] Abort requested; releasing immediately.")
                    break
                # Hard stop
                now = time.time()
                if (now - t0) >= self.cfg.max_hold_s:
                    logger_uma.info("[claw] Max hold reached; releasing.")
                    self._save_debug(
                        img,
                        btn=btn,
                        claw={"xyxy": claw_xyxy},
                        chosen=chosen,
                        locked=locked_best,
                        notes="TIMEOUT",
                        suffix="timeout",
                    )
                    break

                # Capture + detect (measure loop latency)
                t_snap = time.time()
                img, dets = collect(
                    self.yolo_engine,
                    imgsz=self.cfg.imgsz,
                    conf=self.cfg.conf,
                    iou=self.cfg.iou,
                    tag=f"{tag_prefix}_poll",
                )
                loop_dt = max(1e-3, time.time() - t_snap)
                loop_dt_ema = 0.6 * loop_dt + 0.4 * loop_dt_ema  # smooth loop latency

                # Claw
                claws = det_find(dets, "claw")
                if not claws:
                    # Brief loss: keep holding; log every once in a while
                    if (poll_idx % 10) == 0:
                        logger_uma.debug(
                            "[claw] claw not detected at poll=%d; loop_dt=%.3f",
                            poll_idx,
                            loop_dt,
                        )
                    time.sleep(self.cfg.poll_interval_s)
                    poll_idx += 1
                    continue

                claw_xyxy = claws[0]["xyxy"]
                cx_claw, _ = _center(claw_xyxy)
                cw, _ = _wh(claw_xyxy)

                # Velocity EMA
                dt = max(1e-3, now - last_ts)
                vx_inst = (cx_claw - last_cx) / dt
                if abs(vx_inst) < 3000.0:  # guard against spikes
                    vx_ema = (
                        self.cfg.ema_alpha * vx_inst
                        + (1.0 - self.cfg.ema_alpha) * vx_ema
                    )
                last_ts = now

                # Movement / stall
                if (cx_claw - last_cx) >= self.cfg.min_dx_to_consider_moving_px:
                    last_move_ts = now
                    last_cx = cx_claw
                elif (now - last_move_ts) >= self.cfg.stall_release_after_s:
                    logger_uma.info(
                        "[claw] Movement stall (vx≈%.1f px/s, dt=%.2fs); releasing.",
                        vx_ema,
                        now - last_move_ts,
                    )
                    self._save_debug(
                        img,
                        btn=btn,
                        claw={"xyxy": claw_xyxy},
                        chosen=chosen,
                        locked=locked_best,
                        notes="STALL",
                        suffix="stall",
                        cx_claw=cx_claw,
                    )
                    break

                # Plushies (exclude those near/over the button)
                plush_all_raw = det_find(dets, "claw_plushie")
                plush_all = self._exclude_near_button(plush_all_raw, btn["xyxy"])

                # Track unique by center X
                for p in plush_all:
                    cx_p, _ = _center(p["xyxy"])
                    if not any(
                        abs(cx_p - _center(q["xyxy"])[0]) < 6.0 for q in seen_plushies
                    ):
                        seen_plushies.append(p)

                # Viable vs. fallback candidates
                viable = self._filter_viable(plush_all, claw_xyxy)
                candidates = viable if viable else _ltr_sort(plush_all)

                # Lock a thin target (width ≤ thin_ratio × claw_w) once and forever
                if locked_best is None:
                    for p in candidates:
                        pw, _ = _wh(p["xyxy"])
                        if pw <= self.cfg.thin_ratio_vs_claw * cw:
                            locked_best = p
                            sticky_left = max(sticky_left, self.cfg.stickiness_frames)
                            logger_uma.info(
                                "[claw] LOCK thin target: cx=%.1f  pw=%.1f  cw=%.1f  (vx≈%.1f px/s)",
                                _center(p["xyxy"])[0],
                                pw,
                                cw,
                                vx_ema,
                            )
                            self._save_debug(
                                img,
                                btn=btn,
                                claw={"xyxy": claw_xyxy},
                                plushies=plush_all,
                                viable=candidates,
                                chosen=p,
                                locked=p,
                                notes="LOCK THIN",
                                suffix="lock",
                                cx_claw=cx_claw,
                            )
                            break

                # Choose/refresh target (respects lock)
                new_choice = self._choose_best_target(
                    candidates,
                    claw_xyxy,
                    min_target_x,
                    seen_count=len(seen_plushies),
                    locked=locked_best,
                )
                if chosen is None and new_choice is not None:
                    chosen = new_choice
                    sticky_left = self.cfg.stickiness_frames
                    logger_uma.info(
                        "[claw] CHOOSE target: cx=%.1f  (seen=%d, vx≈%.1f)",
                        _center(chosen["xyxy"])[0],
                        len(seen_plushies),
                        vx_ema,
                    )
                elif (
                    new_choice is not None and sticky_left <= 0 and locked_best is None
                ):
                    # Allow switching only after the sticky window expires
                    prev_cx = _center(chosen["xyxy"])[0] if chosen else None
                    chosen = new_choice
                    sticky_left = self.cfg.stickiness_frames
                    logger_uma.info(
                        "[claw] SWITCH target: prev_cx=%s → cx=%.1f (seen=%d)",
                        f"{prev_cx:.1f}" if prev_cx is not None else "None",
                        _center(chosen["xyxy"])[0],
                        len(seen_plushies),
                    )
                else:
                    sticky_left = max(0, sticky_left - 1)

                # Rebind chosen to the nearest current detection by center-X (fight flicker/offset)
                if chosen is not None and plush_all:
                    cx_ref, _ = _center(chosen["xyxy"])
                    nearest = min(
                        plush_all,
                        key=lambda d: abs(_center(d["xyxy"])[0] - cx_ref),
                        default=None,
                    )
                    if nearest is not None:
                        chosen = nearest

                # ------------- release check (predictive) -------------
                released = False
                if chosen is not None:
                    cx_target, _ = _center(chosen["xyxy"])

                    # Tolerance / bias (try-aware scaling)
                    align_tol = (self.cfg.align_tol_frac_of_claw * tol_scale) * cw
                    right_bias = (self.cfg.right_bias_frac_of_claw * bias_scale) * cw
                    target_x = cx_target + right_bias

                    # Look-ahead time = max(loop latency EMA, cfg latency) * try-scale
                    look_ahead = (
                        max(loop_dt_ema, self.cfg.latency_comp_s) * lookahead_scale
                    )
                    cx_pred = cx_claw + max(
                        -self.cfg.max_pred_px,
                        min(self.cfg.max_pred_px, vx_ema * look_ahead),
                    )

                    release_x = target_x - align_tol
                    decision = cx_pred >= release_x

                    logger_uma.debug(
                        "[claw] chk poll=%d | cx=%.1f cx_pred=%.1f vx≈%.1f | tx=%.1f tol=%.1f bias=%.1f "
                        "| look=%.3fs (loop=%.3fs) | decide=%s",
                        poll_idx,
                        cx_claw,
                        cx_pred,
                        vx_ema,
                        target_x,
                        align_tol,
                        right_bias,
                        look_ahead,
                        loop_dt_ema,
                        decision,
                    )

                    if decision:
                        self._save_debug(
                            img,
                            btn=btn,
                            claw={"xyxy": claw_xyxy},
                            plushies=plush_all,
                            viable=candidates,
                            chosen=chosen,
                            locked=locked_best,
                            notes=(
                                f"RELEASE align try={try_idx} (cx={cx_claw:.1f}, cxp={cx_pred:.1f}, "
                                f"tx={target_x:.1f}, tol={align_tol:.1f})"
                            ),
                            suffix="release_align",
                            cx_claw=cx_claw,
                            cx_pred=cx_pred,
                            target_x=target_x,
                            release_x=release_x,
                        )
                        released = True

                # ------------- fallbacks -------------
                if not released:
                    # Only if we never locked/selected a target
                    if (
                        locked_best is None
                        and chosen is None
                        and len(candidates) > 0
                        and len(seen_plushies) >= 3
                    ):
                        x1_l, _, x2_l, _ = candidates[-1]["xyxy"]
                        align_tol = (self.cfg.align_tol_frac_of_claw * tol_scale) * cw
                        right_bias = (
                            self.cfg.right_bias_frac_of_claw * bias_scale
                        ) * cw

                        look_ahead = (
                            max(loop_dt_ema, self.cfg.latency_comp_s) * lookahead_scale
                        )
                        cx_pred = cx_claw + max(
                            -self.cfg.max_pred_px,
                            min(self.cfg.max_pred_px, vx_ema * look_ahead),
                        )

                        release_x = (x2_l + right_bias) - align_tol
                        if cx_pred >= release_x:
                            logger_uma.info("[claw] RELEASE last plushie fallback.")
                            self._save_debug(
                                img,
                                btn=btn,
                                claw={"xyxy": claw_xyxy},
                                plushies=plush_all,
                                viable=candidates,
                                chosen=None,
                                locked=None,
                                notes=(
                                    f"RELEASE last (cx={cx_claw:.1f}, cxp={cx_pred:.1f}, rx={release_x:.1f})"
                                ),
                                suffix="fallback_last",
                                cx_claw=cx_claw,
                                cx_pred=cx_pred,
                                release_x=release_x,
                            )
                            released = True

                # Rail safety
                if (
                    not released
                    and rail_right_limit is not None
                    and cx_claw >= rail_right_limit
                ):
                    logger_uma.info("[claw] Near right rail; releasing.")
                    self._save_debug(
                        img,
                        btn=btn,
                        claw={"xyxy": claw_xyxy},
                        chosen=chosen,
                        locked=locked_best,
                        notes="RAIL",
                        suffix="rail",
                        cx_claw=cx_claw,
                    )
                    released = True

                # Periodic debug frame
                if (poll_idx % max(1, self.cfg.debug_every_n_polls)) == 0:
                    cx_target_dbg = None
                    align_tol_dbg = None
                    right_bias_dbg = None
                    target_x_dbg = None
                    release_x_dbg = None
                    if chosen is not None:
                        cx_target_dbg = _center(chosen["xyxy"])[0]
                        align_tol_dbg = (
                            self.cfg.align_tol_frac_of_claw * tol_scale
                        ) * cw
                        right_bias_dbg = (
                            self.cfg.right_bias_frac_of_claw * bias_scale
                        ) * cw
                        target_x_dbg = cx_target_dbg + right_bias_dbg
                        release_x_dbg = target_x_dbg - align_tol_dbg
                    cx_pred_dbg = cx_claw + max(
                        -self.cfg.max_pred_px,
                        min(
                            self.cfg.max_pred_px,
                            vx_ema
                            * max(loop_dt_ema, self.cfg.latency_comp_s)
                            * lookahead_scale,
                        ),
                    )
                    self._save_debug(
                        img,
                        btn=btn,
                        claw={"xyxy": claw_xyxy},
                        plushies=plush_all,
                        viable=candidates,
                        chosen=chosen,
                        locked=locked_best,
                        notes=(
                            f"poll {poll_idx} | seen={len(seen_plushies)} | vx≈{vx_ema:.1f} | "
                            f"loop_dt={loop_dt:.3f}/{loop_dt_ema:.3f}"
                        ),
                        suffix="poll",
                        cx_claw=cx_claw,
                        cx_pred=cx_pred_dbg,
                        target_x=target_x_dbg,
                        release_x=release_x_dbg,
                    )

                if released:
                    break

                poll_idx += 1
                # optional tiny sleep to free CPU; YOLO usually dominates latency anyway
                # time.sleep(self.cfg.poll_interval_s)

        finally:
            # Always release exactly where we pressed initially (screen coords)
            self._up(bx_screen, by_screen)

        ok = chosen is not None
        if ok:
            cx, _ = _center(chosen["xyxy"])
            logger_uma.debug(
                "[claw] Released over target (cx=%.1f, seen=%d, try=%d).",
                cx,
                len(seen_plushies),
                try_idx,
            )
        else:
            logger_uma.debug(
                "[claw] Released without a confirmed target (timeout/stall/fallback)."
            )
        return ok
