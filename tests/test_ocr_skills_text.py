import pytest

from core.utils.text import fix_common_ocr_confusions
from core.actions.skills import SkillsFlow


def test_fix_common_ocr_confusions_digits_inside_words():
    s = "Gr0undw0rk"
    fixed = fix_common_ocr_confusions(s)
    assert fixed.lower() == "groundwork"


def test_norm_title_and_similarity_groundwork():
    raw = "Gr0undw0rk"
    norm = SkillsFlow._norm_title(raw)
    target = SkillsFlow._norm_title("Groundwork")
    from core.utils.text import fuzzy_ratio

    assert fuzzy_ratio(norm, target) >= 0.9


def test_norm_title_left_handed_passthrough():
    raw = "Left-Handed"
    norm = SkillsFlow._norm_title(raw)
    target = SkillsFlow._norm_title("Left-Handed")
    from core.utils.text import fuzzy_ratio

    assert fuzzy_ratio(norm, target) >= 0.95


def test_norm_title_not_overcorrect_numbers_at_edges():
    # digits at edges should remain as-is
    raw = "0Left"  # 0 not surrounded by letters
    fixed = fix_common_ocr_confusions(raw)
    assert fixed.startswith("0"), "Leading 0 should remain when not between letters"

    raw2 = "Handed6"  # 6 at end, not surrounded by letters
    fixed2 = fix_common_ocr_confusions(raw2)
    assert fixed2.endswith("6"), "Trailing 6 should remain when not between letters"
