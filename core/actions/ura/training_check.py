
from typing import Dict, List, Optional, Tuple

from core.settings import Settings
from core.types import BLUE_GREEN, ORANGE_MAX, TileSV
from core.utils.skill_memory import SkillMemoryManager
from typing import Any

# ---- knobs you may want to tweak later (kept here for clarity) ----
GREEDY_THRESHOLD = 2.5  # "pick immediately" threshold (if you use it)
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
    Compute Support Value (SV) per tile and apply the failure filtering rule.

    Inputs
    ------
    training_state : list[dict]
        Exactly the structure you pasted (each tile has 'supports', 'failure_pct', ...).

    Scoring Rules (as provided)
    ---------------------------
    • Each blue/green gauge support: +1  (per card)
    • If any blue/green support on the tile has a hint: +0.5 once (tile-capped) x2 if HINT_IS_IMPORTANT is True in Settings
    • Rainbow support (FT): +1 per rainbow card
      - Combo bonus: if >=2 rainbous, only add 0.5
    • Orange/Max gauge WITHOUT hint: +0  (no base)
      Orange/Max gauge WITH hint: +0.5 once (tile-capped, even if multiple)  x2 if HINT_IS_IMPORTANT is True in Settings
    • Reporter (support_etsuko): +0.1
    • Director (support_director): color-based
        blue: +0.25, green: +0.15, orange: +0.10, yellow/max: +0
    • Tazuna (support_tazuna): +0.15 (yellow, max). +1 (blue), +0.5 (green, orange)
    Failure rule
    ------------
    Let max_failure = BASE_MAX_FAILURE (20%) by default.
    - If SV < 3.5 → the tile must have failure_pct ≤ max_failure
    - If SV ≥ 3.5 → allow up to min(100, floor(max_failure * 1.5))

    Returns
    -------
    List[dict] with keys:
      - tile_idx, failure_pct, risk_limit_pct, allowed_by_risk
      - sv_total (float)
      - sv_by_type (dict[str,float])    # per support_type aggregation
      - greedy_hit (bool)               # SV ≥ GREEDY_THRESHOLD
      - notes (list[str])               # human-readable breakdown
    """
    out: List[TileSV] = []
    # Skill memory used for conditional hint gating (once required skills are acquired)
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
    default_bluegreen_value = float(default_priority_cfg.get("scoreBlueGreen", 0.75))
    default_orange_value = float(default_priority_cfg.get("scoreOrangeMax", 0.5))

    def _support_label(support: Dict[str, Any]) -> str:
        matched = support.get("matched_card") or {}
        if isinstance(matched, dict) and matched.get("name"):
            name = str(matched.get("name", "")).strip()
            attr = str(matched.get("attribute", "")).strip()
            rarity = str(matched.get("rarity", "")).strip()
            suffix = " / ".join([p for p in (attr, rarity) if p])
            if suffix:
                return f"{name} ({suffix})"
            return name or "support"
        base = str(support.get("name", "support")).strip()
        return base or "support"

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
        # Conditional gating: if ALL required skills are already bought, drop hint value to 0
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
        config_value = float(priority_cfg.get(color_key, default_value))
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
        label = meta["label"]
        color_desc = meta["color_desc"]
        base_value = meta["base_value"]
        source = "priority" if meta["matched"] else "default"
        important_mult = meta.get("important_mult", 1.0)
        note = f"Hint on {label} ({color_desc}): +{bonus:.2f} (base={base_value:.2f} {source}"
        if important_mult != 1.0:
            note += f", important×{important_mult:.1f}"
        note += ")"
        return note

    for tile in training_state:
        idx = int(tile.get("tile_idx", -1))
        failure_pct = int(tile.get("failure_pct", 0) or 0)
        supports = tile.get("supports", []) or []

        sv_total = 0.0
        sv_by_type: Dict[str, float] = {}
        notes: List[str] = []

        # Tile-level caps/flags
        blue_hint_candidates: List[Tuple[float, Dict[str, Any]]] = []
        orange_hint_candidates: List[Tuple[float, Dict[str, Any]]] = []
        hint_disabled_notes: List[str] = []

        # For rainbow combo computation (per type)
        rainbow_count = 0

        # ---- 1) per-support contributions ----
        for s in supports:
            sname = s.get("name", "")
            # stype = s.get("support_type", "unknown") or "unknown"
            bar = s.get("friendship_bar", {}) or {}
            color = str(bar.get("color", "unknown")).lower()
            is_max = bool(bar.get("is_max", False))
            has_hint = bool(s.get("has_hint", False))
            has_rainbow = bool(s.get("has_rainbow", False))
            label = _support_label(s)

            # Normalize 'max' color if flagged
            if is_max and color not in ("yellow", "max"):
                color = "yellow"

            # --- special cameos ---
            if sname == "support_etsuko":  # reporter
                sv_total += 0.1
                sv_by_type["special_reporter"] = (
                    sv_by_type.get("special_reporter", 0.0) + 0.1
                )
                notes.append(f"Reporter ({label}): +0.10")
                continue

            if sname == "support_director":
                # director score depends on color (blue/green/orange/yellow)
                score = DIRECTOR_SCORE_BY_COLOR.get(
                    color, DIRECTOR_SCORE_BY_COLOR.get("yellow", 0.0)
                )
                if score > 0:
                    sv_total += score
                    sv_by_type["special_director"] = (
                        sv_by_type.get("special_director", 0.0) + score
                    )
                    notes.append(f"Director ({label}, {color}): +{score:.2f}")
                else:
                    notes.append(f"Director ({label}, {color}): +0.00")
                continue

            if sname == "support_tazuna":
                # Tazuna score depends on color:
                if color in ("blue", "green"):
                    score = 1.0
                elif color in ("orange", ):
                    score = 0.5
                elif color in ("yellow",) or is_max:
                    score = 0.15
                else:
                    score = 0.0
                
                if score > 0:
                    sv_total += score
                    sv_by_type["special_tazuna"] = (
                        sv_by_type.get("special_tazuna", 0.0) + score
                    )
                    notes.append(f"Tazuna ({label}, {color}): +{score:.2f}")
                else:
                    notes.append(f"Tazuna ({label}, {color}): +0.00")
                continue

            # --- standard support cards (including rainbow variants) ---
            # Rainbow counts as +1 baseline
            if has_rainbow:
                sv_total += 1.0
                notes.append(f"rainbow ({label}): +1.00")
                rainbow_count = rainbow_count + 1
                # Rainbow hint does not add extra beyond standard tile-capped hint rules;
                # we still let hint rules below consider color buckets if needed.
                # (If you want rainbow to bypass color gates, keep as-is)

            # Blue/green baseline
            if color in BLUE_GREEN:
                sv_total += 1.0
                sv_by_type["cards"] = sv_by_type.get("cards", 0.0) + 1.0
                notes.append(f"{label} {color}: +1.00")
                if has_hint:
                    bonus, meta = _hint_candidate_for_support(
                        s,
                        color_key="scoreBlueGreen",
                        default_value=default_bluegreen_value,
                        color_desc="blue/green",
                    )
                    if not meta["enabled"]:
                        hint_disabled_notes.append(
                            f"Hint on {meta['label']} ({meta['color_desc']}): skipped (priority disabled)"
                        )
                    else:
                        blue_hint_candidates.append((bonus, meta))
            # Orange/Max baseline is 0; only hint may help (tile-capped)
            elif color in ORANGE_MAX or is_max:
                if has_hint:
                    bonus, meta = _hint_candidate_for_support(
                        s,
                        color_key="scoreOrangeMax",
                        default_value=default_orange_value,
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

        # ---- 2) tile-capped hint bonuses ----
        for disabled_note in hint_disabled_notes:
            notes.append(disabled_note)

        best_hint_value = 0.0
        best_hint_meta: Optional[Dict[str, Any]] = None

        if blue_hint_candidates:
            candidate_value, candidate_meta = max(
                blue_hint_candidates, key=lambda item: item[0]
            )
            if candidate_value > best_hint_value:
                best_hint_value = candidate_value
                best_hint_meta = {**candidate_meta, "bucket": "hint_bluegreen"}

        if orange_hint_candidates:
            candidate_value, candidate_meta = max(
                orange_hint_candidates, key=lambda item: item[0]
            )
            if candidate_value > best_hint_value:
                best_hint_value = candidate_value
                best_hint_meta = {**candidate_meta, "bucket": "hint_orange_max"}

        if best_hint_meta and best_hint_value > 0:
            bucket = str(best_hint_meta.get("bucket", "hint_bluegreen"))
            sv_total += best_hint_value
            sv_by_type[bucket] = sv_by_type.get(bucket, 0.0) + best_hint_value
            notes.append(_format_hint_note(best_hint_meta, best_hint_value))
        elif best_hint_meta:
            notes.append(_format_hint_note(best_hint_meta, best_hint_value))

        # ---- 3) rainbow combo bonus (per type) ----

        if rainbow_count >= 2:
            # +0.5 for each *type* that has ≥2 rainbow cards
            combo_bonus = 0.5
            sv_total += combo_bonus
            sv_by_type["rainbow_combo"] = (
                sv_by_type.get("rainbow_combo", 0.0) + combo_bonus
            )
            notes.append(f"Rainbow combo +{combo_bonus}")

        # ---- risk gating with dynamic relax based on SV ----
        base_limit = Settings.MAX_FAILURE
        # Piecewise multiplier:
        #   SV ≥ 4.0 → x2.0
        #   SV > 3.0 → x1.5
        #   SV ≥ 2.5 → x1.25
        #   else     → x1.0

        has_hint = bool(blue_hint_candidates or orange_hint_candidates)
        if sv_total >= 5:
            risk_mult = 2.0
        elif sv_total >= 3.5 and not (has_hint and Settings.HINT_IS_IMPORTANT):
            # cap if hint is overcalculating
            risk_mult = 2.0
        elif sv_total >= 2.75 and not (has_hint and Settings.HINT_IS_IMPORTANT):
            # cap if hint is overcalculating
            risk_mult = 1.5
        elif sv_total >= 2.25:
            risk_mult = 1.25
        else:
            risk_mult = 1.0

        risk_limit = int(min(100, base_limit * risk_mult))
        allowed = failure_pct <= risk_limit
        notes.append(
            f"Dynamic risk: SV={sv_total:.2f} → base {base_limit}% × {risk_mult:.2f} = {risk_limit}%"
        )

        # ---- 5) greedy mark (optional early exit logic can use this) ----
        greedy_hit = (sv_total >= GREEDY_THRESHOLD) and allowed
        if greedy_hit:
            notes.append(
                f"Greedy hit: SV {sv_total:.2f} ≥ {GREEDY_THRESHOLD} and failure {failure_pct}% ≤ {risk_limit}%"
            )

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

    # Return simple dicts for convenience in notebooks / JSON
    return [t.as_dict() for t in out]
