#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Unified UMA MUSUME Event Scraper
- HTML mode: parse Event Viewer HTML blocks (multi support cards, trainees).
- JSON mode: fetch Gametora support/character pages, parse __NEXT_DATA__.
- Scoring: Energy > Stats > Skill Pts > Hint (worst-case safe default).
- HTML extras: 'All stats +N', 'X random stats +N', numeric ranges like '-5/-20'.
- JSON extras: translate skill/status IDs (skills.json / status.json), period filter, optional image download.

Usage (single line examples):
  cls && python scrape_events.py --html-file events_full_html.txt --support-defaults "Matikanefukukitaru-SR-WIT|Seeking the Pearl-SR-GUTS" --out supports_events.json --debug
  cls && python scrape_events.py --supports-card "30027-mejiro-palmer,20029-seeking-the-pearl" --characters-card "105602-matikanefukukitaru" --skills in_game/skills.json --status in_game/status.json --period pre_first_anni --images --img-dir images --out supports_events.json --debug
"""

import argparse
import json
import os
import re
import shutil
import sys
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup, Tag

try:
    import requests
except Exception:
    requests = None

# ============================ Scoring weights ================================
W_ENERGY   = 100.0
W_STAT     = 10.0
W_SKILLPTS = 2.0
W_HINT     = 1.0
W_BOND     = 0.3
W_MOOD     = 2.0

STAT_WEIGHTS = {  # same as your working script
    "speed": 5.0,
    "stamina": 4.0,
    "power": 3.0,
    "wit": 2.0,
    "guts": 1.0,
}

# ================================ Utils =====================================
BASE_URL = "https://gametora.com"
SUPPORT_BASE_URL = BASE_URL + "/umamusume/supports/"
CHARACTER_BASE_URL = BASE_URL + "/umamusume/characters/"

def dbg(on: bool, *args, **kwargs):
    if on:
        print(*args, file=sys.stderr, **kwargs)

def T(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def ensure_requests():
    if not requests:
        raise SystemExit("This mode requires `requests`. Please: pip install requests")

# =============== Value helpers (covers '5/10' strings safely) ===============
_SPLIT = re.compile(r"/")
_NUM = re.compile(r"^[+\-]?\d+(?:\.\d+)?$")

def values_from_maybe_range(v: Any) -> List[float]:
    """
    Accepts ints/floats or strings like '+5' or '+5/+10' and returns list of floats.
    Worst-case scoring will pick the minimum impact later.
    """
    if isinstance(v, (int, float)):
        return [float(v)]
    if not isinstance(v, str):
        return [0.0]
    s = v.strip().lstrip("+")
    parts = [p.strip() for p in _SPLIT.split(s)] if "/" in s else [s]
    vals: List[float] = []
    for p in parts:
        if _NUM.match(p):
            vals.append(float(p))
        else:
            # fallback: extract first integer found
            m = re.search(r"[+\-]?\d+(?:\.\d+)?", p)
            vals.append(float(m.group(0)) if m else 0.0)
    return vals or [0.0]

def min_from_maybe_range(v: Any) -> float:
    vals = values_from_maybe_range(v)
    # "worst" is the minimum contribution for positive rewards; for negatives this already is ≤
    return min(vals)

# ============================ HTML mode regexes ==============================
_RE_INT       = r"([+\-]?\d+)"
_RE_RANGE     = r"([+\-]?\d+)\s*/\s*([+\-]?\d+)"
RE_ENERGY       = re.compile(r"\benergy\b\s*"+_RE_INT, re.I)
RE_ENERGY_RANGE = re.compile(r"\benergy\b\s*"+_RE_RANGE, re.I)
RE_BOND         = re.compile(r"\bbond\b\s*"+_RE_INT, re.I)
RE_SKILLPTS     = re.compile(r"\bskill\s*(?:points|pts)\b\s*"+_RE_INT, re.I)
RE_MOOD         = re.compile(r"\bmood\b\s*"+_RE_INT, re.I)
RE_LAST_TRAINED_STAT = re.compile(r"\blast\s*trained\s*stat\b\s*"+_RE_INT, re.I)
RE_MOTIV_UP     = re.compile(r"\b(mood|motivation)\b.*\b(up|good)\b", re.I)
RE_MOTIV_DOWN   = re.compile(r"\b(mood|motivation)\b.*\b(down|bad)\b", re.I)

STAT_RX = {
    "speed":   re.compile(r"\bspeed\b\s*"+_RE_INT, re.I),
    "stamina": re.compile(r"\bstamina\b\s*"+_RE_INT, re.I),
    "power":   re.compile(r"\bpower\b\s*"+_RE_INT, re.I),
    "guts":    re.compile(r"\bguts\b\s*"+_RE_INT, re.I),
    "wit":     re.compile(r"\b(?:wit|wis|wisdom|int|intelligence)\b\s*"+_RE_INT, re.I),
}
STAT_RX_RANGE = {
    "speed":   re.compile(r"\bspeed\b\s*"+_RE_RANGE, re.I),
    "stamina": re.compile(r"\bstamina\b\s*"+_RE_RANGE, re.I),
    "power":   re.compile(r"\bpower\b\s*"+_RE_RANGE, re.I),
    "guts":    re.compile(r"\bguts\b\s*"+_RE_RANGE, re.I),
    "wit":     re.compile(r"\b(?:wit|wis|wisdom|int|intelligence)\b\s*"+_RE_RANGE, re.I),
}
RE_ALL_STATS     = re.compile(r"\b(all\s*stats|all\s*parameters|all\s*status)\b\s*"+_RE_INT, re.I)
RE_RANDOM_STATS  = re.compile(r"\b(\d+)\s*random\s*(?:stats?|parameters?)\b\s*"+_RE_INT, re.I)
RE_CHAIN_HDR     = re.compile(r"^\(\s*([»❯>]+)\s*\)\s*(.*)$")

# ============================ Defaults mapping ==============================
def parse_support_defaults(raw: str) -> Dict[str, Tuple[str, str]]:
    """
    'Name-RAR-ATTR|Name2-RAR-ATTR' -> {name_lower: (RAR, ATTR)}; splits from end so hyphens in names remain.
    """
    mapping: Dict[str, Tuple[str, str]] = {}
    if not raw:
        return mapping
    for chunk in [c.strip() for c in raw.split("|") if c.strip()]:
        parts = [p.strip() for p in chunk.split("-")]
        if len(parts) < 3:
            continue
        attr  = parts[-1]
        rarity= parts[-2]
        name  = "-".join(parts[:-2]).strip()
        if name:
            mapping[name.lower()] = (rarity, attr)
    return mapping

# ================================ Scoring ===================================
def score_outcome(eff: Dict[str, Any]) -> float:
    # Energy
    energy = min_from_maybe_range(eff.get("energy", 0))
    # Stats
    stats_sum = 0.0
    for stat, weight in STAT_WEIGHTS.items():
        stats_sum += weight * min_from_maybe_range(eff.get(stat, 0))
    # 'random_stats' from HTML mode
    if isinstance(eff.get("random_stats"), dict):
        rs = eff["random_stats"]
        avg_weight = sum(STAT_WEIGHTS.values()) / float(len(STAT_WEIGHTS))
        stats_sum += avg_weight * float(rs.get("count", 0)) * float(rs.get("amount", 0))
    # Others
    spts  = float(min_from_maybe_range(eff.get("skill_pts", 0)))
    hints = len(eff.get("hints", []))
    bond  = float(min_from_maybe_range(eff.get("bond", 0)))
    mood  = float(min_from_maybe_range(eff.get("mood", 0)))
    return (W_ENERGY*energy + W_STAT*stats_sum + W_SKILLPTS*spts +
            W_HINT*hints + W_BOND*bond + W_MOOD*mood)

def choose_default_preference(options: Dict[str, List[Dict[str, Any]]]) -> int:
    """
    Worst-case (min) over outcomes per option; ties prefer lower option index.
    """
    best_key = 1
    best_score = float("-inf")
    for k, outs in options.items():
        if not outs:
            continue
        worst_case = min(score_outcome(o) for o in outs)
        k_int = int(k) if str(k).isdigit() else 1
        if worst_case > best_score or (worst_case == best_score and k_int < best_key):
            best_score = worst_case
            best_key = k_int
    return best_key

# ================================ HTML MODE =================================
def soup_from_args(args: argparse.Namespace) -> BeautifulSoup:
    if args.html_file:
        html = open(args.html_file, "r", encoding="utf-8", errors="ignore").read()
        dbg(args.debug, f"[DEBUG] Loaded HTML: {args.html_file} ({len(html)} bytes)")
        return BeautifulSoup(html, "lxml")
    if args.url:
        ensure_requests()
        r = requests.get(args.url, timeout=30)
        r.raise_for_status()
        dbg(args.debug, f"[DEBUG] Fetched URL: {args.url} ({len(r.text)} bytes)")
        return BeautifulSoup(r.text, "lxml")
    raise SystemExit("Provide --html-file or --url for HTML mode, or use JSON mode flags.")

def find_support_items(soup: BeautifulSoup, debug: bool) -> List[Tag]:
    items = soup.select('div[class^="eventhelper_listgrid_item__"], div[class*=" eventhelper_listgrid_item__"]')
    dbg(debug, f"[DEBUG] Found support items: {len(items)}")
    return items

def extract_support_name(item: Tag, debug: bool) -> str:
    center = item.select_one('div[style*="text-align: center"]')
    name = ""
    if center:
        divs = center.find_all("div", recursive=False)
        if len(divs) >= 2:
            name = T(divs[1].get_text())
    if not name:
        cand = item.find("div")
        name = T(cand.get_text()) if cand else ""
    dbg(debug, f"[DEBUG] Support name: {name!r}")
    return name

def find_trainee_items(soup: BeautifulSoup, debug: bool) -> List[Tag]:
    items: List[Tag] = []
    for a in soup.select('a[href^="/umamusume/characters/"]'):
        center = a.find_parent("div", attrs={"style": lambda s: isinstance(s, str) and "text-align: center" in s})
        if not center:
            continue
        root = center.parent
        if not isinstance(root, Tag):
            continue
        if root.select_one('div[class^="eventhelper_ewrapper__"], div[class*=" eventhelper_ewrapper__"]'):
            if root not in items:
                items.append(root)
    dbg(debug, f"[DEBUG] Found trainee items: {len(items)}")
    return items

def extract_trainee_name(item: Tag, debug: bool) -> str:
    name = extract_support_name(item, debug)
    dbg(debug, f"[DEBUG] Trainee name: {name!r}")
    return name

def normalize_label(label: str) -> str:
    l = label.strip().lower()
    if "top" in l or re.fullmatch(r"1", l): return "top"
    if "mid" in l or "middle" in l or re.fullmatch(r"2", l): return "mid"
    if "bot" in l or "bottom" in l or re.fullmatch(r"3", l): return "bot"
    if re.search(r"\boption\s*1\b", l): return "top"
    if re.search(r"\boption\s*2\b", l): return "mid"
    if re.search(r"\boption\s*3\b", l): return "bot"
    if m := re.match(r"^(?:no\.?\s*)?(\d+)\s*[.)]?$", l):
        return m.group(1)
    return "top"

def parse_effects_from_text(txt: str) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    eff: Dict[str, Any] = {}
    alt_eff: Optional[Dict[str, Any]] = None

    # All stats
    m = RE_ALL_STATS.search(txt)
    if m:
        val = int(m.group(2))
        eff.update({"speed": val, "stamina": val, "power": val, "guts": val, "wit": val})

    # Random stats
    m = RE_RANDOM_STATS.search(txt)
    if m:
        cnt, val = int(m.group(1)), int(m.group(2))
        eff["stats"] = val
        if cnt > 1:
            eff.setdefault("random_stats", {"count": cnt, "amount": val})

    # Energy range or single
    m_range = RE_ENERGY_RANGE.search(txt)
    if m_range:
        val1, val2 = int(m_range.group(1)), int(m_range.group(2))
        eff["energy"] = val1
        alt_eff = {"energy": val2}
    else:
        m = RE_ENERGY.search(txt)
        if m:
            eff["energy"] = int(m.group(1))

    # Bond / Skill Pts
    m = RE_BOND.search(txt);       eff["bond"]      = int(m.group(1)) if m else eff.get("bond")
    m = RE_SKILLPTS.search(txt);   eff["skill_pts"] = int(m.group(1)) if m else eff.get("skill_pts")

    # Mood (explicit or textual up/down)
    m = RE_MOOD.search(txt)
    if m: eff["mood"] = int(m.group(1))
    else:
        if RE_MOTIV_UP.search(txt):   eff["mood"] = 1
        if RE_MOTIV_DOWN.search(txt): eff["mood"] = -1

    # Last trained stat
    m = RE_LAST_TRAINED_STAT.search(txt)
    if m:
        eff["last_trained_stat"] = int(m.group(1))

    # Individual stat ranges or singles
    for k, rx_range in STAT_RX_RANGE.items():
        if m := rx_range.search(txt):
            val1, val2 = int(m.group(1)), int(m.group(2))
            eff[k] = val1
            if alt_eff is None:
                alt_eff = {}
            alt_eff[k] = val2
            break
    else:
        for k, rx in STAT_RX.items():
            if m := rx.search(txt):
                eff[k] = int(m.group(1))

    clean_eff = {k: v for k, v in eff.items() if v not in (None, "", [], {})}
    clean_alt = {k: v for k, v in (alt_eff or {}).items() if v not in (None, "", [], {})} if alt_eff else None
    return clean_eff, clean_alt

def parse_right_cell(right: Tag, debug: bool) -> List[Dict[str, Any]]:
    outcomes: List[Dict[str, Any]] = []
    base_effect: Dict[str, Any] = {}
    base_hints: List[str] = []
    base_statuses: List[str] = []
    optionals: List[Dict[str, Any]] = []
    active_optional: Optional[Dict[str, Any]] = None
    has_range_variation: bool = False
    range_variations: List[Dict[str, Any]] = []

    def make_outcome(effect: Dict[str, Any], hints_seq: List[str], statuses_seq: List[str]) -> Dict[str, Any]:
        out: Dict[str, Any] = {**effect}
        if hints_seq: out["hints"] = hints_seq[:]
        if statuses_seq:
            out["status"] = statuses_seq[0] if len(statuses_seq) == 1 else statuses_seq[:]
        return out

    def push(out: Dict[str, Any]) -> None:
        if out and out not in outcomes:
            outcomes.append(out)

    def flush():
        nonlocal base_effect, base_hints, base_statuses, optionals, active_optional, has_range_variation, range_variations
        base_present = bool(base_effect or base_hints or base_statuses)
        if has_range_variation and range_variations:
            # primary
            if base_present:
                push(make_outcome(base_effect, base_hints, base_statuses))
            for opt in optionals:
                combined = {**base_effect}
                for k, v in opt.get("effects", {}).items():
                    combined[k] = combined.get(k, 0) + v if isinstance(v, (int, float)) and isinstance(combined.get(k), (int, float)) else v
                push(make_outcome(combined, base_hints + opt.get("hints", []), base_statuses + opt.get("statuses", [])))
            # alternates
            for alt_vals in range_variations:
                alt_effect = {**base_effect, **alt_vals}
                if base_present:
                    push(make_outcome(alt_effect, base_hints, base_statuses))
                for opt in optionals:
                    combined = {**alt_effect}
                    for k, v in opt.get("effects", {}).items():
                        combined[k] = combined.get(k, 0) + v if isinstance(v, (int, float)) and isinstance(combined.get(k), (int, float)) else v
                    push(make_outcome(combined, base_hints + opt.get("hints", []), base_statuses + opt.get("statuses", [])))
        else:
            if base_present:
                push(make_outcome(base_effect, base_hints, base_statuses))
            for opt in optionals:
                combined = {**base_effect}
                for k, v in opt.get("effects", {}).items():
                    combined[k] = combined.get(k, 0) + v if isinstance(v, (int, float)) and isinstance(combined.get(k), (int, float)) else v
                push(make_outcome(combined, base_hints + opt.get("hints", []), base_statuses + opt.get("statuses", [])))

        base_effect, base_hints, base_statuses = {}, [], []
        optionals.clear()
        active_optional = None
        has_range_variation = False
        range_variations.clear()

    lines = right.find_all("div", recursive=False)
    dbg(debug, f"          [DEBUG] right-cell lines: {len(lines)}")
    for li in lines:
        classes = li.get("class") or []
        if any("eventhelper_random_text__" in c or "eventhelper_divider_or__" in c for c in classes):
            dbg(debug, f"            [DEBUG] separator: {T(li.get_text())!r} → flush")
            flush(); continue

        txt = T(li.get_text(" ", strip=True))
        low = txt.lower()

        # Hints / statuses via anchors
        anchor_texts = []
        for a in li.select('.utils_linkcolor__rvv3k, a[href*="/umamusume/skills/"]'):
            nm = T(a.get_text())
            if nm: anchor_texts.append(nm)

        line_hints: List[str] = []
        line_statuses: List[str] = []
        clean_txt = txt.replace("(random)", "").strip()
        if anchor_texts:
            if "status" in low: line_statuses.extend(anchor_texts)
            elif "hint" in low: line_hints.extend(anchor_texts)
            else: line_hints.extend(anchor_texts)
        else:
            if "status" in low and clean_txt: line_statuses.append(clean_txt)
            if "hint" in low and clean_txt:   line_hints.append(clean_txt)

        eff, alt_eff = parse_effects_from_text(txt)
        is_random_line = "(random" in low
        dbg(debug, f"            [DEBUG] line: {txt!r} → eff={eff or {}} alt_eff={alt_eff or {}} hints={line_hints} statuses={line_statuses} random={is_random_line}")

        if alt_eff:
            has_range_variation = True
            range_variations.append(alt_eff)
            for k, v in eff.items():
                base_effect[k] = base_effect.get(k, 0) + v if isinstance(v, (int, float)) and isinstance(base_effect.get(k), (int, float)) else v
            base_hints.extend(line_hints); base_statuses.extend(line_statuses)
        elif is_random_line:
            if not eff and not line_hints and not line_statuses:
                continue
            if active_optional is None:
                active_optional = {"effects": {}, "hints": [], "statuses": []}
                optionals.append(active_optional)
            opt_eff = active_optional["effects"]
            for k, v in eff.items():
                opt_eff[k] = opt_eff.get(k, 0) + v if isinstance(v, (int, float)) and isinstance(opt_eff.get(k), (int, float)) else v
            active_optional["hints"].extend(line_hints); active_optional["statuses"].extend(line_statuses)
        else:
            active_optional = None
            for k, v in eff.items():
                base_effect[k] = base_effect.get(k, 0) + v if isinstance(v, (int, float)) and isinstance(base_effect.get(k), (int, float)) else v
            base_hints.extend(line_hints); base_statuses.extend(line_statuses)

    flush()
    return outcomes

def parse_events_in_card(item: Tag, debug: bool) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    section_blocks: List[Tuple[Optional[Tag], List[Tag]]] = []
    raw_sections = item.select('div[class^="eventhelper_elist__"], div[class*=" eventhelper_elist__"]')
    for sec in raw_sections:
        sec_header = sec.select_one('.sc-fc6527df-0')
        wrappers = sec.select('div[class^="eventhelper_ewrapper__"], div[class*=" eventhelper_ewrapper__"]')
        section_blocks.append((sec_header, wrappers))

    if not section_blocks:
        headers = item.select('div.sc-fc6527df-0')
        for header in headers:
            listgrid = header.find_next_sibling(
                lambda t: isinstance(t, Tag) and any(cls.startswith("eventhelper_listgrid__") for cls in (t.get("class") or []))
            )
            if not isinstance(listgrid, Tag):
                continue
            wrappers = listgrid.select('div[class^="eventhelper_ewrapper__"], div[class*=" eventhelper_ewrapper__"]')
            if wrappers:
                section_blocks.append((header, wrappers))

    dbg(debug, f"[DEBUG]   sections: {len(section_blocks)}")

    for s_idx, (header, wrappers) in enumerate(section_blocks, 1):
        sec_title = T(header.get_text()) if header else ""
        if "After a Race" in sec_title: default_type = "special"
        elif "Chain" in sec_title:      default_type = "chain"
        else:                           default_type = "random"
        dbg(debug, f"[DEBUG]     section[{s_idx}] '{sec_title}' → default_type={default_type}")
        for w_idx, w in enumerate(wrappers, 1):
            h = w.select_one('.tooltips_ttable_heading__DK4_X')
            title = ""
            if h:
                parts = [T(s) for s in h.stripped_strings if T(s)]
                title = parts[0] if parts else ""
            etype = default_type; step = 1
            if m := RE_CHAIN_HDR.match(title):
                arrows, tail = m.groups()
                step = len(arrows); title = T(tail); etype = "chain"
            grid = w.select_one('div[class^="eventhelper_egrid__"], div[class*=" eventhelper_egrid__"]')
            if not grid: continue
            left_cells = grid.select('div.eventhelper_leftcell__Xzdy1')
            labels = [normalize_label(T(l.get_text())) for l in left_cells]
            uniq = []
            for lab in labels:
                if lab not in uniq: uniq.append(lab)
            if set(uniq) == {"top", "bot"}:
                mapping = {"top": "1", "bot": "2"}
            elif set(uniq) == {"top", "mid", "bot"}:
                mapping = {"top": "1", "mid": "2", "bot": "3"}
            else:
                mapping = {lab: str(i) for i, lab in enumerate(uniq, 1)}

            options: Dict[str, List[Dict[str, Any]]] = {}
            for left in left_cells:
                raw_label = T(left.get_text())
                lab = normalize_label(raw_label)
                key = mapping.get(lab, "1")
                right = left.find_next_sibling('div')
                if right:
                    outcomes = parse_right_cell(right, debug)
                    if outcomes:
                        options.setdefault(key, []).extend(outcomes)
            if not options: continue
            default_pref = choose_default_preference(options)
            out.append({
                "type": etype,
                "chain_step": step,
                "name": title,
                "options": options,
                "default_preference": default_pref
            })
    return out

# ================================ JSON MODE =================================
ATTRIBUTE_MAP = {
    "speed": "SPD",
    "stamina": "STA",
    "power": "PWR",
    "guts": "GUTS",
    "intelligence": "WIT",
    "friend": "PAL",
}

def load_skill_data(file_path: str, debug: bool) -> Dict[str, str]:
    lookup: Dict[str, str] = {}
    if not file_path: return lookup
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for skill in data:
            sid = str(skill.get("id")); name = skill.get("name")
            if sid and isinstance(name, str):
                lookup[sid] = name
        dbg(debug, f"[DEBUG] Loaded {len(lookup)} skills from {file_path}.")
    except Exception as e:
        print(f"[WARN] Skills file issue '{file_path}': {e}", file=sys.stderr)
    return lookup

def load_status_data(file_path: str, debug: bool) -> Dict[str, str]:
    lookup: Dict[str, str] = {}
    if not file_path: return lookup
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        lookup = {str(k): v for k, v in data.items() if isinstance(v, str)}
        dbg(debug, f"[DEBUG] Loaded {len(lookup)} statuses from {file_path}.")
    except Exception as e:
        print(f"[WARN] Status file issue '{file_path}': {e}", file=sys.stderr)
    return lookup

def parse_effects_from_event_dict(event_dict: Dict[str, Any], skill_map: Dict[str, str], status_map: Dict[str, str]) -> List[Dict[str, Any]]:
    """
    Gametora 'r' list: 'di' splits outcomes. 'sp/st/po/gu/in/en/pt/bo' → stats/energy/points/bond.
    'sk' single hint (id in 'd'), 'sr' hint roll (list), 'se' status, 'sg' skill obtain, 'ha' heal all.
    Values can be numbers or strings like '+5/+10' → we keep raw for export, score with min_from_maybe_range.
    """
    outcomes: List[Dict[str, Any]] = []
    cur: Dict[str, Any] = {}

    def push_current():
        if any(v not in (None, 0, [], "", {}) for v in cur.values()):
            outcomes.append({k: v for k, v in cur.items() if v not in (None, 0, [], "", {})})

    for item in event_dict.get('r', []):
        t = item.get('t'); v = item.get('v'); d = item.get('d')
        if t == 'di':
            push_current(); cur = {}
            continue
        if t == 'sp': cur['speed'] = v
        elif t == 'st': cur['stamina'] = v
        elif t == 'po': cur['power'] = v
        elif t == 'gu': cur['guts'] = v
        elif t == 'in': cur['wit'] = v
        elif t == 'en': cur['energy'] = v
        elif t == 'pt': cur['skill_pts'] = v
        elif t == 'bo': cur['bond'] = v
        elif t == 'sk':
            sid = str(d or "")
            cur.setdefault('hints', []).append(f"{skill_map.get(sid, f'Skill ID: {sid}')} ({v})")
        elif t == 'sr':
            skills = []
            for s in (d or []):
                sid = str(s.get('d', '')); sv = s.get('v')
                skills.append(f"{skill_map.get(sid, f'Skill ID: {sid}')} ({sv})")
            if skills:
                cur.setdefault('hints', []).append(" / ".join(skills))
        elif t == 'se':
            cur.setdefault("status", status_map.get(str(d), f"Unknown Status {d!r}"))
        elif t == 'sg':
            sid = str(d or "")
            cur.setdefault("status", f"Obtain {skill_map.get(sid, f'Skill ID: {sid}')}")
        elif t == 'ha':
            cur.setdefault("status", "Heal all negative status effects")
        elif t == 'ee':
            cur.setdefault("chain_end", True)

    push_current()
    if not outcomes:
        outcomes.append({})
    return outcomes

def parse_events_from_json_data(event_data: Dict[str, Any], debug: bool, skill_map: Dict[str, str], status_map: Dict[str, str], period: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    lang = 'en' if 'en' in event_data else 'ja'
    try:
        events_struct = json.loads(event_data.get(lang, '{}'))
    except json.JSONDecodeError:
        dbg(debug, "[ERROR] Could not decode eventData JSON string."); return out

    def choose_list(block: Dict[str, Any]) -> List[Any]:
        if not period: return block.get('c', [])
        hist = block.get('history', [])
        if not hist:   return block.get('c', [])
        hit = next((h for h in hist if h.get("period") == period), None)
        if not hit:    return block.get('c', [])
        data = hit.get('data', [])
        return data.get('c', []) if isinstance(data, dict) else block.get('c', [])

    def parse_block(events: List[Any], etype: str, step_start: int = 1) -> int:
        chain_step = step_start
        for ev in events:
            title = ev.get('n', 'Unknown')
            options: Dict[str, List[Dict[str, Any]]] = {}
            for idx, choice in enumerate(choose_list(ev), 1):
                option_key = str(idx)
                options[option_key] = parse_effects_from_event_dict(choice, skill_map, status_map)
            if options:
                out.append({
                    "type": etype,
                    "chain_step": chain_step if etype == "chain" else 1,
                    "name": title,
                    "options": options,
                    "default_preference": choose_default_preference(options)
                })
                dbg(debug, f"[INFO] Parsed {etype} event: {title!r} (step {chain_step if etype=='chain' else 1})")
                if etype == "chain": chain_step += 1
        return chain_step

    # Random-like blocks
    for key in ('random', 'version', 'wchoice', 'outings', 'nochoice'):
        parse_block(events_struct.get(key, []), 'random')
    # Chain block
    parse_block(events_struct.get('arrows', []), 'chain', step_start=1)
    return out

def fetch_and_parse_cards(slugs: List[str], card_type: str, skill_lookup: Dict[str, str], status_lookup: Dict[str, str], period: str, img_dir: Optional[str], download_images: bool, debug: bool) -> List[Dict[str, Any]]:
    ensure_requests()
    results: List[Dict[str, Any]] = []
    if not slugs: return results

    # Prepare image dir if requested
    if download_images and img_dir:
        if not os.path.exists(img_dir):
            os.makedirs(img_dir, exist_ok=True)

    # img class patterns on Gametora
    SUPPORT_IMG_CLASS_PATTERN = re.compile(r"^supports_infobox_top_image__")
    CHARACTER_IMG_CLASS_PATTERN = re.compile(r"^characters_infobox_character_image__")

    for slug in slugs:
        url = (SUPPORT_BASE_URL if card_type == "support" else CHARACTER_BASE_URL) + slug
        dbg(debug, f"[DEBUG] Fetching {card_type} URL: {url}")
        try:
            r = requests.get(url, timeout=20); r.raise_for_status()
        except Exception as e:
            print(f"[WARN] Failed to fetch {slug}: {e}", file=sys.stderr); continue

        soup = BeautifulSoup(r.content, 'html.parser')
        next_tag = soup.find(id="__NEXT_DATA__")
        if not next_tag:
            print(f"[WARN] __NEXT_DATA__ not found for {slug}", file=sys.stderr); continue

        try:
            data = json.loads(next_tag.decode_contents())
            page_props = data['props']['pageProps']
            item_data  = page_props['itemData']
            event_data = page_props['eventData']
        except Exception as e:
            print(f"[ERROR] JSON parse error for {slug}: {e}", file=sys.stderr); continue

        # Meta
        name = item_data.get("char_name", "Unknown") if card_type == "support" else item_data.get("name_en", "Unknown")
        rarity_code = item_data.get("rarity")
        rarity = "SSR" if rarity_code == 3 else "SR" if rarity_code == 2 else "R" if rarity_code == 1 else "None"
        version = item_data.get("version", None)
        raw_attr = (item_data.get("type", "unknown") or "").lower()
        attribute = ATTRIBUTE_MAP.get(raw_attr, raw_attr.upper() if raw_attr else "None")

        # Image (optional)
        if download_images and img_dir:
            img_tag = soup.find("img", class_=SUPPORT_IMG_CLASS_PATTERN) if card_type == "support" else soup.find("div", class_=CHARACTER_IMG_CLASS_PATTERN)
            if img_tag and card_type == "trainee":
                img_tag = img_tag.find("span").find("img") if img_tag.find("span") else None
            img_url = None
            if img_tag and img_tag.get('src'):
                cleaned_src = str(img_tag['src']).lstrip('/')
                img_url = BASE_URL + '/' + cleaned_src
                try:
                    ir = requests.get(img_url, timeout=12); ir.raise_for_status()
                    ext = os.path.splitext(img_url.split('?')[0])[-1] or ".png"
                    fname = f"{name}_{attribute}_{rarity}{ext}" if card_type == "support" else f"{name} ({(version or '').replace('_',' ').title()})_profile{ext}"
                    sub = os.path.join(img_dir, card_type)
                    os.makedirs(sub, exist_ok=True)
                    with open(os.path.join(sub, fname), "wb") as f:
                        f.write(ir.content)
                    dbg(debug, f"[INFO] Downloaded image: {os.path.join(sub, fname)}")
                except Exception as e:
                    print(f"[WARN] Image download failed for {slug}: {e}", file=sys.stderr)

        # Events
        events = parse_events_from_json_data(event_data, debug, skill_lookup, status_lookup, period)
        obj = {
            "type": "support" if card_type == "support" else "trainee",
            "name": name if card_type == "support" else (f"{name} ({(version or '').replace('_',' ').title()})" if version else name),
            "rarity": rarity if card_type == "support" else "None",
            "attribute": attribute if card_type == "support" else "None",
            "id": f"{name}_{attribute}_{rarity}".strip("_") if card_type == "support" else f"{name}_profile",
            "choice_events": events
        }
        results.append(obj)
        dbg(debug, f"[DEBUG] Parsed {card_type} '{obj['name']}' with {len(events)} events.")
    return results

# ================================== MAIN ====================================
def main():
    ap = argparse.ArgumentParser(description="Scrape Umamusume event data from HTML Event Viewer pages and/or Gametora JSON pages.")
    # HTML mode
    ap.add_argument("--html-file", help="Saved Event Viewer HTML (entire page)")
    ap.add_argument("--url", help="Event Viewer URL (HTML mode)")
    ap.add_argument("--support-defaults", default="", help='HTML mapping: "NameA-RAR-ATTR|NameB-RAR-ATTR|..."')
    # JSON mode
    ap.add_argument("--supports-card", type=str, help="Comma-separated Gametora support slugs (e.g., 30027-mejiro-palmer,20029-seeking-the-pearl)")
    ap.add_argument("--characters-card", type=str, help="Comma-separated Gametora character slugs (e.g., 105602-matikanefukukitaru)")
    ap.add_argument("--skills", type=str, default="in_game/skills.json", help="Skills dataset (id->name)")
    ap.add_argument("--status", type=str, default="in_game/status.json", help="Status dataset (id->name)")
    ap.add_argument("--period", type=str, default="", help="Event history period key to prefer (e.g., pre_first_anni)")
    ap.add_argument("--images", action="store_true", help="Download card images (JSON mode)")
    ap.add_argument("--img-dir", type=str, default="images", help="Target folder for images (if --images)")
    ap.add_argument("--clear-images", action="store_true", help="Clear --img-dir before downloading")
    # Common
    ap.add_argument("--out", required=True, help="Output JSON file (array of supports/trainees)")
    ap.add_argument("--debug", action="store_true", help="Verbose debug prints")
    args = ap.parse_args()

    all_entries: List[Dict[str, Any]] = []

    # ---------- HTML path ----------
    if args.html_file or args.url:
        soup = soup_from_args(args)
        support_items = find_support_items(soup, args.debug)
        trainee_items = find_trainee_items(soup, args.debug)
        defaults = parse_support_defaults(args.support_defaults)

        for idx, item in enumerate(support_items):
            name = extract_support_name(item, args.debug)
            if not name:
                dbg(args.debug, f"[WARN] Support[{idx}] has no name; skipping."); continue
            rarity, attr = defaults.get(name.lower(), ("", ""))
            if not rarity or not attr:
                dbg(args.debug, f"[WARN] No defaults for '{name}'. Supply via --support-defaults 'Name-RAR-ATTR|...'")
            events = parse_events_in_card(item, args.debug)
            entry = {
                "type": "support",
                "name": name,
                "rarity": rarity or "None",
                "attribute": attr or "None",
                "id": f"{name}_{attr}_{rarity}".strip("_"),
                "choice_events": events
            }
            all_entries.append(entry)

        for idx, item in enumerate(trainee_items):
            name_full = extract_trainee_name(item, args.debug) or ""
            # strip "(Original)" suffix if any
            name = re.sub(r'\s*\(Original\)\s*$', '', name_full, flags=re.IGNORECASE).strip() or name_full
            events = parse_events_in_card(item, args.debug)
            all_entries.append({
                "type": "trainee",
                "name": name,
                "rarity": "None",
                "attribute": "None",
                "id": f"{name}_profile",
                "choice_events": events
            })

    # ---------- JSON path ----------
    supports_slugs   = [s.strip() for s in (args.supports_card or "").split(",") if s.strip()]
    character_slugs  = [s.strip() for s in (args.characters_card or "").split(",") if s.strip()]

    if supports_slugs or character_slugs:
        skill_lookup  = load_skill_data(args.skills, args.debug)
        status_lookup = load_status_data(args.status, args.debug)
        # Clear images dir if requested
        if args.images and args.img_dir and args.clear_images and os.path.exists(args.img_dir):
            print(f"[INFO] Clearing existing content in {args.img_dir}...")
            for item in os.listdir(args.img_dir):
                p = os.path.join(args.img_dir, item)
                try:
                    if os.path.isfile(p) or os.path.islink(p): os.unlink(p)
                    elif os.path.isdir(p): shutil.rmtree(p)
                except Exception as e:
                    print(f"[WARN] Failed to delete {p}: {e}", file=sys.stderr)
        # Fetch & parse
        all_entries.extend(fetch_and_parse_cards(supports_slugs, "support",  skill_lookup, status_lookup, args.period, args.img_dir, args.images, args.debug))
        all_entries.extend(fetch_and_parse_cards(character_slugs, "trainee", skill_lookup, status_lookup, args.period, args.img_dir, args.images, args.debug))

    if not all_entries:
        raise SystemExit("No entries were parsed. Provide HTML (--html-file/--url) and/or JSON slugs (--supports-card/--characters-card).")

    # ---------- Write ----------
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(all_entries, f, ensure_ascii=False, indent=2)
    print(f"[OK] Wrote {len(all_entries)} entries → {args.out}")

if __name__ == "__main__":
    main()
