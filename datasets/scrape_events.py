#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Scrape UMA MUSUME Event-Viewer HTML (multiple support cards) into a JSON array.

Key points
- Parse every support card block (eventhelper_listgrid_item__…).
- Robust option mapping: Top/Mid/Bot -> "1"/"2"/"3" (Top/Bot-only -> "1"/"2").
- Split multi-outcome cells ("Randomly either" / "or").
- Effects parsed: energy, mood, bond, skill_pts, stats (speed/stamina/power/guts/wit).
- Handles 'All stats +N' and 'X random stats +N' (kept as {"random_stats":{count,amount}} and used for scoring).
- default_preference picked by score: Energy > Stats > Skill Pts > Hint (bond/mood tie-breakers), averaging outcomes.
- Rarity/Attribute mapping via ONE flag:
    --support-defaults "NameA-RAR-ATTR|NameB-RAR-ATTR|..."
  (Name may contain spaces; we split from the END so hyphens in names are OK.)

Example (single line):
  cls && python scrape_events.py --html-file events_full_html.txt --support-defaults "Matikanefukukitaru-SR-WIT|Seeking the Pearl-SR-GUTS" --out supports_events.json --debug
"""

import argparse
import json
import re
from typing import Any, Dict, List, Optional, Tuple
from bs4 import BeautifulSoup, Tag

try:
    import requests
except Exception:
    requests = None

# -------------------- scoring weights (tweak if needed) ---------------------
W_ENERGY   = 100.0
W_STAT     = 10.0
W_SKILLPTS = 2.0
W_HINT     = 1.0
W_BOND     = 0.3
W_MOOD     = 2.0

# ------------------------------- regexes ------------------------------------
_RE_INT       = r"([+\-]?\d+)"
_RE_RANGE     = r"([+\-]?\d+)\s*/\s*([+\-]?\d+)"  # e.g., "-5/-20" or "10/20"
RE_ENERGY     = re.compile(r"\benergy\b\s*"+_RE_INT, re.I)
RE_ENERGY_RANGE = re.compile(r"\benergy\b\s*"+_RE_RANGE, re.I)
RE_BOND       = re.compile(r"\bbond\b\s*"+_RE_INT, re.I)
RE_SKILLPTS   = re.compile(r"\bskill\s*(?:points|pts)\b\s*"+_RE_INT, re.I)
RE_MOOD       = re.compile(r"\bmood\b\s*"+_RE_INT, re.I)
RE_LAST_TRAINED_STAT = re.compile(r"\blast\s*trained\s*stat\b\s*"+_RE_INT, re.I)
RE_MOTIV_UP   = re.compile(r"\b(mood|motivation)\b.*\b(up|good)\b", re.I)
RE_MOTIV_DOWN = re.compile(r"\b(mood|motivation)\b.*\b(down|bad)\b", re.I)

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

STAT_WEIGHTS = {
    "speed": 5.0,
    "stamina": 4.0,
    "power": 3.0,
    "wit": 2.0,
    "guts": 1.0,
}

# All stats +5 / All parameters +5
RE_ALL_STATS  = re.compile(r"\b(all\s*stats|all\s*parameters|all\s*status)\b\s*"+_RE_INT, re.I)
# 3 random stats +6 / 2 random parameters +10
RE_RANDOM_STATS = re.compile(r"\b(\d+)\s*random\s*(?:stats?|parameters?)\b\s*"+_RE_INT, re.I)

# Chain heading like "(❯❯) Guidance and Friends"
RE_CHAIN_HDR  = re.compile(r"^\(\s*([»❯>]+)\s*\)\s*(.*)$")

# --------------------------------- utils ------------------------------------
def T(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def dbg(on: bool, *args, **kwargs):
    if on:
        print(*args, **kwargs)

def soup_from_args(args: argparse.Namespace) -> BeautifulSoup:
    if args.html_file:
        html = open(args.html_file, "r", encoding="utf-8", errors="ignore").read()
        dbg(args.debug, f"[DEBUG] Loaded HTML: {args.html_file} ({len(html)} bytes)")
        return BeautifulSoup(html, "lxml")
    if args.url:
        if not requests:
            raise SystemExit("`requests` required for --url. pip install requests")
        r = requests.get(args.url, timeout=30)
        r.raise_for_status()
        dbg(args.debug, f"[DEBUG] Fetched URL: {args.url} ({len(r.text)} bytes)")
        return BeautifulSoup(r.text, "lxml")
    raise SystemExit("Provide --html-file or --url")

# --------------------------- support defaults map ---------------------------
def parse_support_defaults(raw: str) -> Dict[str, Tuple[str, str]]:
    """
    Parse "Name-RAR-ATTR|Name2-RAR-ATTR" into {lower_name: (rarity, attr)}.
    Split from the end so hyphens inside names are preserved.
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

# --------------------------- find support card items -------------------------
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

def normalize_trainee_name(name: str) -> str:
    return T(re.sub(r"\s*\([^)]*\)\s*$", "", name or ""))

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
    raw = extract_support_name(item, debug)
    nm = normalize_trainee_name(raw)
    dbg(debug, f"[DEBUG] Trainee name normalized: {nm!r} (raw={raw!r})")
    return nm

# --------------------------- parsing helpers --------------------------------
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
    """
    Parse effects from text. Returns (primary_effect, alternate_effect).
    alternate_effect is None unless range notation is detected (e.g., "Energy -5/-20").
    """
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
    
    # Check for range notation first (e.g., "Energy -5/-20")
    m_range = RE_ENERGY_RANGE.search(txt)
    if m_range:
        val1, val2 = int(m_range.group(1)), int(m_range.group(2))
        eff["energy"] = val1
        alt_eff = {"energy": val2}
    else:
        m = RE_ENERGY.search(txt)
        if m:
            eff["energy"] = int(m.group(1))
    
    # Bond and skill_pts (no range notation seen in practice)
    m = RE_BOND.search(txt);       eff["bond"]      = int(m.group(1)) if m else eff.get("bond")
    m = RE_SKILLPTS.search(txt);   eff["skill_pts"] = int(m.group(1)) if m else eff.get("skill_pts")
    
    # Mood
    m = RE_MOOD.search(txt)
    if m: eff["mood"] = int(m.group(1))
    else:
        if RE_MOTIV_UP.search(txt):   eff["mood"] = 1
        if RE_MOTIV_DOWN.search(txt): eff["mood"] = -1
    
    # Last trained stat
    m = RE_LAST_TRAINED_STAT.search(txt)
    if m:
        eff["last_trained_stat"] = int(m.group(1))
    
    # Individual stats - check for range notation
    for k, rx_range in STAT_RX_RANGE.items():
        if m := rx_range.search(txt):
            val1, val2 = int(m.group(1)), int(m.group(2))
            eff[k] = val1
            if alt_eff is None:
                alt_eff = {}
            alt_eff[k] = val2
            break  # Only one stat should have range notation per line
    else:
        # No range found, check for single values
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
    optionals: List[Dict[str, Any]] = []  # each: {"effects":{}, "hints":[], "statuses":[]}
    active_optional: Optional[Dict[str, Any]] = None
    has_range_variation: bool = False  # Track if we need to create range-based outcomes
    range_variations: List[Dict[str, Any]] = []  # Store alternate values from ranges

    def make_outcome(effect: Dict[str, Any], hints_seq: List[str], statuses_seq: List[str]) -> Dict[str, Any]:
        out: Dict[str, Any] = {**effect}
        if hints_seq:
            out["hints"] = hints_seq[:]
        if statuses_seq:
            if len(statuses_seq) == 1:
                out["status"] = statuses_seq[0]
            else:
                out["statuses"] = statuses_seq[:]
        return out

    def push(out: Dict[str, Any]) -> None:
        if out and out not in outcomes:
            outcomes.append(out)

    def flush():
        nonlocal base_effect, base_hints, base_statuses, optionals, active_optional, has_range_variation, range_variations
        base_present = bool(base_effect or base_hints or base_statuses)
        
        # If we have range variations, generate outcomes for each variation
        if has_range_variation and range_variations:
            # Create outcome with primary values
            if base_present:
                push(make_outcome(base_effect, base_hints, base_statuses))
            for opt in optionals:
                combined: Dict[str, Any] = {**base_effect}
                for k, v in opt.get("effects", {}).items():
                    if k in combined and isinstance(combined[k], (int, float)) and isinstance(v, (int, float)):
                        combined[k] = combined[k] + v
                    else:
                        combined[k] = v
                combined_hints = base_hints + opt.get("hints", [])
                combined_statuses = base_statuses + opt.get("statuses", [])
                push(make_outcome(combined, combined_hints, combined_statuses))
            
            # Create outcomes with alternate values from range
            for alt_vals in range_variations:
                alt_effect = {**base_effect}
                for k, v in alt_vals.items():
                    alt_effect[k] = v
                if base_present:
                    push(make_outcome(alt_effect, base_hints, base_statuses))
                for opt in optionals:
                    combined: Dict[str, Any] = {**alt_effect}
                    for k, v in opt.get("effects", {}).items():
                        if k in combined and isinstance(combined[k], (int, float)) and isinstance(v, (int, float)):
                            combined[k] = combined[k] + v
                        else:
                            combined[k] = v
                    combined_hints = base_hints + opt.get("hints", [])
                    combined_statuses = base_statuses + opt.get("statuses", [])
                    push(make_outcome(combined, combined_hints, combined_statuses))
        else:
            # No range variations, use standard logic
            if base_present:
                push(make_outcome(base_effect, base_hints, base_statuses))
            for opt in optionals:
                combined: Dict[str, Any] = {**base_effect}
                for k, v in opt.get("effects", {}).items():
                    if k in combined and isinstance(combined[k], (int, float)) and isinstance(v, (int, float)):
                        combined[k] = combined[k] + v
                    else:
                        combined[k] = v
                combined_hints = base_hints + opt.get("hints", [])
                combined_statuses = base_statuses + opt.get("statuses", [])
                push(make_outcome(combined, combined_hints, combined_statuses))

        if not base_present and not optionals:
            # nothing parsed for this block
            pass

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
            flush()
            continue

        txt = T(li.get_text(" ", strip=True))
        low = txt.lower()

        anchor_texts = []
        for a in li.select('.utils_linkcolor__rvv3k, a[href*="/umamusume/skills/"]'):
            nm = T(a.get_text())
            if nm:
                anchor_texts.append(nm)

        line_hints: List[str] = []
        line_statuses: List[str] = []
        clean_txt = txt.replace("(random)", "").strip()

        if anchor_texts:
            if "status" in low:
                line_statuses.extend(anchor_texts)
            elif "hint" in low:
                line_hints.extend(anchor_texts)
            else:
                line_hints.extend(anchor_texts)
        else:
            if "status" in low and clean_txt:
                line_statuses.append(clean_txt)
            if "hint" in low and clean_txt:
                line_hints.append(clean_txt)

        eff, alt_eff = parse_effects_from_text(txt)
        is_random_line = "(random" in low

        dbg(debug, f"            [DEBUG] line: {txt!r} → eff={eff or {}} alt_eff={alt_eff or {}} line_hints={line_hints} line_statuses={line_statuses} random={is_random_line}")

        # If we have alt_eff from range notation, mark that we need to generate range variations
        if alt_eff:
            has_range_variation = True
            range_variations.append(alt_eff)
            # Process eff normally into base_effect
            active_optional = None
            for k, v in eff.items():
                if k in base_effect and isinstance(base_effect[k], (int, float)) and isinstance(v, (int, float)):
                    base_effect[k] = base_effect[k] + v
                else:
                    base_effect[k] = v
            base_hints.extend(line_hints)
            base_statuses.extend(line_statuses)
        elif is_random_line:
            if line_statuses:
                # statuses remain optional outcomes
                pass
            elif not eff and line_hints:
                # random hint text without branches: treat as deterministic metadata
                base_hints.extend(line_hints)
                continue
            elif not eff and not line_hints and not line_statuses:
                # nothing to record
                continue
            if active_optional is None:
                active_optional = {"effects": {}, "hints": [], "statuses": []}
                optionals.append(active_optional)
            opt_eff = active_optional["effects"]
            for k, v in eff.items():
                if k in opt_eff and isinstance(opt_eff[k], (int, float)) and isinstance(v, (int, float)):
                    opt_eff[k] = opt_eff[k] + v
                else:
                    opt_eff[k] = v
            active_optional["hints"].extend(line_hints)
            active_optional["statuses"].extend(line_statuses)
        else:
            active_optional = None
            for k, v in eff.items():
                if k in base_effect and isinstance(base_effect[k], (int, float)) and isinstance(v, (int, float)):
                    base_effect[k] = base_effect[k] + v
                else:
                    base_effect[k] = v
            base_hints.extend(line_hints)
            base_statuses.extend(line_statuses)

    flush()
    return outcomes

def score_outcome(eff: Dict[str, Any]) -> float:
    energy = float(eff.get("energy", 0))
    stats_sum = 0.0
    for stat, weight in STAT_WEIGHTS.items():
        stats_sum += weight * float(eff.get(stat, 0))
    if isinstance(eff.get("random_stats"), dict):
        rs = eff["random_stats"]
        avg_weight = sum(STAT_WEIGHTS.values()) / float(len(STAT_WEIGHTS))
        stats_sum += avg_weight * float(rs.get("count", 0)) * float(rs.get("amount", 0))
    spts   = float(eff.get("skill_pts", 0))
    hints  = len(eff.get("hints", []))
    bond   = float(eff.get("bond", 0))
    mood   = float(eff.get("mood", 0))
    return (W_ENERGY*energy + W_STAT*stats_sum + W_SKILLPTS*spts +
            W_HINT*hints + W_BOND*bond + W_MOOD*mood)

def choose_default_preference(options: Dict[str, List[Dict[str, Any]]]) -> int:
    """
    Choose the best option using WORST-CASE scoring for each option.
    This ensures we don't prefer options with potentially bad random outcomes.
    """
    best_key = 1
    best_score = float("-inf")
    for k, outs in options.items():
        if not outs:
            continue
        # Use minimum score (worst case) for this option
        worst_case = min(score_outcome(o) for o in outs)
        if worst_case > best_score:
            best_score = worst_case
            best_key = int(k) if str(k).isdigit() else 1
    return best_key

# ------------------------------ event parsing --------------------------------
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
        if "After a Race" in sec_title:
            default_type = "special"
        elif "Chain" in sec_title:
            default_type = "chain"
        else:
            default_type = "random"
        dbg(debug, f"[DEBUG]     section[{s_idx}] '{sec_title}' → default_type={default_type}")

        dbg(debug, f"[DEBUG]       wrappers: {len(wrappers)}")

        for w_idx, w in enumerate(wrappers, 1):
            h = w.select_one('.tooltips_ttable_heading__DK4_X')
            title = ""
            if h:
                parts = [T(s) for s in h.stripped_strings if T(s)]
                title = parts[0] if parts else ""
            etype = default_type
            step = 1

            if m := RE_CHAIN_HDR.match(title):
                arrows, tail = m.groups()
                step = len(arrows)
                title = T(tail)
                etype = "chain"

            dbg(debug, f"[DEBUG]       wrapper[{w_idx}] title={title!r} type={etype} step={step}")

            grid = w.select_one('div[class^="eventhelper_egrid__"], div[class*=" eventhelper_egrid__"]')
            if not grid:
                dbg(debug, f"[WARN]         no grid; skip")
                continue

            # LEFT labels determine mapping
            left_cells = grid.select('div.eventhelper_leftcell__Xzdy1')
            labels = [normalize_label(T(l.get_text())) for l in left_cells]
            uniq = []
            for lab in labels:
                if lab not in uniq:
                    uniq.append(lab)

            if set(uniq) == {"top", "bot"} or uniq == ["top", "bot"]:
                mapping = {"top": "1", "bot": "2"}
            elif set(uniq) == {"top", "mid", "bot"} or uniq == ["top", "mid", "bot"]:
                mapping = {"top": "1", "mid": "2", "bot": "3"}
            else:
                mapping = {lab: str(i) for i, lab in enumerate(uniq, 1)}  # fallback

            dbg(debug, f"[DEBUG]         left labels={labels} → mapping={mapping}")

            options: Dict[str, List[Dict[str, Any]]] = {}
            for lc_idx, left in enumerate(left_cells, 1):
                raw_label = T(left.get_text())
                lab = normalize_label(raw_label)
                key = mapping.get(lab, "1")
                right = left.find_next_sibling('div')

                dbg(debug, f"[DEBUG]           L{lc_idx}: left='{raw_label}' (norm={lab}) → key={key} | right={bool(right)}")
                if right:
                    outcomes = parse_right_cell(right, debug)
                    if outcomes:
                        options.setdefault(key, []).extend(outcomes)

            if not options:
                dbg(debug, f"[WARN]         event parsed no options; skip")
                continue

            default_pref = choose_default_preference(options)

            out.append({
                "type": etype,
                "chain_step": step,
                "name": title,
                "options": options,
                "default_preference": default_pref
            })

    return out

# ---------------------------------- main ------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--html-file", help="Saved Event Viewer HTML")
    ap.add_argument("--url", help="URL that renders the same block")
    ap.add_argument("--support-defaults", default="", help='Mapping: "NameA-RAR-ATTR|NameB-RAR-ATTR|..."')
    ap.add_argument("--out", required=True, help="Output JSON file (array of supports)")
    ap.add_argument("--debug", action="store_true", help="Verbose debug prints")
    args = ap.parse_args()

    soup = soup_from_args(args)
    items = find_support_items(soup, args.debug)
    trainee_items = find_trainee_items(soup, args.debug)

    defaults = parse_support_defaults(args.support_defaults)

    supports: List[Dict[str, Any]] = []
    for idx, item in enumerate(items, 0):
        name = extract_support_name(item, args.debug)
        if not name:
            dbg(args.debug, f"[WARN] Item[{idx}] has no name; skipping.")
            continue

        rarity, attr = defaults.get(name.lower(), ("", ""))
        if not rarity or not attr:
            dbg(args.debug, f"[WARN] No defaults found for '{name}'. You can pass it as 'Name-RAR-ATTR' in --support-defaults.")

        events = parse_events_in_card(item, args.debug)

        support_obj = {
            "type": "support",
            "name": name,
            "rarity": rarity,
            "attribute": attr,
            "id": f"{name}_{attr}_{rarity}".strip("_"),
            "choice_events": events
        }
        supports.append(support_obj)
        dbg(args.debug, f"[DEBUG] Parsed support '{name}' with {len(events)} events. rarity={rarity}, attr={attr}")

    # Parse trainee blocks (if present)
    for idx, item in enumerate(trainee_items, 0):
        name = extract_trainee_name(item, args.debug)
        if not name:
            dbg(args.debug, f"[WARN] Trainee[{idx}] has no name; skipping.")
            continue

        events = parse_events_in_card(item, args.debug)
        trainee_obj = {
            "type": "trainee",
            "name": name,
            "rarity": "None",
            "attribute": "None",
            "choice_events": events,
        }
        supports.append(trainee_obj)
        dbg(args.debug, f"[DEBUG] Parsed trainee '{name}' with {len(events)} events.")

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(supports, f, ensure_ascii=False, indent=2)

    print(f"[OK] Wrote {len(supports)} entries → {args.out}")

if __name__ == "__main__":
    main()
