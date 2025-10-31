#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scrape_umamusume_skills.py

Scrapes (or parses a saved HTML of) https://gametora.com/umamusume/skills
to extract every skill entry from the "row" divs the site renders (no <table>).

For each skill, we capture:
- icon_filename (e.g., "utx_ico_skill_10021.png")
- icon_src (absolute URL)
- name (keeps symbols like ◎, ○, ×)
- description
- color_class (the short hashed class that encodes color; e.g., dnlGQR / geDDHx / bhlwbP)
- rarity (derived from color_class: normal/gray, gold, unique; best-effort)
- grade_symbol (◎ / ○ / × if present at end of name)

Usage:
  # From live site
  python scrape_umamusume_skills.py --out skills.json

  # From a saved HTML file (e.g., full_html.txt you provided)
  python scrape_umamusume_skills.py --html-file full_html.txt --out skills.json

Requires:
  pip install beautifulsoup4 lxml requests
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Optional, Tuple

import requests
from bs4 import BeautifulSoup, Tag

BASE_URL = "https://gametora.com"

# Known color/rarity mapping (best-effort; hashed class may change across deploys).
# We still return the raw "color_class" so you can re-map later if needed.
RARITY_BY_COLOR_CLASS = {
    "geDDHx": "gold",    # example seen in your sample HTML
    "bhlwbP": "unique",  # example seen in your sample HTML
    # Anything else => "normal" (gray)
}

CIRCLE_SYMBOLS = ("◎", "○", "×")


def clean_text(s: str) -> str:
    if not s:
        return ""
    s = s.replace("\xa0", " ")
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r"\s*\n\s*", "\n", s)
    return s.strip()


def absolute_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    if url.startswith("http://") or url.startswith("https://"):
        return url
    # treat as site-relative
    return BASE_URL.rstrip("/") + "/" + url.lstrip("/")


def get_grade_symbol(name: str) -> Optional[str]:
    for sym in CIRCLE_SYMBOLS:
        if name.endswith(sym):
            return sym
    return None


def find_color_class(name_div: Tag) -> Tuple[str, str]:
    """
    Returns (color_class, rarity).
    color_class is the short hashed class associated with color (e.g. dnlGQR / geDDHx / bhlwbP).
    We identify it as the class on the name DIV that:
      - is NOT the 'skills_table_jpname__*' class
      - is NOT the 'sc-*-*' generated class prefix
    Everything else in that element's classList is framework boilerplate.
    """
    classes = name_div.get("class", [])
    color_cls = None
    for c in classes:
        if c.startswith("skills_table_jpname__"):
            continue
        if c.startswith("sc-"):
            continue
        # the remaining short token is the color marker
        color_cls = c
        break

    rarity = "normal"
    if color_cls:
        rarity = RARITY_BY_COLOR_CLASS.get(color_cls, "normal")

    return color_cls or "", rarity


def parse_html_skills(html: str):
    soup = BeautifulSoup(html, "lxml")

    # Rows look like:
    # <div class="skills_table_row_ja__XXxOj skills_stripes__1Jy49"> ... </div>
    # We'll match any class starting with 'skills_table_row_' to be safe
    row_selectors = [
        "div[class^='skills_table_row_']",
        "div[class*=' skills_table_row_']",
    ]
    rows = []
    for sel in row_selectors:
        rows.extend(soup.select(sel))
    # Deduplicate while preserving order
    seen_ids = set()
    unique_rows = []
    for r in rows:
        if id(r) not in seen_ids:
            unique_rows.append(r)
            seen_ids.add(id(r))

    skills = []
    for row in unique_rows:
        # Icon: ".skills_table_icon__* img"
        icon_img = row.select_one("div[class^='skills_table_icon__'] img, div[class*=' skills_table_icon__'] img")
        icon_src_rel = icon_img.get("src") if icon_img else None
        icon_src = absolute_url(icon_src_rel) if icon_src_rel else None
        icon_filename = os.path.basename(icon_src_rel) if icon_src_rel else None

        # Name: "div.skills_table_jpname__*"
        name_div = row.select_one("div[class^='skills_table_jpname__'], div[class*=' skills_table_jpname__']")
        name = clean_text(name_div.get_text(" ", strip=True)) if name_div else ""

        # Description: "div.skills_table_desc__*"
        desc_div = row.select_one("div[class^='skills_table_desc__'], div[class*=' skills_table_desc__']")
        description = clean_text(desc_div.get_text(" ", strip=True)) if desc_div else ""

        if not name and not description:
            # Not a skill row we recognize
            continue

        # Color / rarity from the name div's extra hashed class
        color_class, rarity = ("", "normal")
        if name_div:
            color_class, rarity = find_color_class(name_div)

        # Grade symbol at the end of the name (◎/○/×)
        grade_symbol = get_grade_symbol(name)

        skill = {
            "icon_filename": icon_filename,
            "icon_src": icon_src,
            "name": name,
            "description": description,
            "color_class": color_class,  # e.g., dnlGQR (gray), geDDHx (gold), bhlwbP (unique)
            "rarity": rarity,            # "normal" | "gold" | "unique" (best-effort)
            "grade_symbol": grade_symbol # "◎" | "○" | "×" | None
        }
        skills.append(skill)

    return skills


def fetch_or_read(url: str, html_file: Optional[str]) -> str:
    if html_file:
        return Path(html_file).read_text(encoding="utf-8")
    headers = {
        "User-Agent": "Mozilla/5.0 (UmaSkillScraper; +https://gametora.com)",
        "Accept-Language": "en-US,en;q=0.9",
    }
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.text


def main():
    ap = argparse.ArgumentParser(description="Scrape Uma Musume skills from gametora.com.")
    ap.add_argument("--url", default=f"{BASE_URL}/umamusume/skills", help="Page URL to fetch (default: %(default)s)")
    ap.add_argument("--html-file", help="Parse a previously saved HTML file instead of fetching.")
    ap.add_argument("--out", default="skills.json", help="Output JSON file (default: %(default)s)")
    ap.add_argument("--indent", type=int, default=2, help="JSON indent (default: %(default)s)")
    args = ap.parse_args()

    html = fetch_or_read(args.url, args.html_file)
    skills = parse_html_skills(html)

    Path(args.out).write_text(
        json.dumps(skills, ensure_ascii=False, indent=args.indent),
        encoding="utf-8"
    )

    print(f"[OK] Extracted {len(skills)} skills → {args.out}")
    # print a couple of examples
    for s in skills[:5]:
        print(f" - {s['name']} :: {s['description']}")


if __name__ == "__main__":
    main()
