# core/perception/extractors.py
from __future__ import annotations

import difflib
import re
from typing import Dict, List, Optional, Tuple
import os, time
from pathlib import Path
import cv2
import numpy as np
from PIL import Image

from core.perception.analyzers.mood import mood_label
from core.perception.ocr import OCREngine
from core.perception.analyzers.energy_bar import energy_from_bar_crop
from core.settings import Settings
from core.types import (
    DetectionDict,
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
from PIL import Image, ImageStat

from core.utils.text import fuzzy_contains


# ------------------------------
# Common helper
# ------------------------------
def find_best(parsed_objects_screen: List[DetectionDict], name: str, conf_min: float = 0.50) -> Optional[DetectionDict]:
    """
    Pick the highest-confidence detection of a given class name.
    """
    cands = [d for d in parsed_objects_screen if d["name"] == name and d["conf"] >= conf_min]
    if not cands:
        return None
    return max(cands, key=lambda d: d["conf"])


# ------------------------------
# Mood
# ------------------------------
def extract_mood(
    ocr: OCREngine,
    game_img: Image.Image,
    parsed_objects_screen: List[DetectionDict],
    *,
    conf_min: float = 0.20,
    pad: int = 1
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
    ocr: OCREngine,
    game_img: Image.Image,
    parsed_objects_screen: List[DetectionDict],
    *,
    conf_min: float = 0.20,
) -> Tuple[int, str]:
    """
    Returns (turns_left, career_date_raw). If missing, (-1, "").
    """
    d = find_best(parsed_objects_screen, CLASS_UI_TURNS, conf_min=conf_min)
    if not d:
        return -1
    # Turns (prefer a 1–2 digit number)
    x1 = d["xyxy"][0]
    y1 = d["xyxy"][1]
    x2 = d["xyxy"][2]
    y2 = d["xyxy"][3]

    element_height = abs(y2 - y1)
    gap = element_height * 0.2
    y1 += gap
    y2 -= gap

    turns_img = crop_pil(game_img, (x1, y1, x2, y2), pad=0)

    # Using ML to predict digit
    turns_left = ocr.digits(turns_img)
    # use digits cropper + resnet if it is faster than ocr.

    if turns_left > 0 and turns_left <= 30:
        return turns_left

    if turns_left == -1:
        logger_uma.warning("Unrecognized turns")
    return turns_left

# ------------------------------
# Turns
# ------------------------------
def extract_career_date(
    ocr: OCREngine,
    game_img: Image.Image,
    parsed_objects_screen: List[DetectionDict],
    *,
    conf_min: float = 0.20,
) -> Tuple[int, str]:
    """
    Returns (turns_left, career_date_raw). If missing, (-1, "").
    """
    d = find_best(parsed_objects_screen, CLASS_UI_TURNS, conf_min=conf_min)
    if not d:
        return -1, ""

    # Career date: box immediately above the turns widget
    W, H = game_img.size
    x1, y1, x2, y2 = xyxy_int(d["xyxy"])
    tw, th = x2 - x1, y2 - y1
    width = int(round(2.5 * tw))
    half_gap = min(y1 // 2, y1)
    rx1 = x1
    ry2 = max(0, y1 - 2)
    ry1 = half_gap
    rx2 = min(W, rx1 + width)
    career_crop = game_img.crop((rx1, ry1, rx2, ry2))
    career_date_raw = (ocr.text(career_crop) or "").strip()

    return career_date_raw

# ------------------------------
# Stats (SPD/STA/PWR/GUTS/WIT)
# ------------------------------
def _parse_stat_segment(ocr: OCREngine, seg_img: Image.Image) -> int:
    """
    Segment typically looks like `C 416 / 1200`.
    Robust parsing rules:
      - Strip '/1200' (with or without slash/spaces).
      - Allow one trailing *letter* (common OCR for the last digit: e→6, O→0, etc.).
      - Map common letter/digit confusions.
      - If a trailing letter remains unmapped, replace it with '0' (warn).
      - Clamp to [90, 1200]; if <90 and there was no trailing letter, clamp to 90.
    """
    raw = (ocr.text(seg_img) or "")
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
        "O": "0", "o": "0", "D": "0", "Q": "0",
        "I": "1", "l": "1", "|": "1", "!": "1",
        "Z": "2",
        "S": "5", "s": "5",
        "E": "6", "e": "6", "G": "6",
        "B": "8",
        "g": "9", "q": "9",
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
                # keep a placeholder for trailing unknown; drop others
                if i == len(token) - 1:  # trailing unknown letter
                    out.append("")  # will fill with '0' below

    # If we had a trailing letter and it didn't map, force '0'
    if trailing_letter and (not out or not out[-1].isdigit()):
        out[-1:] = ["0"]
        logger_uma.warning("Stat OCR had trailing letter '%s' → using 0 (raw='%s')",
                           trailing_char, raw)

    digits = "".join(out)
    if not digits:
        return -1

    try:
        val = int(digits)
    except Exception:
        # Very last fallback: first plain digit group from the original text
        nums = re.findall(r"\d+", raw)
        val = int(nums[0]) if nums else -1
        if val == -1:
            return -1

    # Clamp to valid range
    if val > 2000:
        val = 1200
    if val < 90:
        if not trailing_letter:
            # No letter to “fix”; clamp to the known minimum
            logger_uma.debug("Stat %s < 90 without trailing letter; clamping to 90 (raw='%s')",
                             val, raw)
        val = -1  # not recognized

    return val


def extract_stats(
    ocr: OCREngine,
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
    """
    d = find_best(parsed_objects_screen, CLASS_UI_STATS, conf_min=conf_min)
    if not d:
        return {"SPD": -1, "STA": -1, "PWR": -1, "GUTS": -1, "WIT": -1}

    stats_img = crop_pil(game_img, d["xyxy"], pad=(0, 0))
    W, H = stats_img.size
    k = 5
    segW = max(1, W // k)
    keys = ["SPD", "STA", "PWR", "GUTS", "WIT"]

    if with_segments:
        out: Dict[str, Dict[str, object]] = {}
        for i, key in enumerate(keys):
            x1 = int((i * segW) + segW * 0.4)
            x2 = W if i == k - 1 else int((i + 1) * segW)
            x2 += segW * 0.25
            seg = stats_img.crop((x1, int(H * 0.26), x2, int(H * 0.74)))
            out[key] = {"value": _parse_stat_segment(ocr, seg), "seg": seg}
        return out

    out2: Dict[str, int] = {}
    for i, key in enumerate(keys):
        x1 = int((i * segW) + segW * 0.4)
        x2 = W if i == k - 1 else int((i + 1) * segW)
        seg = stats_img.crop((x1, int(H * 0.26), x2, int(H * 0.74)))
        out2[key] = _parse_stat_segment(ocr, seg)
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
    If a joblib classifier exists (Settings.IS_BUTTON_ACTIVE_CLF_PATH) and Settings.USE_INFIRMARY_CLF is True,
    use it; otherwise fall back to a HSV heuristic.
    """
    d = find_best(parsed_objects_screen, CLASS_LOBBY_INFIRMARY, conf_min=conf_min)
    if not d:
        return False

    crop = crop_pil(game_img, d["xyxy"], pad=0)

    # Try model first
    if Settings.USE_INFIRMARY_CLF and Settings.IS_BUTTON_ACTIVE_CLF_PATH.exists():
        try:
            import joblib  # lazy import
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
    ocr: OCREngine,
    game_img: Image.Image,
    parsed_objects_screen: List[DetectionDict],
    *,
    conf_min: float = 0.20,
) -> int:
    """
    Returns the skill points integer (0..9999), or -1 if not found.
    """
    d = find_best(parsed_objects_screen, CLASS_UI_SKILLS_PTS, conf_min=conf_min)
    if not d:
        return -1
    crop = crop_pil(game_img, d["xyxy"], pad=0)
    digits = ocr.digits(crop)
    return digits


# ------------------------------
# Goal text
# ------------------------------
def extract_goal_text(
    ocr: OCREngine,
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
