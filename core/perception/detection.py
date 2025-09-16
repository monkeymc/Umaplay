# core/perception/detection.py
from __future__ import annotations

from typing import List, Dict, Tuple, Optional
from collections import Counter

import numpy as np
from PIL import Image
from ultralytics import YOLO

from core.settings import Settings
from core.types import DetectionDict, ScreenName, ScreenInfo
from core.utils.img import pil_to_bgr
from core.utils.logger import logger_uma

# Lazily-initialized global (keeps call sites simple)
_YOLO_MODEL: Optional[YOLO] = None


def load_yolo(weights: Optional[str] = None) -> YOLO:
    """
    Initialize and cache the Ultralytics YOLO model.
    If no path is provided, uses Settings.YOLO_WEIGHTS.
    """
    global _YOLO_MODEL
    if _YOLO_MODEL is not None:
        return _YOLO_MODEL

    weights_path = str(weights or Settings.YOLO_WEIGHTS)
    logger_uma.info(f"Loading YOLO weights from: {weights_path}")
    _YOLO_MODEL = YOLO(weights_path)
    
    if Settings.USE_GPU:
        try:
            _YOLO_MODEL.to('cuda:0')
        except Exception as e:
            logger_uma.error(f"Couldn't set YOLO model to CUDA: {e}")
    return _YOLO_MODEL


def get_model() -> YOLO:
    """Return a ready YOLO model (load lazily on first use)."""
    return load_yolo()


def extract_dets(res, conf_min: float = 0.25) -> List[DetectionDict]:
    """
    Flatten a single Ultralytics `Results` into a list of normalized dicts:
    {name, conf, xyxy, idx}. Filters by conf_min.
    """
    boxes = getattr(res, "boxes", None)
    if boxes is None or len(boxes) == 0:
        return []

    names = res.names if isinstance(res.names, dict) else {i: n for i, n in enumerate(res.names)}
    xyxy = boxes.xyxy.cpu().numpy()
    cls  = boxes.cls.cpu().numpy().astype(int)
    conf = boxes.conf.cpu().numpy()

    out: List[DetectionDict] = []
    for i in range(len(cls)):
        if conf[i] < conf_min:
            continue
        out.append({
            "idx": i,
            "name": names.get(int(cls[i]), str(cls[i])),
            "conf": float(conf[i]),
            "xyxy": tuple(map(float, xyxy[i])),
        })
    return out


def detect_on_bgr(
    bgr: np.ndarray,
    *,
    imgsz: Optional[int] = None,
    conf: Optional[float] = None,
    iou: Optional[float] = None,
) -> Tuple[object, List[DetectionDict]]:
    """
    Run YOLO on an OpenCV BGR image and return:
      (yolo_result, det_list[DetectionDict])

    Controller-specific capture is intentionally NOT here; call this from your
    SteamController helper (e.g., controller grabs an image, then passes BGR here).
    """
    # Defaults from Settings unless explicitly overridden
    imgsz = imgsz if imgsz is not None else Settings.YOLO_IMGSZ
    conf  = conf  if conf  is not None else Settings.YOLO_CONF
    iou   = iou   if iou   is not None else Settings.YOLO_IOU

    model = get_model()
    res_list = model.predict(source=bgr, imgsz=imgsz, conf=conf, iou=iou, verbose=False)
    result = res_list[0]
    dets = extract_dets(result, conf_min=conf)

    return result, dets


def detect_on_pil(
    pil_img: Image.Image,
    *,
    imgsz: Optional[int] = None,
    conf: Optional[float] = None,
    iou: Optional[float] = None,
) -> Tuple[object, List[DetectionDict]]:
    """
    Run YOLO on a PIL Image and return:
      (yolo_result, det_list[DetectionDict])
    """
    bgr = pil_to_bgr(pil_img)
    return detect_on_bgr(bgr, imgsz=imgsz, conf=conf, iou=iou)

def classify_screen(
    dets: List[DetectionDict],
    *,
    lobby_conf: float = 0.70,
    require_infirmary: bool = True,
    training_conf: float = 0.50,
    event_conf: float = 0.60,
    race_conf: float = 0.80,
    names_map: Optional[Dict[str, str]] = None,
    debug: bool = True,
) -> Tuple[ScreenName, ScreenInfo]:
    """
    Decide which screen we're on.

    Rules (priority order):
      - 'Event'       → ≥1 'event_choice' @ ≥ event_conf
      - 'Inspiration' -> has_inspiration button
      - 'Raceday' → detect 'lobby_tazuna' @ ≥ lobby_conf AND 'race_race_day' @ ≥ race_conf
      - 'Training'    → exactly 5 'training_button' @ ≥ training_conf
      - 'LobbySummer' → has 'lobby_tazuna' AND 'lobby_rest_summer'
                         AND NOT 'lobby_rest' AND NOT 'lobby_recreation'
      - 'Lobby'       → has 'lobby_tazuna' AND (has 'lobby_infirmary' or not require_infirmary)
      - else 'Unknown'
    """
    names_map = names_map or {
        "tazuna":            "lobby_tazuna",
        "infirmary":         "lobby_infirmary",
        "training_button":   "training_button",
        "event":             "event_choice",
        "rest":              "lobby_rest",
        "rest_summer":       "lobby_rest_summer",
        "recreation":        "lobby_recreation",
        "race_day": "race_race_day",
        "event_inspiration": "event_inspiration",
        "race_after_next": "race_after_next",
        "lobby_skills": "lobby_skills",
        "button_claw_action": "button_claw_action",
        "claw": "claw",
    }

    counts = Counter(d["name"] for d in dets)

    n_event_choices = sum(
        1 for d in dets if d["name"] == names_map["event"] and d["conf"] >= event_conf
    )
    n_train = sum(
        1 for d in dets if d["name"] == names_map["training_button"] and d["conf"] >= training_conf
    )

    has_tazuna      = any(d["name"] == names_map["tazuna"]      and d["conf"] >= lobby_conf for d in dets)
    has_infirmary   = any(d["name"] == names_map["infirmary"]   and d["conf"] >= lobby_conf for d in dets)
    has_rest        = any(d["name"] == names_map["rest"]        and d["conf"] >= lobby_conf for d in dets)
    has_rest_summer = any(d["name"] == names_map["rest_summer"] and d["conf"] >= lobby_conf for d in dets)
    has_recreation  = any(d["name"] == names_map["recreation"]  and d["conf"] >= lobby_conf for d in dets)
    has_race_day  = any(d["name"] == names_map["race_day"]  and d["conf"] >= race_conf  for d in dets)
    has_inspiration = any(d["name"] == names_map["event_inspiration"]  and d["conf"] >= race_conf  for d in dets)
    has_lobby_skills = any(d["name"] == names_map["lobby_skills"]  and d["conf"] >= lobby_conf  for d in dets)
    race_after_next = any(d["name"] == names_map["race_after_next"]  and d["conf"] >= 0.5  for d in dets)
    has_button_claw_action = any(d["name"] == names_map["button_claw_action"]  and d["conf"] >= lobby_conf  for d in dets)
    has_claw = any(d["name"] == names_map["claw"]  and d["conf"] >= lobby_conf  for d in dets)
    
    # 1) Event
    if n_event_choices >= 1:
        return "Event", {"event_choices": n_event_choices}

    if has_inspiration:
        return "Inspiration", {"has_inspiration": has_inspiration}
    if has_tazuna and has_race_day:
        return "Raceday", {"tazuna": has_tazuna, "race_day": has_race_day}

    # 2) Training
    if n_train == 5:
        return "Training", {"training_buttons": n_train}

    # 3) LobbySummer
    if has_tazuna and has_rest_summer and (not has_rest) and (not has_recreation):
        return "LobbySummer", {
            "tazuna": has_tazuna,
            "rest_summer": has_rest_summer,
            "infirmary": has_infirmary,
            "recreation_present": has_recreation,
        }

    # 4) Regular Lobby
    if has_tazuna and (has_infirmary or not require_infirmary) and has_lobby_skills:
        return "Lobby", {"tazuna": has_tazuna, "infirmary": has_infirmary, "has_lobby_skills": has_lobby_skills}

    if (
        (len(dets) == 2 and has_lobby_skills and race_after_next)
        or (len(dets) <= 2 and has_lobby_skills)
    ):
        return "FinalScreen", {"has_lobby_skills": has_lobby_skills, "race_after_next": race_after_next}

    if has_button_claw_action and has_claw:
        return "ClawMachine", {"has_button_claw_action": has_button_claw_action, "has_claw": has_claw}
    
    # 5) Fallback
    return "Unknown", {
        "training_buttons": n_train,
        "tazuna": has_tazuna,
        "infirmary": has_infirmary,
        "rest": has_rest,
        "rest_summer": has_rest_summer,
        "recreation": has_recreation,
        "race_day": has_race_day,
        "counts": dict(counts),
    }