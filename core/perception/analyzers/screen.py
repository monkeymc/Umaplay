from collections import Counter
from typing import Dict, List, Optional, Tuple

from core.types import DetectionDict, ScreenInfo, ScreenName


def classify_screen(
    dets: List[DetectionDict],
    *,
    lobby_conf: float = 0.70,
    require_infirmary: bool = True,
    training_conf: float = 0.50,
    event_conf: float = 0.60,
    race_conf: float = 0.80,
    names_map: Optional[Dict[str, str]] = None,
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
        "tazuna": "lobby_tazuna",
        "infirmary": "lobby_infirmary",
        "training_button": "training_button",
        "event": "event_choice",
        "rest": "lobby_rest",
        "rest_summer": "lobby_rest_summer",
        "recreation": "lobby_recreation",
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
        1
        for d in dets
        if d["name"] == names_map["training_button"] and d["conf"] >= training_conf
    )

    has_tazuna = any(
        d["name"] == names_map["tazuna"] and d["conf"] >= lobby_conf for d in dets
    )
    has_infirmary = any(
        d["name"] == names_map["infirmary"] and d["conf"] >= lobby_conf for d in dets
    )
    has_rest = any(
        d["name"] == names_map["rest"] and d["conf"] >= lobby_conf for d in dets
    )
    has_rest_summer = any(
        d["name"] == names_map["rest_summer"] and d["conf"] >= lobby_conf for d in dets
    )
    has_recreation = any(
        d["name"] == names_map["recreation"] and d["conf"] >= lobby_conf for d in dets
    )
    has_race_day = any(
        d["name"] == names_map["race_day"] and d["conf"] >= race_conf for d in dets
    )
    has_inspiration = any(
        d["name"] == names_map["event_inspiration"] and d["conf"] >= race_conf
        for d in dets
    )
    has_lobby_skills = any(
        d["name"] == names_map["lobby_skills"] and d["conf"] >= lobby_conf for d in dets
    )
    race_after_next = any(
        d["name"] == names_map["race_after_next"] and d["conf"] >= 0.5 for d in dets
    )
    has_button_claw_action = any(
        d["name"] == names_map["button_claw_action"] and d["conf"] >= lobby_conf
        for d in dets
    )
    has_claw = any(
        d["name"] == names_map["claw"] and d["conf"] >= lobby_conf for d in dets
    )

    # 1) Event
    if n_event_choices >= 2:
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
        return "Lobby", {
            "tazuna": has_tazuna,
            "infirmary": has_infirmary,
            "has_lobby_skills": has_lobby_skills,
        }

    if (len(dets) == 2 and has_lobby_skills and race_after_next) or (
        len(dets) <= 2 and has_lobby_skills
    ):
        return "FinalScreen", {
            "has_lobby_skills": has_lobby_skills,
            "race_after_next": race_after_next,
        }

    if has_button_claw_action and has_claw:
        return "ClawMachine", {
            "has_button_claw_action": has_button_claw_action,
            "has_claw": has_claw,
        }

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
