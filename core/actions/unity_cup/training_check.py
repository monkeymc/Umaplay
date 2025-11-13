
from __future__ import annotations

from typing import Dict, List, Optional, Tuple
from core.settings import Settings
from core.utils.skill_memory import SkillMemoryManager
from typing import Any
from core.types import BLUE_GREEN, ORANGE_MAX, TileSV


# ---- knobs you may want to tweak later (kept here for clarity) ----
GREEDY_THRESHOLD_UNITY_CUP = 3.5
HIGH_SV_THRESHOLD = 3.5  # when SV >= this, allow risk up to ×RISK_RELAX_FACTOR
RISK_RELAX_FACTOR = 1.5  # e.g., 20% -> 30% when SV is high

# Director scoring by bar color (latest rule you wrote)
DIRECTOR_SCORE_BY_COLOR = {
    "blue": 0.25,  # "blue or less"
    "green": 0.15,
    "orange": 0.10,
    "yellow": 0.00,  # max (or treat is_max as yellow)
    "max": 0.00,  # alias
}

def compute_support_values(training_state: List[Dict]) -> List[Dict[str, Any]]:
    """
    Unity Cup variant. Same output shape as URA.
    Differences:
      • Hint defaults: 0.50 (blue/green), 0.25 (orange/max) — still overridable via priority_config
      • Rainbow combo: 0.25 * (#rainbows) if >= 2
      • Kashimoto: if support_type ∈ {SPD,STA,PWR,GUTS,WIT,PAL} → treat like PAL card (Tazuna rules);
                   otherwise treat like Director (color-based)
      • Spirits: per-spirit + combo bonus:
            per spirit: +0.50 if flame_type == 'filling_up', +0.12 if 'exploded'
            combo (only if ≥2 filling): 0.25*(2*n_fill-1) + 0.01*n_exploded
    """
    out: List[TileSV] = []
    skill_memory = SkillMemoryManager(
        Settings.resolve_skill_memory_path(Settings.ACTIVE_SCENARIO),
        scenario=Settings.ACTIVE_SCENARIO,
    )

    def _canon_skill(name: object) -> str:
        s = str(name or "")
        for sym in ("◎", "○", "×"):
            s = s.replace(sym, "")
        return " ".join(s.split()).strip()

    default_priority_cfg = Settings.default_support_priority()
    # Unity defaults (still overridable):
    UNITY_BLUEGREEN_HINT_DEFAULT = 0.50
    UNITY_ORANGE_HINT_DEFAULT = 0.25

    def _support_label(support: Dict[str, Any]) -> str:
        matched = support.get("matched_card") or {}
        if isinstance(matched, dict) and matched.get("name"):
            name = str(matched.get("name", "")).strip()
            attr = str(matched.get("attribute", "")).strip()
            rarity = str(matched.get("rarity", "")).strip()
            suffix = " / ".join([p for p in (attr, rarity) if p])
            return f"{name} ({suffix})" if suffix else (name or "support")
        return str(support.get("name", "support")).strip() or "support"

    def _hint_candidate_for_support(
        support: Dict[str, Any],
        *,
        color_key: str,
        default_value: float,
        color_desc: str,
    ) -> Tuple[float, Dict[str, Any]]:
        priority_cfg = support.get("priority_config")
        matched_card = support.get("matched_card")
        matched = isinstance(matched_card, dict) and bool(matched_card)
        if not isinstance(priority_cfg, dict):
            priority_cfg = default_priority_cfg
            matched = False

        enabled = bool(priority_cfg.get("enabled", True))
        # Gate by required skills (if all already bought → disable)
        gated = False
        try:
            req = priority_cfg.get("skillsRequiredForPriority")
            req_list = []
            if isinstance(req, list):
                req_list = [n for n in (_canon_skill(x) for x in req) if n]
            elif isinstance(req, str):
                req_list = [n for n in (_canon_skill(x) for x in str(req).split(",")) if n]
            if req_list:
                gated = all(skill_memory.has_bought(n) for n in req_list)
        except Exception:
            gated = False
        if gated:
            enabled = False

        label = _support_label(support)
        config_value = float(priority_cfg.get(color_key, default_value))  # allow override
        base_value = config_value if matched else default_value
        important_mult = 3.0 if Settings.HINT_IS_IMPORTANT else 1.0
        effective_value = base_value * important_mult if enabled else 0.0
        meta = {
            "label": label,
            "color_desc": color_desc,
            "enabled": enabled,
            "matched": matched,
            "base_value": base_value,
            "important_mult": important_mult,
            "gated": gated,
        }
        return effective_value, meta

    def _format_hint_note(meta: Dict[str, Any], bonus: float) -> str:
        label = meta["label"]; color_desc = meta["color_desc"]; base_value = meta["base_value"]
        source = "priority" if meta["matched"] else "default"
        note = f"Hint on {label} ({color_desc}): +{bonus:.2f} (base={base_value:.2f} {source}"
        if meta.get("important_mult", 1.0) != 1.0:
            note += f", important×{meta['important_mult']:.1f}"
        note += ")"
        return note

    KNOWN_TYPES = {"SPD","STA","PWR","GUTS","WIT","PAL"}

    for tile in training_state:
        idx = int(tile.get("tile_idx", -1))
        failure_pct = int(tile.get("failure_pct", 0) or 0)
        supports = tile.get("supports", []) or []

        sv_total = 0.0
        sv_by_type: Dict[str, float] = {}
        notes: List[str] = []

        blue_hint_candidates: List[Tuple[float, Dict[str, Any]]] = []
        orange_hint_candidates: List[Tuple[float, Dict[str, Any]]] = []
        hint_disabled_notes: List[str] = []

        rainbow_count = 0

        # ---- 1) per-support contributions -----------------------------------
        for s in supports:
            sname = s.get("name", "")
            bar = s.get("friendship_bar", {}) or {}
            color = str(bar.get("color", "unknown")).lower()
            is_max = bool(bar.get("is_max", False))
            has_hint = bool(s.get("has_hint", False))
            has_rainbow = bool(s.get("has_rainbow", False))
            stype = (s.get("support_type") or "").strip().upper()
            label = _support_label(s)

            if is_max and color not in ("yellow", "max"):
                color = "yellow"

            # Special cameos
            if sname == "support_etsuko":
                sv_total += 0.10
                sv_by_type["special_reporter"] = sv_by_type.get("special_reporter", 0.0) + 0.10
                notes.append(f"Reporter ({label}): +0.10")
                continue

            if sname == "support_director":
                score = DIRECTOR_SCORE_BY_COLOR.get(color, DIRECTOR_SCORE_BY_COLOR["yellow"])
                if score > 0:
                    sv_total += score
                    sv_by_type["special_director"] = sv_by_type.get("special_director", 0.0) + score
                notes.append(f"Director ({label}, {color}): +{score:.2f}")
                continue

            if sname == "support_tazuna":
                # PAL rules
                if color in ("blue",):       score = 1.5
                else:                                 score = 0.5
                sv_total += score
                sv_by_type["special_tazuna"] = sv_by_type.get("special_tazuna", 0.0) + score
                notes.append(f"Tazuna ({label}, {color}): +{score:.2f}")
                continue

            if sname == "support_kashimoto":
                # If she shows any support_type → treat as PAL; else as Director
                if stype in KNOWN_TYPES and stype != "":
                    if color in ("blue",):       score = 1.5
                    else:                                 score = 0.5
                    sv_total += score
                    sv_by_type["special_kashimoto_pal"] = sv_by_type.get("special_kashimoto_pal", 0.0) + score
                    notes.append(f"Kashimoto as PAL ({label}, {color}): +{score:.2f}")
                else:
                    score = DIRECTOR_SCORE_BY_COLOR.get(color, DIRECTOR_SCORE_BY_COLOR["yellow"])
                    if score > 0:
                        sv_total += score
                        sv_by_type["special_kashimoto_director"] = sv_by_type.get("special_kashimoto_director", 0.0) + score
                    notes.append(f"Kashimoto as Director ({label}, {color}): +{score:.2f}")
                continue

            # Standard supports
            if has_rainbow:
                sv_total += 1.0
                rainbow_count += 1
                notes.append(f"rainbow ({label}): +1.00")

            if color in BLUE_GREEN:
                sv_total += 1.0
                sv_by_type["cards"] = sv_by_type.get("cards", 0.0) + 1.0
                notes.append(f"{label} {color}: +1.00")
                if has_hint:
                    bonus, meta = _hint_candidate_for_support(
                        s,
                        color_key="scoreBlueGreen",
                        default_value=UNITY_BLUEGREEN_HINT_DEFAULT,
                        color_desc="blue/green",
                    )
                    if not meta["enabled"]:
                        hint_disabled_notes.append(
                            f"Hint on {meta['label']} ({meta['color_desc']}): skipped (priority disabled)"
                        )
                    else:
                        blue_hint_candidates.append((bonus, meta))
            elif color in ORANGE_MAX or is_max:
                if has_hint:
                    bonus, meta = _hint_candidate_for_support(
                        s,
                        color_key="scoreOrangeMax",
                        default_value=UNITY_ORANGE_HINT_DEFAULT,
                        color_desc="orange/max",
                    )
                    if not meta["enabled"]:
                        hint_disabled_notes.append(
                            f"Hint on {meta['label']} ({meta['color_desc']}): skipped (priority disabled)"
                        )
                    else:
                        orange_hint_candidates.append((bonus, meta))
                notes.append(f"{label} {color}: +0.00")
            else:
                notes.append(f"{label} {color}: +0.00 (unknown color category)")

        # ---- tile-capped hint bonus (best only) ------------------------------
        for dn in hint_disabled_notes:
            notes.append(dn)

        best_hint_value = 0.0
        best_hint_meta: Optional[Dict[str, Any]] = None
        if blue_hint_candidates:
            v, m = max(blue_hint_candidates, key=lambda it: it[0])
            if v > best_hint_value:
                best_hint_value, best_hint_meta = v, {**m, "bucket": "hint_bluegreen"}
        if orange_hint_candidates:
            v, m = max(orange_hint_candidates, key=lambda it: it[0])
            if v > best_hint_value:
                best_hint_value, best_hint_meta = v, {**m, "bucket": "hint_orange_max"}

        if best_hint_meta and best_hint_value > 0:
            bucket = str(best_hint_meta.get("bucket", "hint_bluegreen"))
            sv_total += best_hint_value
            sv_by_type[bucket] = sv_by_type.get(bucket, 0.0) + best_hint_value
            notes.append(_format_hint_note(best_hint_meta, best_hint_value))
        elif best_hint_meta:
            notes.append(_format_hint_note(best_hint_meta, best_hint_value))

        # ---- rainbow combo (Unity) ------------------------------------------
        if rainbow_count >= 2:
            combo_bonus = 0.5 * float(rainbow_count - 1)
            sv_total += combo_bonus
            sv_by_type["rainbow_combo"] = sv_by_type.get("rainbow_combo", 0.0) + combo_bonus
            notes.append(f"Rainbow combo ({rainbow_count}): +{combo_bonus:.2f}")

        # ---- spirits (colored) ----------------------------------------------
        spirits = [s for s in supports if s.get("has_spirit", False)]

        # Split by color
        whites = [s for s in spirits if (s.get("spirit_color") == "white" or s.get("spirit_color") == "unknown")]
        blues  = [s for s in spirits if s.get("spirit_color") == "blue"]

        # Per-spirit base value
        n_white_fill     = sum(1 for s in whites if s.get("has_flame") and s.get("flame_type") == "filling_up")
        n_white_exploded = sum(1 for s in whites if s.get("has_flame") and s.get("flame_type") == "exploded")
        n_blue_total     = len(blues)
        n_blue_fill      = sum(1 for s in blues  if s.get("has_flame") and s.get("flame_type") == "filling_up")

        # White spirits: same rule as before (0.50 filling, 0.12 exploded)
        white_value = 0.40 * n_white_fill + 0.13 * n_white_exploded
        if white_value > 0:
            sv_total += white_value
            sv_by_type["spirits_white"] = sv_by_type.get("spirits_white", 0.0) + white_value
            notes.append(f"White spirits: +{white_value:.2f} (fill={n_white_fill}, exploded={n_white_exploded})")

        # White combo (only for not-exploded/flame filling) + tiny weight for exploded inside combo
        white_combo = 0.0
        if n_white_fill >= 2:
            white_combo += 0.2 + 0.25 * n_white_fill  # 2→0.75, 3→1.0, ...
        if (n_white_fill + n_white_exploded) >= 2:
            white_combo += 0.01 * n_white_exploded
        if white_combo > 0:
            sv_total += white_combo
            sv_by_type["spirit_combo_white"] = sv_by_type.get("spirit_combo_white", 0.0) + white_combo
            notes.append(f"White spirit combo: +{white_combo:.2f}")

        # Blue spirits: regardless of flame, 0.5 each
        blue_value = 0.5 * n_blue_total
        if blue_value > 0:
            sv_total += blue_value
            sv_by_type["spirits_blue"] = sv_by_type.get("spirits_blue", 0.0) + blue_value
            notes.append(f"Blue spirits: +{blue_value:.2f} (count={n_blue_total})")

        # Blue combo: if ≥2 blue 'to explode' (i.e., filling), +1 for each beyond the first
        blue_combo = 0.0
        if n_blue_fill > 1:
            # Blue is ADDITIVE, so combo is not as strong as white
            blue_combo = 0.25 * (n_blue_fill - 1)
            sv_total += blue_combo
            sv_by_type["spirit_combo_blue"] = sv_by_type.get("spirit_combo_blue", 0.0) + blue_combo
            notes.append(f"Blue spirit combo: +{blue_combo:.2f} (filling={n_blue_fill})")

        # ---- risk gating (higher than URA) --------------------------------------
        base_limit = Settings.MAX_FAILURE
        has_any_hint = bool(blue_hint_candidates or orange_hint_candidates)
        if sv_total >= 7:
            risk_mult = 2.0
        elif sv_total >= 5 and not (has_any_hint and Settings.HINT_IS_IMPORTANT):
            risk_mult = 2.0
        elif sv_total > 4.5 and not (has_any_hint and Settings.HINT_IS_IMPORTANT):
            risk_mult = 1.5
        elif sv_total >= 4.25 and not (has_any_hint and Settings.HINT_IS_IMPORTANT):
            risk_mult = 1.35
        elif sv_total >= 4:
            risk_mult = 1.25
        else:
            risk_mult = 1.0

        risk_limit = int(min(100, base_limit * risk_mult))
        allowed = failure_pct <= risk_limit
        notes.append(f"Dynamic risk: SV={sv_total:.2f} → base {base_limit}% × {risk_mult:.2f} = {risk_limit}%")

        greedy_hit = (sv_total >= GREEDY_THRESHOLD_UNITY_CUP) and allowed
        if greedy_hit:
            notes.append(f"Greedy hit: SV {sv_total:.2f} ≥ {GREEDY_THRESHOLD_UNITY_CUP} and failure {failure_pct}% ≤ {risk_limit}%")

        out.append(
            TileSV(
                tile_idx=idx,
                failure_pct=failure_pct,
                risk_limit_pct=risk_limit,
                allowed_by_risk=bool(allowed),
                sv_total=float(sv_total),
                sv_by_type=sv_by_type,
                greedy_hit=greedy_hit,
                notes=notes,
            )
        )

    return [t.as_dict() for t in out]
