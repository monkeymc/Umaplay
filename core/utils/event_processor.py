import json
import fnmatch
import os
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image
import imagehash
from rapidfuzz import fuzz, process
from PIL.Image import Image as PILImage

from core.utils.logger import logger_uma

# -----------------------------
# Paths (adjust if needed)
# -----------------------------
DATASETS_EVENTS = Path("datasets/in_game/events.json")
ASSETS_EVENTS_DIR = Path(
    "assets/events"
)  # /{support|trainee|scenario}/<name>_<rarity>.png
BUILD_DIR = Path("build")  # will hold event_catalog.json
CATALOG_JSON = Path("datasets/in_game/event_catalog.json")


def safe_phash_from_image(img: PILImage) -> Optional[int]:
    """Compute 64-bit pHash from an in-memory PIL image."""
    try:
        ph = imagehash.phash(img)
        return int(str(ph), 16)
    except Exception:
        return None


# -----------------------------
# Utilities
# -----------------------------


def normalize_text(s: str) -> str:
    """Basic normalization robust to punctuation and spacing differences."""
    if not s:
        return ""
    # unify punctuation commonly seen in Uma text (music notes, arrows, full/half width)
    rep = {
        "≫": ">>",
        "«": "<<",
        "»": ">>",
        "♪": " note ",
        "☆": "*",
        "★": "*",
        "　": " ",  # full-width space
        "–": "-",
        "—": "-",
        "―": "-",
        "-": "-",
        "…": "...",
    }
    s2 = s.strip().lower()
    for k, v in rep.items():
        s2 = s2.replace(k, v)
    # collapse spaces
    while "  " in s2:
        s2 = s2.replace("  ", " ")
    return s2


def safe_phash(img_path: Path) -> Optional[int]:
    """Compute 64-bit pHash for an image path, return as python int (or None if missing)."""
    try:
        with Image.open(img_path) as im:
            ph = imagehash.phash(im)  # 64-bit by default
            return int(str(ph), 16)  # store hex→int for portability
    except Exception:
        return None


def hamming_similarity64(a_int: Optional[int], b_int: Optional[int]) -> float:
    """Return similarity in [0,1] from two 64-bit pHash integers. If any None, return 0."""
    if a_int is None or b_int is None:
        return 0.0
    # hamming distance of 64-bit integers
    # Python 3.8+: use int.bit_count()
    dist = (a_int ^ b_int).bit_count()
    return 1.0 - (dist / 64.0)


def find_event_image_path(
    ev_type: str, name: str, rarity: str, attribute: str
) -> Optional[Path]:
    """
    Find an image under assets/events/{ev_type}/<name>_<attribute>_<rarity>.(png|jpg|jpeg|webp).
    ev_type is one of: support|trainee|scenario
    """
    folder = ASSETS_EVENTS_DIR / ev_type
    exts = (".png", ".jpg", ".jpeg", ".webp")

    attr = (attribute or "None").strip()
    rar = (rarity or "None").strip()
    attr_up = attr.upper()

    candidates: List[str] = []

    # Primary (new convention): <name>_<ATTRIBUTE>_<rarity>
    if attr.lower() not in ("none", "null") and rar.lower() not in ("none", "null"):
        candidates.append(f"{name}_{attr_up}_{rar}")

    # Variants in case a pack is missing one dimension:
    #  - <name>_<ATTRIBUTE>
    if attr.lower() not in ("none", "null"):
        candidates.append(f"{name}_{attr_up}")
    #  - <name>_<rarity>
    if rar.lower() not in ("none", "null"):
        candidates.append(f"{name}_{rar}")

    # Legacy: just <name>
    candidates.append(name)

    # Trainee special: profile portrait like "<name>_profile"
    if ev_type == "trainee":
        candidates.insert(0, f"{name}_profile")

    for base in candidates:
        for ext in exts:
            p = folder / f"{base}{ext}"
            if p.exists():
                return p
    return None


# -----------------------------
# Data structures
# -----------------------------


@dataclass
class EventRecord:
    # Stable key: "type/name/rarity/event_name"
    key: str
    key_step: str  # new: step-aware key → ".../event_name#s<step>"
    type: str  # support|trainee|scenario
    name: str  # e.g., "Kitasan Black", "Vodka", "Ura Finale", or "general"
    rarity: str  # e.g., "SSR", "SR", "R", "None"
    attribute: str  # e.g., "SPD", "STA", "PWR", "GUTS", "WIT", "None"
    event_name: str  # e.g., "Paying It Forward"
    chain_step: Optional[int]
    default_preference: Optional[int]  # which option number to pick by default
    options: Dict[str, List[Dict]]  # as-is from JSON (stringified keys for safety)
    title_norm: str  # normalized event_name for fast match
    image_path: Optional[str]  # representative icon path (per name+rarity)
    phash64: Optional[int]  # 64-bit pHash int

    @staticmethod
    def from_json_item(
        parent: Dict,
        ev_item: Dict,
        phash_map: Dict[Tuple[str, str, str, str], Tuple[Optional[str], Optional[int]]],
    ) -> "EventRecord":
        ev_type = parent.get("type", "")
        name = parent.get("name", "")
        rarity = parent.get("rarity", "None") or "None"
        ev_name = ev_item.get("name", "")
        attribute = parent.get("attribute", "None")
        chain_step = ev_item.get("chain_step", None)
        default_pref = ev_item.get("default_preference", None)
        options = ev_item.get("options", {})

        # Make options keys strings for JSON stability
        options_str_keys = {str(k): v for k, v in options.items()}

        title_norm = normalize_text(ev_name)
        key = f"{ev_type}/{name}/{attribute}/{rarity}/{ev_name}"

        img_path, phash = phash_map.get(
            (ev_type, name, rarity, attribute), (None, None)
        )
        return EventRecord(
            key=key,
            key_step=f"{key}#s{chain_step if chain_step is not None else 1}",
            type=ev_type,
            name=name,
            rarity=rarity,
            attribute=attribute,
            event_name=ev_name,
            chain_step=chain_step,
            default_preference=default_pref,
            options=options_str_keys,
            title_norm=title_norm,
            image_path=(str(img_path) if img_path else None),
            phash64=phash,
        )


# -----------------------------
# Build step (offline, local)
# -----------------------------


def build_catalog() -> None:
    """
    Parse datasets/in_game/events.json, compute representative image pHashes once per (type,name,rarity,attribute),
    and produce datasets/in_game/event_catalog.json with one row per *event* (choice_event).
    """
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    if not DATASETS_EVENTS.exists():
        raise FileNotFoundError(f"Missing {DATASETS_EVENTS}")

    with DATASETS_EVENTS.open("r", encoding="utf-8") as f:
        root = json.load(f)

    # Precompute phash for each (type,name,rarity)
    set_data_to_file_and_phash: Dict[
        Tuple[str, str, str, str], Tuple[Optional[str], Optional[int]]
    ] = {}
    seen_set_data = set()

    for parent in root:
        ev_type = parent.get("type", "")
        name = parent.get("name", "")
        rarity = parent.get("rarity", "None") or "None"
        attribute = parent.get("attribute", "None")
        set_data = (ev_type, name, rarity, attribute)
        if set_data in seen_set_data:
            continue
        seen_set_data.add(set_data)

        img_path = find_event_image_path(ev_type, name, rarity, attribute)
        phash = safe_phash(img_path) if img_path else None
        set_data_to_file_and_phash[set_data] = (
            str(img_path) if img_path else None,
            phash,
        )

    # Expand to event records
    records: List[EventRecord] = []
    for parent in root:
        choice_events = parent.get("choice_events", []) or []
        for ev in choice_events:
            rec = EventRecord.from_json_item(parent, ev, set_data_to_file_and_phash)
            records.append(rec)

    # Save compact JSON for runtime
    payload = [asdict(r) for r in records]
    with CATALOG_JSON.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"[build_catalog] Wrote {len(records)} events → {CATALOG_JSON}")


# -----------------------------
# Preferences (overrides)
# -----------------------------


def _generalize_trainee_key(key: str) -> Optional[str]:
    """Map a trainee-specific override key (with optional step suffix) to its general equivalent."""
    try:
        base, sep, step = key.partition("#")
        parts = base.split("/")
        if len(parts) < 5:
            return None
        typ = str(parts[0]).strip().lower()
        name = str(parts[1]).strip().lower()
        attribute = str(parts[2]).strip().lower()
        rarity = str(parts[3]).strip().lower()
        if typ != "trainee":
            return None
        if name in {"general", "", "none", "null"}:
            return None
        if attribute not in {"none", "", "null"}:
            return None
        if rarity not in {"none", "", "null"}:
            return None
        generalized_parts = [
            "trainee",
            "general",
            "None",
            "None",
        ] + parts[4:]
        generalized = "/".join(generalized_parts)
        if sep:
            generalized += sep + step
        return generalized
    except Exception:
        return None


def _build_alias_overrides(overrides: Dict[str, int]) -> Dict[str, int]:
    alias_overrides: Dict[str, int] = {}
    for key, pick in overrides.items():
        alias = _generalize_trainee_key(key)
        if not alias:
            continue
        base_alias, sep, step = alias.partition("#")

        def _store(candidate: str) -> None:
            if not candidate:
                return
            if candidate in overrides or candidate in alias_overrides:
                return
            alias_overrides[candidate] = pick
            logger_uma.debug(
                "[event_prefs] alias override mapped %s → %s (pick=%s)",
                candidate,
                key,
                pick,
            )

        _store(alias)
        _store(base_alias)
        if sep != "#" and base_alias:
            _store(f"{base_alias}#s1")
        elif sep == "#" and base_alias and step and not step.lower().startswith("s"):
            _store(f"{base_alias}#s{step}")
    return alias_overrides


def _match_specific_trainee_override(
    overrides: Dict[str, int], rec: "EventRecord"
) -> Optional[int]:
    target_name = normalize_text(rec.event_name)
    target_step = rec.chain_step or 1
    for key, pick in overrides.items():
        base, _, step = key.partition("#")
        parts = base.split("/")
        if len(parts) < 5:
            continue
        if parts[0].strip().lower() != "trainee":
            continue
        trainee_name = parts[1].strip().lower()
        if trainee_name in {"general", "", "none", "null"}:
            continue
        attribute = parts[2].strip().lower()
        rarity = parts[3].strip().lower()
        if attribute not in {"none", "", "null"}:
            continue
        if rarity not in {"none", "", "null"}:
            continue
        override_event = normalize_text(parts[4])
        if override_event != target_name:
            continue
        step_norm = step.strip().lower()
        step_idx: Optional[int]
        if not step_norm:
            step_idx = 1
        elif step_norm.startswith("s"):
            try:
                step_idx = int(step_norm[1:])
            except ValueError:
                step_idx = None
        else:
            try:
                step_idx = int(step_norm)
            except ValueError:
                step_idx = None
        if step_idx is not None and step_idx != target_step:
            continue
        return int(pick)
    return None


@dataclass
class UserPrefs:
    # exact key → option_number
    overrides: Dict[str, int]
    # wildcard patterns (fnmatch) checked in order
    patterns: List[Tuple[str, int]]
    # fallback per type if nothing else found
    default_by_type: Dict[str, int]
    # alias keys (e.g., trainee/general) derived from overrides
    alias_overrides: Dict[str, int] = field(default_factory=dict)

    @staticmethod
    def load(path: Path) -> "UserPrefs":
        if not path.exists():
            # sensible defaults
            return UserPrefs(
                overrides={},
                patterns=[],
                default_by_type={"support": 1, "trainee": 1, "scenario": 1},
            )
        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        overrides = raw.get("overrides", {}) or {}
        # patterns as ordered list; dict order is preserved in modern Python, but accept both
        patt_src = raw.get("patterns", [])
        if isinstance(patt_src, dict):
            patterns = list(patt_src.items())
        else:
            # expect list of {"pattern": "support/Kitasan*/SSR/*", "pick": 2}
            patterns = [(d.get("pattern", ""), int(d.get("pick", 1))) for d in patt_src]
        default_by_type = raw.get(
            "defaults", {"support": 1, "trainee": 1, "scenario": 1}
        )
        alias_overrides = _build_alias_overrides(overrides)

        return UserPrefs(
            overrides=overrides,
            patterns=patterns,
            default_by_type=default_by_type,
            alias_overrides=alias_overrides,
        )

    # ---- build UserPrefs from the active preset inside config.json ----
    @staticmethod
    def from_config(cfg: dict | None) -> "UserPrefs":
        """
        Pull event prefs from config['presets'][active]['event_setup']['prefs'].
        If anything is missing or malformed, we return sensible defaults.
        """
        cfg = cfg or {}
        presets = cfg.get("presets") or []
        active_id = cfg.get("activePresetId")
        preset = next((p for p in presets if p.get("id") == active_id), None) or (
            presets[0] if presets else None
        )
        if not preset:
            # no presets at all
            return UserPrefs(
                overrides={},
                patterns=[],
                default_by_type={"support": 1, "trainee": 1, "scenario": 1},
            )

        setup = preset.get("event_setup") or {}
        prefs = setup.get("prefs") or {}

        # --- overrides ---
        overrides_in = prefs.get("overrides", {}) or {}
        overrides: Dict[str, int] = {}
        if isinstance(overrides_in, dict):
            for k, v in overrides_in.items():
                try:
                    n = int(v)
                    if n >= 1:  # don't accept 0/negatives
                        overrides[str(k)] = n
                except Exception:
                    # ignore malformed values
                    continue

        alias_overrides = _build_alias_overrides(overrides)

        # --- patterns ---
        patt_src = prefs.get("patterns", []) or []
        patterns: List[Tuple[str, int]] = []
        if isinstance(patt_src, dict):
            # tolerate dict form as well
            for pat, pick in patt_src.items():
                try:
                    patterns.append((str(pat), int(pick)))
                except Exception:
                    continue
        else:
            # expect list of {"pattern": "...", "pick": 2}
            for item in patt_src:
                if not isinstance(item, dict):
                    continue
                pat = str(item.get("pattern", "")).strip()
                if not pat:
                    continue
                try:
                    pick = int(item.get("pick", 1))
                except Exception:
                    pick = 1
                patterns.append((pat, pick if pick >= 1 else 1))

        # --- defaults ---
        d = prefs.get("defaults", {}) or {}
        default_by_type = {
            "support": int(d.get("support", 1) or 1),
            "trainee": int(d.get("trainee", 1) or 1),
            "scenario": int(d.get("scenario", 1) or 1),
        }
        return UserPrefs(
            overrides=overrides, patterns=patterns, default_by_type=default_by_type, alias_overrides=alias_overrides
        )

    def pick_for(self, rec: EventRecord) -> int:
        """
        Resolve preference in this order:
        1) exact override (step-aware key "#s<step>")
        2) exact override (legacy key without step)
        3) first matching wildcard pattern (try step-aware then legacy)
        4) event.default_preference (from DB)
        5) type default
        """
        # 1) exact (step-aware)
        if rec.key_step in self.overrides:
            return int(self.overrides[rec.key_step])
        # 2) exact (legacy)
        if rec.key in self.overrides:
            return int(self.overrides[rec.key])
        # alias (trainee → general)
        if not self.alias_overrides and self.overrides:
            self.alias_overrides = _build_alias_overrides(self.overrides)
        if rec.key_step in self.alias_overrides:
            return int(self.alias_overrides[rec.key_step])
        if rec.key in self.alias_overrides:
            return int(self.alias_overrides[rec.key])
        if rec.type == "trainee" and normalize_text(rec.name) == "general":
            specific_pick = _match_specific_trainee_override(self.overrides, rec)
            if specific_pick is not None:
                return int(specific_pick)
        # 3) wildcard patterns
        for patt, pick in self.patterns:
            if fnmatch.fnmatch(rec.key_step, patt):
                return int(pick)
            if fnmatch.fnmatch(rec.key, patt):
                return int(pick)

        # 4) event default_preference
        if rec.default_preference is not None:
            return int(rec.default_preference)

        # 5) type default
        return int(self.default_by_type.get(rec.type, 1))


# -----------------------------
# Runtime: load catalog
# -----------------------------


@dataclass
class Catalog:
    records: List[EventRecord]

    @staticmethod
    def load(path: Path = CATALOG_JSON) -> "Catalog":
        if not path.exists():
            raise FileNotFoundError(
                f"Missing catalog {path}. Run build_catalog() first."
            )
        with path.open("r", encoding="utf-8") as f:
            rows = json.load(f)
        recs = [EventRecord(**row) for row in rows]
        return Catalog(records=recs)


# -----------------------------
# Retrieval + Reranking
# -----------------------------


@dataclass
class Query:
    # Minimal info you’ll have from OCR/UI
    ocr_title: str
    # Optional hints (help scoring if provided)
    type_hint: Optional[str] = None  # support|trainee|scenario
    name_hint: Optional[str] = None  # e.g., "Kitasan Black"
    rarity_hint: Optional[str] = None  # "SSR"/"SR"/"R"/"None"
    attribute_hint: Optional[str] = None  # "SPD"/"STA"/"PWR"/"GUTS"/"WIT"/"None"
    chain_step_hint: Optional[int] = None  # e.g., 1/2/3 for chain events
    portrait_path: Optional[str] = None  # optional: path to portrait/icon
    portrait_image: Optional[PILImage] = None  # optional: PIL image crop (in-memory)
    portrait_phash: Optional[int] = None  # optional: precomputed 64-bit pHash


@dataclass
class MatchResult:
    rec: EventRecord
    score: float
    text_sim: float
    img_sim: float
    hint_bonus: float


def score_candidate(
    q: Query, rec: EventRecord, portrait_phash: Optional[int]
) -> MatchResult:
    # 1) text similarity on titles (normalized)
    qt = normalize_text(q.ocr_title)
    if qt:
        ts_token = fuzz.token_set_ratio(qt, rec.title_norm) / 100.0
        ts_ratio = fuzz.ratio(qt, rec.title_norm) / 100.0
        ts_partial = fuzz.partial_ratio(qt, rec.title_norm) / 100.0
        text_sim = (
            0.5 * ts_token + 0.3 * ts_ratio + 0.2 * ts_partial
        )
        if qt == rec.title_norm:
            text_sim = 1.0
    else:
        text_sim = 0.0

    # 2) image similarity (pHash) if we have a portrait crop
    img_sim = (
        hamming_similarity64(portrait_phash, rec.phash64) if portrait_phash else 0.0
    )

    # 3) hint bonus (soft constraints, deck-agnostic)
    hint_bonus = 0.0
    if q.type_hint and q.type_hint == rec.type:
        hint_bonus += 0.04
    if q.name_hint and normalize_text(q.name_hint) == normalize_text(rec.name):
        hint_bonus += 0.08
    if q.rarity_hint and normalize_text(q.rarity_hint) == normalize_text(rec.rarity):
        hint_bonus += 0.12
    if q.attribute_hint and normalize_text(q.attribute_hint) == normalize_text(
        rec.attribute
    ):
        hint_bonus += 0.12
    if q.chain_step_hint is not None and (rec.chain_step or 1) == q.chain_step_hint:
        hint_bonus += 0.12
    # Weighted sum (tuneable, but conservative)
    # Text carries most of the weight; image breaks ties when portrait is present.
    score = 0.82 * text_sim + 0.11 * img_sim + hint_bonus

    return MatchResult(
        rec=rec, score=score, text_sim=text_sim, img_sim=img_sim, hint_bonus=hint_bonus
    )


def retrieve_best(
    catalog: Catalog,
    q: Query,
    top_k: int = 5,
    min_score: float = 0.75,
) -> List[MatchResult]:
    """
    Apply hint-driven *pre-filters* first (type → name → rarity). Each filter is
    only kept if it doesn't collapse the pool to empty; otherwise we gracefully
    fall back to the previous pool. This lets 'rarity=R' surface R variants when
    they exist for the same title, without breaking cases where they don't.
    After scoring, results are filtered by `min_score` (default 0.80) to drop
    spurious matches; callers can detect "no candidates" and fall back.
    """
    # Compute portrait pHash once (if provided)
    portrait_phash = None
    # priority: explicit pHash > PIL image > path
    if q.portrait_phash is not None:
        portrait_phash = q.portrait_phash
    elif q.portrait_image is not None:
        portrait_phash = safe_phash_from_image(q.portrait_image)
    elif q.portrait_path and os.path.exists(q.portrait_path):
        portrait_phash = safe_phash(Path(q.portrait_path))

    pool = list(catalog.records)
    # Keep a backup at each stage in case a filter would drop everything.
    if q.type_hint:
        subset = [r for r in pool if r.type == q.type_hint]
        if subset:
            pool = subset
    if q.name_hint:
        subset = [
            r for r in pool if normalize_text(r.name) == normalize_text(q.name_hint)
        ]
        if subset:
            pool = subset
    if q.rarity_hint:
        subset = [
            r for r in pool if normalize_text(r.rarity) == normalize_text(q.rarity_hint)
        ]
        if subset:
            pool = subset
    if q.attribute_hint:
        subset = [
            r
            for r in pool
            if normalize_text(r.attribute) == normalize_text(q.attribute_hint)
        ]
        if subset:
            pool = subset
    if q.chain_step_hint is not None:
        subset = [r for r in pool if (r.chain_step or 1) == q.chain_step_hint]
        if subset:
            pool = subset
    # If all filters emptied the pool (rare), revert to full catalog.
    if not pool:
        pool = list(catalog.records)

    results: List[MatchResult] = [
        score_candidate(q, rec, portrait_phash) for rec in pool
    ]
    results.sort(key=lambda r: r.score, reverse=True)
    # Filter low-confidence candidates
    if min_score is not None:
        results = [r for r in results if r.score >= float(min_score)]
    return results[:top_k]
