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
RE_ENERGY     = re.compile(r"\benergy\b\s*"+_RE_INT, re.I)
RE_BOND       = re.compile(r"\bbond\b\s*"+_RE_INT, re.I)
RE_SKILLPTS   = re.compile(r"\bskill\s*(?:points|pts)\b\s*"+_RE_INT, re.I)
RE_MOOD       = re.compile(r"\bmood\b\s*"+_RE_INT, re.I)
RE_MOTIV_UP   = re.compile(r"\b(mood|motivation)\b.*\b(up|good)\b", re.I)
RE_MOTIV_DOWN = re.compile(r"\b(mood|motivation)\b.*\b(down|bad)\b", re.I)

STAT_RX = {
    "speed":   re.compile(r"\bspeed\b\s*"+_RE_INT, re.I),
    "stamina": re.compile(r"\bstamina\b\s*"+_RE_INT, re.I),
    "power":   re.compile(r"\bpower\b\s*"+_RE_INT, re.I),
    "guts":    re.compile(r"\bguts\b\s*"+_RE_INT, re.I),
    "wit":     re.compile(r"\b(?:wit|wis|wisdom|int|intelligence)\b\s*"+_RE_INT, re.I),
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

# --------------------------- parsing helpers --------------------------------
def normalize_label(label: str) -> str:
    l = label.lower()
    if "top" in l or re.fullmatch(r"1", l): return "top"
    if "mid" in l or "middle" in l or re.fullmatch(r"2", l): return "mid"
    if "bot" in l or "bottom" in l or re.fullmatch(r"3", l): return "bot"
    if re.search(r"\boption\s*1\b", l): return "top"
    if re.search(r"\boption\s*2\b", l): return "mid"
    if re.search(r"\boption\s*3\b", l): return "bot"
    return "top"

def parse_effects_from_text(txt: str) -> Dict[str, Any]:
    eff: Dict[str, Any] = {}
    # All stats
    m = RE_ALL_STATS.search(txt)
    if m:
        val = int(m.group(2))
        eff.update({"speed": val, "stamina": val, "power": val, "guts": val, "wit": val})
    # Random stats
    m = RE_RANDOM_STATS.search(txt)
    if m:
        cnt, val = int(m.group(1)), int(m.group(2))
        eff.setdefault("random_stats", {"count": cnt, "amount": val})
    # Individual effects
    m = RE_ENERGY.search(txt);     eff["energy"]    = int(m.group(1)) if m else eff.get("energy")
    m = RE_BOND.search(txt);       eff["bond"]      = int(m.group(1)) if m else eff.get("bond")
    m = RE_SKILLPTS.search(txt);   eff["skill_pts"] = int(m.group(1)) if m else eff.get("skill_pts")
    m = RE_MOOD.search(txt)
    if m: eff["mood"] = int(m.group(1))
    else:
        if RE_MOTIV_UP.search(txt):   eff["mood"] = 1
        if RE_MOTIV_DOWN.search(txt): eff["mood"] = -1
    for k, rx in STAT_RX.items():
        if m := rx.search(txt):
            eff[k] = int(m.group(1))
    return {k: v for k, v in eff.items() if v not in (None, "", [], {})}

def parse_right_cell(right: Tag, debug: bool) -> List[Dict[str, Any]]:
    outcomes: List[Dict[str, Any]] = []
    cur: Dict[str, Any] = {}
    hints: List[str] = []

    def flush():
        nonlocal cur, hints
        if hints:
            cur = {**cur, "hints": hints[:] }
        if cur:
            outcomes.append(cur)
        cur, hints[:] = {}, []

    lines = right.find_all("div", recursive=False)
    dbg(debug, f"          [DEBUG] right-cell lines: {len(lines)}")
    for li in lines:
        classes = li.get("class") or []
        if any("eventhelper_random_text__" in c or "eventhelper_divider_or__" in c for c in classes):
            dbg(debug, f"            [DEBUG] separator: {T(li.get_text())!r} → flush")
            flush()
            continue

        txt = T(li.get_text(" ", strip=True))

        # collect skill hints on the line
        for a in li.select('.utils_linkcolor__rvv3k, a[href*="/umamusume/skills/"]'):
            nm = T(a.get_text())
            if nm:
                hints.append(nm)

        eff = parse_effects_from_text(txt)
        if eff:
            cur.update(eff)

        dbg(debug, f"            [DEBUG] line: {txt!r} → eff={eff or {}} hints_now={hints}")

    flush()
    return outcomes

def score_outcome(eff: Dict[str, Any]) -> float:
    energy = float(eff.get("energy", 0))
    stats_sum = sum(float(eff.get(k, 0)) for k in ("speed","stamina","power","guts","wit"))
    if isinstance(eff.get("random_stats"), dict):
        rs = eff["random_stats"]
        stats_sum += float(rs.get("count", 0)) * float(rs.get("amount", 0))
    spts   = float(eff.get("skill_pts", 0))
    hints  = len(eff.get("hints", []))
    bond   = float(eff.get("bond", 0))
    mood   = float(eff.get("mood", 0))
    return (W_ENERGY*energy + W_STAT*stats_sum + W_SKILLPTS*spts +
            W_HINT*hints + W_BOND*bond + W_MOOD*mood)

def choose_default_preference(options: Dict[str, List[Dict[str, Any]]]) -> int:
    best_key = 1
    best_score = float("-inf")
    for k, outs in options.items():
        if not outs:
            continue
        avg = sum(score_outcome(o) for o in outs) / float(len(outs))
        if avg > best_score:
            best_score = avg
            best_key = int(k) if str(k).isdigit() else 1
    return best_key

# ------------------------------ event parsing --------------------------------
def parse_events_in_card(item: Tag, debug: bool) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    sections = item.select('div[class^="eventhelper_elist__"], div[class*=" eventhelper_elist__"]')
    dbg(debug, f"[DEBUG]   sections: {len(sections)}")

    for s_idx, sec in enumerate(sections, 1):
        sec_header = sec.select_one('.sc-fc6527df-0')
        sec_title = T(sec_header.get_text()) if sec_header else ""
        default_type = "chain" if "Chain" in sec_title else "random"
        dbg(debug, f"[DEBUG]     section[{s_idx}] '{sec_title}' → default_type={default_type}")

        wrappers = sec.select('div[class^="eventhelper_ewrapper__"], div[class*=" eventhelper_ewrapper__"]')
        dbg(debug, f"[DEBUG]       wrappers: {len(wrappers)}")

        for w_idx, w in enumerate(wrappers, 1):
            h = w.select_one('.tooltips_ttable_heading__DK4_X')
            title = T(h.get_text()) if h else ""
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

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(supports, f, ensure_ascii=False, indent=2)

    print(f"[OK] Wrote {len(supports)} supports → {args.out}")

if __name__ == "__main__":
    main()
