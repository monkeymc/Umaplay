# core/perception/extractors.py
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple
from PIL import Image

from core.perception.analyzers.mood import mood_label
from core.perception.ocr.interface import OCRInterface
from core.perception.analyzers.energy_bar import energy_from_bar_crop
from core.settings import Settings
from core.types import DetectionDict
from core.constants import (
    MOOD_MAP,
    CLASS_UI_MOOD,
    CLASS_UI_TURNS,
    CLASS_UI_STATS,
    CLASS_UI_SKILLS_PTS,
    CLASS_UI_GOAL,
    CLASS_LOBBY_INFIRMARY,
)
from core.utils.geometry import crop_pil, xyxy_int
from core.utils.logger import logger_uma
from core.perception.is_button_active import ActiveButtonClassifier
from PIL import ImageStat

from core.utils.preprocessors import (
    tighten_to_pill,
    career_date_crop_box,
    preprocess_digits,
    read_date_pill_robust,
)
from core.utils.text import fuzzy_contains


# ------------------------------
# Common helper
# ------------------------------
def find_best(
    parsed_objects_screen: List[DetectionDict], name: str, conf_min: float = 0.50
) -> Optional[DetectionDict]:
    """
    Pick the highest-confidence detection of a given class name.
    """
    cands = [
        d for d in parsed_objects_screen if d["name"] == name and d["conf"] >= conf_min
    ]
    if not cands:
        return None
    return max(cands, key=lambda d: d["conf"])


# ------------------------------
# Mood
# ------------------------------
def extract_mood(
    ocr: OCRInterface,
    game_img: Image.Image,
    parsed_objects_screen: List[DetectionDict],
    *,
    conf_min: float = 0.20,
    pad: int = 1,
) -> Tuple[str, int]:
    """
    Returns (mood_text, mood_score). If missing, returns ("UNKNOWN", -1).
    """
    d = find_best(parsed_objects_screen, CLASS_UI_MOOD, conf_min=0.5)
    if not d:
        return "UNKNOWN", -1
    # 1) Color-first classification with OCR fallback (handled inside mood_label)
    label = mood_label(ocr, game_img, d["xyxy"])
    if label in MOOD_MAP:
        return label, MOOD_MAP[label]

    logger_uma.debug("Couldn't determine mood by color, using OCR")
    # 2) Keep legacy OCR-based fallback if label is unknown (paranoid safety)
    crop = crop_pil(game_img, d["xyxy"], pad)
    text = (ocr.text(crop) or "").upper()
    for k in ("AWFUL", "BAD", "NORMAL", "GOOD", "GREAT"):
        if k in text:
            return k, MOOD_MAP[k]

    # 3) Fuzzy last resort
    best_text, best_idx, best_ratio = "UNKNOWN", -1, -1.0
    for k in ("AWFUL", "BAD", "NORMAL", "GOOD", "GREAT"):
        contains, ratio = fuzzy_contains(k, text, threshold=conf_min, return_ratio=True)
        if contains and ratio > best_ratio:
            best_ratio = ratio
            best_text = k
            best_idx = MOOD_MAP[k]

    if best_idx == -1:
        logger_uma.warning(f"[mood] No mood detected for OCR text: {text!r}")
    return best_text, best_idx


# ------------------------------
# Turns
# ------------------------------
def extract_turns(
    ocr: OCRInterface,
    game_img: Image.Image,
    parsed_objects_screen: List[DetectionDict],
    *,
    conf_min: float = 0.20,
) -> int:
    """
    Returns turns_left (1..30) or -1 if not recognized.
    Uses light preprocessing only when the full frame is small (H < 900).
    """
    d = find_best(parsed_objects_screen, CLASS_UI_TURNS, conf_min=conf_min)
    if not d:
        return -1

    # --- keep your current gap logic ---
    x1, y1, x2, y2 = d["xyxy"]
    element_height = abs(y2 - y1)
    gap = element_height * 0.20
    y1 = y1 + gap
    y2 = y2 - gap

    turns_img = crop_pil(game_img, (x1, y1, x2, y2), pad=0)

    # First, try raw (fast path)
    turns_left = ocr.digits(turns_img)
    if 1 <= turns_left <= 30:
        return turns_left

    # Frame-aware preprocessing (only when the overall image is small)
    use_pp = game_img.height < 900
    if not use_pp:
        if turns_left == -1:
            logger_uma.warning("Unrecognized turns")
        return turns_left

    # Light PP for single, chunky glyphs (avoid heavy top cropping!)
    # - small top drop
    # - no right trim
    # - focus largest CC to auto-tighten around the digit
    try:
        final_pil, _steps = preprocess_digits(
            turns_img,
            scale=4,
            drop_top_frac=0.12,  # was ~0.35; too aggressive -> '2' looked like a 'Z'
            trim_right_frac=0.00,
            dilate_iters=0,  # keep strokes thin for single digits
            focus_largest_cc=True,
        )
        # OCR with a loose text fallback that maps I/l/| -> 1 (helps ultra-thin '1')
        turns_pp = ocr.digits(final_pil)
        if not (1 <= turns_pp <= 30):
            loose_txt = ocr.text(final_pil, min_conf=0.0) or ""
            m = re.search(r"[0-9Il|]{1,2}", loose_txt)
            if m:
                tok = m.group(0).replace("I", "1").replace("l", "1").replace("|", "1")
                try:
                    turns_pp = int(tok)
                except ValueError:
                    pass
        if 1 <= turns_pp <= 30:
            return turns_pp
    except Exception as e:
        logger_uma.debug("Turns PP failed: %s", e)

    if turns_left == -1:
        logger_uma.warning("Unrecognized turns")
    return turns_left


# ------------------------------
# Turns
# ------------------------------


# ------------------------------
# Career date (raw OCR)
# ------------------------------
def extract_career_date(
    ocr: OCRInterface,
    game_img: Image.Image,
    parsed_objects_screen: List[DetectionDict],
    *,
    conf_min: float = 0.20,
) -> str:
    """
    Return the raw text inside the career-date pill; empty string if not found.
    """
    d = find_best(parsed_objects_screen, CLASS_UI_TURNS, conf_min=conf_min)
    if not d:
        return ""
    # Use shared helper so we can also draw the crop in notebooks.
    # 1) Robust box for the banner region above Turns
    rx1, ry1, rx2, ry2 = career_date_crop_box(game_img, d["xyxy"])
    banner = game_img.crop((rx1, ry1, rx2, ry2))

    #    Heuristic: in HSV, the pill is a bright, low-saturation blob near the lower half.
    pill_box = tighten_to_pill(banner)
    cx1, cy1, cx2, cy2 = pill_box
    cx1, cy1, cx2, cy2 = (
        rx1 + cx1,
        ry1 + cy1,
        rx1 + cx2,
        ry1 + cy2,
    )  # map to full image coords (for debugging)
    pill = banner.crop((pill_box))

    # 3) OCR the pill with low-res friendly pre-processing and choose best candidate
    career_date_raw = read_date_pill_robust(ocr, pill)
    return (career_date_raw or "").strip()


# ------------------------------
# Stats (SPD/STA/PWR/GUTS/WIT)
# ------------------------------
def _parse_stat_segment(ocr: OCRInterface, seg_img: Image.Image) -> int:
    """
    Segment typically looks like `C 416 / 1200`.
    Strategy:
      1) Try a digits-only fast path using low confidence threshold (min_conf=0.0).
      2) If that fails, fall back to your robust regex salvage (kept intact).
    """
    import re

    # ---- 1) fast path: keep low-confidence chars, then strip to digits ----
    try:
        raw_loose = ocr.text(seg_img, min_conf=0.0) or ""
        digits_only = re.sub(r"[^\d]", "", raw_loose).strip()
        if 1 <= len(digits_only) <= 4:
            val_fast = int(digits_only)
            if 90 <= val_fast <= 1200:
                return val_fast
            # if it's clearly out of range (e.g., 2034), fall through to salvage
    except Exception:
        pass

    # ---- 2) original robust salvage path (unchanged) ----
    raw = ocr.text(seg_img) or ""
    # Normalize and remove the capacity part (tolerant to whitespace)
    t = re.sub(r"[\s,.:;]+", "", raw)
    t = re.sub(r"/\s*1200", "", t, flags=re.IGNORECASE)

    # Prefer a compact token that is digits with an optional trailing letter
    # (1–4 digits because values ∈ [90..1200])
    m = re.search(r"(\d{1,4}[A-Za-z]?)", t)
    if not m:
        # Last-chance: any digits in the string
        m = re.search(r"(\d+)", t)
        if not m:
            return -1
    token = m.group(1)

    # Was there a trailing letter?
    trailing_letter = token[-1].isalpha()
    trailing_char = token[-1] if trailing_letter else ""

    # Common OCR confusions -> digits
    MAP = {
        "O": "0",
        "o": "0",
        "D": "0",
        "Q": "0",
        "I": "1",
        "l": "1",
        "|": "1",
        "!": "1",
        "Z": "2",
        "S": "5",
        "s": "5",
        "E": "6",
        "e": "6",
        "G": "6",
        "B": "8",
        "g": "9",
        "q": "9",
        "A": "4",
    }

    out: list[str] = []
    for i, ch in enumerate(token):
        if ch.isdigit():
            out.append(ch)
        else:
            mapped = MAP.get(ch, MAP.get(ch.upper()))
            if mapped is not None:
                out.append(mapped)
            else:
                if i == len(token) - 1:  # trailing unknown letter
                    out.append("")  # will fill with '0' below

    if trailing_letter and (not out or not out[-1].isdigit()):
        out[-1:] = ["0"]
        logger_uma.warning(
            "Stat OCR had trailing letter '%s' → using 0 (raw='%s')", trailing_char, raw
        )

    digits = "".join(out)
    if not digits:
        return -1

    try:
        val = int(digits)
    except Exception:
        nums = re.findall(r"\d+", raw)
        val = int(nums[0]) if nums else -1
        if val == -1:
            return -1

    # Clamp to valid range
    if val > 1200:
        # TODO: improve when val is higher than 2k
        val = -1
    if val < 90:
        if not trailing_letter:
            logger_uma.debug(
                "Stat %s < 90 without trailing letter; treating as unrecognized (raw='%s')",
                val,
                raw,
            )
        val = -1

    return val


def extract_stats(
    ocr: OCRInterface,
    game_img: Image.Image,
    parsed_objects_screen: List[DetectionDict],
    *,
    conf_min: float = 0.20,
    with_segments: bool = False,
) -> Dict[str, int] | Dict[str, Dict[str, object]]:
    """
    Returns dict:
      if with_segments=False (default):
        {"SPD":103, "STA":95, "PWR":88, "GUTS":76, "WIT":82}
      if with_segments=True:
        {"SPD":{"value":103,"seg":<PIL>}, ...}

    Smart bits:
      • If the *full* input image is small (height < 900), preprocess each
        stat segment before OCR to improve low-res robustness.
      • Keeps your y/x offsets exactly as requested.
    """
    d = find_best(parsed_objects_screen, CLASS_UI_STATS, conf_min=conf_min)
    if not d:
        return {"SPD": -1, "STA": -1, "PWR": -1, "GUTS": -1, "WIT": -1}

    stats_img = crop_pil(game_img, d["xyxy"], pad=(0, 0))
    W, H = stats_img.size

    # segmentation geometry (kept as you set)
    k = 5
    segW = max(1, W // k)
    keys = ["SPD", "STA", "PWR", "GUTS", "WIT"]
    y_top_offset = 0.27
    y_bottom_offset = 0.74
    x_left_offset = 0.45
    x_right_offset = 0.10

    # Decide whether to run the preprocessor based on *full* image height
    full_h = game_img.size[1]
    use_pp = full_h < 900

    def _crop_seg(i: int, last: bool) -> Image.Image:
        x1 = int((i * segW) + segW * x_left_offset)
        x2 = W if last else int((i + 1) * segW)
        x2 = int(x2 + segW * x_right_offset)  # keep your extra right margin
        return stats_img.crop((x1, int(H * y_top_offset), x2, int(H * y_bottom_offset)))

    if with_segments:
        out: Dict[str, Dict[str, object]] = {}
        for i, key in enumerate(keys):
            seg = _crop_seg(i, last=(i == k - 1))

            # Preprocess only for small full-frame captures
            seg_for_ocr = seg
            if use_pp:
                try:
                    seg_for_ocr, _ = preprocess_digits(
                        seg,
                        scale=3,
                        drop_top_frac=0.35,
                        trim_right_frac=0.15,
                        dilate_iters=1,
                        focus_largest_cc=False,
                    )
                except Exception as e:
                    logger_uma.debug(
                        f"[stats] preprocess_digits failed ({e}); using raw segment"
                    )

            out[key] = {"value": _parse_stat_segment(ocr, seg_for_ocr), "seg": seg}
        return out

    out2: Dict[str, int] = {}
    for i, key in enumerate(keys):
        seg = _crop_seg(i, last=(i == k - 1))

        seg_for_ocr = seg
        if use_pp:
            try:
                seg_for_ocr, _ = preprocess_digits(
                    seg,
                    scale=3,
                    drop_top_frac=0.35,
                    trim_right_frac=0.15,
                    dilate_iters=1,
                    focus_largest_cc=False,
                )
            except Exception as e:
                logger_uma.debug(
                    f"[stats] preprocess_digits failed ({e}); using raw segment"
                )

        out2[key] = _parse_stat_segment(ocr, seg_for_ocr)

    return out2


# ------------------------------
# Infirmary ON/OFF
# ------------------------------


def extract_infirmary_on(
    game_img: Image.Image,
    parsed_objects_screen: List[DetectionDict],
    *,
    conf_min: float = 0.20,
    threshold: float = 0.55,
) -> bool:
    """
    If a joblib classifier exists (Settings.IS_BUTTON_ACTIVE_CLF_PATH),
    use it; otherwise fall back to a HSV heuristic.
    """
    d = find_best(parsed_objects_screen, CLASS_LOBBY_INFIRMARY, conf_min=conf_min)
    if not d:
        return False

    crop = crop_pil(game_img, d["xyxy"], pad=0)

    # Try model first
    if Settings.IS_BUTTON_ACTIVE_CLF_PATH.exists():
        try:
            clf = ActiveButtonClassifier.load(Settings.IS_BUTTON_ACTIVE_CLF_PATH)
            p = float(clf.predict_proba(crop))
            return p >= threshold
        except Exception as e:
            logger_uma.debug("infirmary model failed, fallback to heuristic: %s", e)

    # HSV heuristic fallback
    gray = crop.convert("L")
    avg = ImageStat.Stat(gray).mean[0]
    return avg > 150


# ------------------------------
# Skill points
# ------------------------------
def extract_skill_points(
    ocr: OCRInterface,
    game_img: Image.Image,
    parsed_objects_screen: List[DetectionDict],
    *,
    conf_min: float = 0.20,
) -> int:
    """
    Returns the skill points integer (0..9999), or -1 if not found.
    Uses digits-focused preprocessing only when the full frame is small (H < 900).
    """
    d = find_best(parsed_objects_screen, CLASS_UI_SKILLS_PTS, conf_min=conf_min)
    if not d:
        return -1

    crop = crop_pil(game_img, d["xyxy"], pad=0)

    # Fast path
    v = ocr.digits(crop)
    if 0 <= v <= 9999:
        return v

    # Loose fallback before PP (handles thin digits without PP cost on big frames)
    if v == -1:
        loose_txt = ocr.text(crop, min_conf=0.0) or ""
        m = re.search(r"\d{1,4}", loose_txt)
        if m:
            try:
                return int(m.group(0))
            except ValueError:
                pass

    # Frame-aware PP (small screens)
    if game_img.height >= 900:
        return v

    try:
        # Similar to what worked in your tests: remove cyan header, slight right trim,
        # then let Paddle read only the digits.
        final_pil, _steps = preprocess_digits(
            crop,
            scale=3,
            drop_top_frac=0.30,
            trim_right_frac=0.15,
            dilate_iters=1,
            focus_largest_cc=True,  # helps isolate the digits block
        )
        v2 = ocr.digits(final_pil)
        if 0 <= v2 <= 9999:
            return v2
        return v2
    except Exception as e:
        logger_uma.debug("SkillPts PP failed: %s", e)
        return v


# ------------------------------
# Goal text
# ------------------------------
def extract_goal_text(
    ocr: OCRInterface,
    game_img: Image.Image,
    parsed_objects_screen: List[DetectionDict],
    *,
    conf_min: float = 0.20,
) -> str:
    """
    Returns the goal text as-is (may be empty string).
    """
    d = find_best(parsed_objects_screen, CLASS_UI_GOAL, conf_min=conf_min)
    if not d:
        return ""
    crop = crop_pil(game_img, d["xyxy"], pad=(4, 2))
    return (ocr.text(crop) or "").strip()


# ------------------------------
# Energy percentage (via analyzer)
# ------------------------------
def extract_energy_pct(
    game_img: Image.Image,
    parsed_objects_screen: List[DetectionDict],
    *,
    conf_min: float = 0.20,
) -> int:
    """
    Returns the energy fill (0..100) if detected, else -1.
    """
    d = find_best(parsed_objects_screen, "ui_energy", conf_min=conf_min)
    if not d:
        return -1

    e_img = crop_pil(game_img, d["xyxy"], pad=0)
    info = energy_from_bar_crop(e_img)
    if not info.get("valid", False):
        logger_uma.debug("energy_from_bar_crop invalid: %s", info.get("reason"))
        return -1
    return int(info.get("energy_pct", -1))
