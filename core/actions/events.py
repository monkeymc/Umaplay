from typing import List, Optional
from core.types import DetectionDict

from core.utils.logger import logger_uma

def click_top_event_choice(
    ctrl, ocr,
    parsed_objects_screen: List[DetectionDict],
    *,
    conf_min: float = 0.60,
) -> Optional[DetectionDict]:
    """
    Click the first (top-most) event choice once.

    Requirements:
    - Must be called right after a capture+detect so ctrl's last_origin matches
        the coordinates in `parsed_objects_screen`.
    Returns:
    - The DetectionDict of the clicked choice, or None if not found.
    """
    # Filter candidates
    choices = [
        d for d in parsed_objects_screen
        if d.get("name") == "event_choice" and float(d.get("conf", 0.0)) >= conf_min
    ]
    if not choices:
        logger_uma.info("[event] No event_choice found (conf_min=%.2f).", conf_min)
        return None

    if len(choices) == 1:
        # no multiple selection so let's ignore the false positive
        # TODO: make this stronger
        return None
    # Sort top → bottom by y1, take the top one
    top_choice = min(choices, key=lambda d: d["xyxy"][1])

    # One centered click; default jitter from controller (jitter=2)
    ctrl.click_xyxy_center(top_choice["xyxy"], clicks=1)

    logger_uma.info("[event] Clicked top event_choice (conf=%.3f).", top_choice["conf"])
    return top_choice