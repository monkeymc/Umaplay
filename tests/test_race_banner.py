import cv2
import numpy as np

from core.perception.analyzers.race_banner import RaceBannerMatcher
from core.utils.race_index import RaceIndex


def _synth_card_from_template(template_path: str) -> np.ndarray:
    tmpl = cv2.imread(template_path, cv2.IMREAD_COLOR)
    if tmpl is None:
        raise FileNotFoundError(template_path)

    card_h, card_w = 360, 640
    card = np.full((card_h, card_w, 3), 30, dtype=np.uint8)

    top = int(card_h * 0.05)
    bottom = int(card_h * 0.55)
    left = int(card_w * 0.08)
    right = int(card_w * 0.92)

    region_h = max(1, bottom - top)
    region_w = max(1, right - left)
    resized = cv2.resize(tmpl, (region_w, region_h), interpolation=cv2.INTER_AREA)
    card[top:bottom, left:right] = resized
    return card


def test_banner_matcher_identifies_banner():
    meta = RaceIndex.banner_template("Japanese Oaks")
    assert meta is not None, "Japanese Oaks banner template missing"

    card = _synth_card_from_template(str(meta["path"]))
    matcher = RaceBannerMatcher()
    match = matcher.best_match(card)

    assert match is not None, "Expected a banner match"
    assert match.name == meta["name"]
    assert match.score >= 0.5


def test_banner_matcher_respects_candidate_filter():
    meta_target = RaceIndex.banner_template("Japanese Oaks")
    meta_other = RaceIndex.banner_template("Mainichi Okan")
    assert meta_target and meta_other

    card = _synth_card_from_template(str(meta_target["path"]))
    matcher = RaceBannerMatcher()
    match = matcher.best_match(card, candidates=[meta_target["name"], meta_other["name"]])

    assert match is not None
    assert match.name == meta_target["name"]
