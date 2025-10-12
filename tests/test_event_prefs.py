from core.utils.event_processor import EventRecord, UserPrefs


def _make_general_event(name: str, step: int = 1) -> EventRecord:
    """Construct a minimal `EventRecord` for general trainee events."""
    return EventRecord(
        key=f"trainee/general/None/None/{name}",
        key_step=f"trainee/general/None/None/{name}#s{step}",
        type="trainee",
        name="general",
        rarity="None",
        attribute="None",
        event_name=name,
        chain_step=step,
        default_preference=1,
        options={"1": [{}], "2": [{}]},
        title_norm=name.lower(),
        image_path=None,
        phash64=None,
    )


def test_pick_for_general_event_uses_specific_override():
    """Ensure overrides for trainee-specific keys apply to general matches."""
    prefs = UserPrefs(
        overrides={
            "trainee/Rice Shower/None/None/Defeat (G1)#s1": 2,
        },
        patterns=[],
        default_by_type={"support": 1, "trainee": 1, "scenario": 1},
    )

    rec = _make_general_event("Defeat (G1)")
    assert prefs.pick_for(rec) == 2


def test_pick_for_general_event_with_step_suffix_alias():
    """Ensure alias mapping covers default #s1 suffix when omitted."""
    prefs = UserPrefs(
        overrides={
            "trainee/Rice Shower/None/None/Solid Showing (G1)#s1": 2,
        },
        patterns=[],
        default_by_type={"support": 1, "trainee": 1, "scenario": 1},
    )

    rec = _make_general_event("Solid Showing (G1)")
    assert prefs.pick_for(rec) == 2
