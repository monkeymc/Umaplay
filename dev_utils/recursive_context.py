#!/usr/bin/env python3
"""
python dev_utils/recursive_context.py --target core/actions/lobby.py
 --repo-root . --depth 1 --output dev_utils/recursive_out_agent.md
"""
# ---------------------------------------------------------------------
# For a given Python target file, build a compact slice of the codebase:
#   1) Resolve imports (absolute + relative) to concrete LOCAL files.
#   2) Include only "first-order essentials": interfaces, models,
#      serializers, validators, base classes, feature flags, DTOs/schemas.
#      (Target file is always included.)
#   3) Cap traversal depth (e.g., N=2 or N=3). Beyond the cap, list far nodes
#      (and optionally inline their code with --include-far-code).
#   4) Detect third-party deps mentioned via imports (names + brief roles).
#   5) OUTPUT MARKDOWN that inlines the FULL REAL CODE for the included files
#      (not third-party). Large files are truncated with a clear notice.
#
# Terminal behavior:
#   - Prints STATS to STDERR (so stdout stays clean for the Markdown content).
#   - If --output is a file, writes Markdown there; stats still go to STDERR.
#
# Usage examples:
#   python recursive_context.py --target src/orders/views.py --depth 2 --output -
#   python recursive_context.py --target src/app/module/foo.py --include-far-code \
#       --max-bytes-per-file 400000 --exclude-tests --output progress_slice.md
#
# Exit code 0 on success; non-zero on obvious misconfiguration.
# ---------------------------------------------------------------------

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Iterable, List, Set, Tuple, Dict

import ast
from importlib import metadata

# ---------- Configuration knobs ----------

DEFAULT_REPO_ROOT = "."
DEFAULT_DEPTH = 2
DEFAULT_MAX_FILES = 300  # safety brake for runaway graphs
DEFAULT_MAX_ANCHORS_PER_FILE = 12  # metadata only (kept for anchors list)
DEFAULT_OUTPUT = "-"  # "-" = stdout
DEFAULT_MAX_BYTES_PER_FILE = 500_000  # truncate with a note if exceeded

# Heuristic keywords to classify "first-order essentials"
ESSENTIAL_KEYWORDS = (
    "interface",
    "interfaces",
    "model",
    "models",
    "serializer",
    "serializers",
    "validator",
    "validators",
    "base",
    "abstract",
    "feature_flag",
    "feature-flags",
    "featureflags",
    "feature",
    "flags",
    "schema",
    "schemas",
    "dto",
    "dtos",
    "core",
)

# File name patterns considered likely "essentials"
LIKELY_ESSENTIAL_FILENAMES = (
    "interfaces.py",
    "interface.py",
    "models.py",
    "serializers.py",
    "validators.py",
    "validator.py",
    "base.py",
    "abstract.py",
    "feature_flags.py",
    "flags.py",
    "schema.py",
    "schemas.py",
    "dto.py",
    "dtos.py",
    "__init__.py",  # packages may expose contracts
)

# Special constants to detect feature flags
FEATURE_FLAG_NAMES = ("FEATURE_FLAGS", "FLAGS", "FEATURES")

# Heuristic roles for popular third-party libs (extend as needed)
THIRDPARTY_ROLE_HINTS: Dict[str, str] = {
    "django": "Web framework / ORM",
    "djangorestframework": "Django REST APIs (serializers/views)",
    "fastapi": "Web framework (ASGI)",
    "starlette": "ASGI toolkit",
    "pydantic": "Data validation / settings",
    "sqlalchemy": "DB ORM",
    "alembic": "DB migrations",
    "requests": "HTTP client",
    "httpx": "HTTP client (async/sync)",
    "numpy": "Numerics",
    "pandas": "Dataframes",
    "pyyaml": "YAML parsing",
    "typer": "CLI",
    "click": "CLI",
    "loguru": "Logging",
    "structlog": "Structured logging",
    "attrs": "Data classes",
    "grpc": "gRPC",
    "protobuf": "Protobuf messages",
}

# ---------- Data structures ----------


@dataclass
class Anchor:
    kind: str  # "class" | "def" | "const"
    name: str
    start: int
    end: Optional[int]  # may be None if end not available


@dataclass
class FileSummary:
    path: Path
    role: str
    anchors: List[Anchor] = field(default_factory=list)
    depth: int = 0


@dataclass
class VisitNode:
    path: Path
    depth: int


@dataclass
class BuildStats:
    visited_count: int = 0
    included_count: int = 0
    far_nodes_count: int = 0
    total_bytes_inlined: int = 0
    files_truncated: int = 0
    third_party_unique: int = 0


# ---------- Repo helpers ----------


def detect_code_root(repo_root: Path) -> Path:
    """Prefer <repo>/src as code root; otherwise use repo root."""
    src = repo_root / "src"
    return src if src.exists() and src.is_dir() else repo_root


def discover_local_packages(code_root: Path) -> Set[str]:
    """Discover first-party top-level modules under code_root.

    This includes:
    - Directories that either contain an __init__.py OR have any .py files in their tree
      (to support namespace-like packages where __init__.py may be absent).
    - Top-level .py files (their stem becomes a local root name).
    """
    pkgs: Set[str] = set()
    if not code_root.exists():
        return pkgs

    for child in code_root.iterdir():
        if child.is_dir():
            if (child / "__init__.py").exists():
                pkgs.add(child.name)
                continue
            # Fallback: treat directory as local if it contains any .py file
            try:
                has_py = any(p.suffix == ".py" for p in child.rglob("*.py"))
            except Exception:
                has_py = False
            if has_py:
                pkgs.add(child.name)
        elif child.is_file() and child.suffix == ".py":
            pkgs.add(child.stem)
    return pkgs


# ---------- Import parsing ----------


def parse_imports(py_path: Path) -> Tuple[Set[str], List[Tuple[str, int, List[str]]]]:
    """
    Returns:
      - top_imports: names imported via `import x` (top-level segment)
      - from_imports: list of (module, level, names) for `from module import ...`
        where level>=1 means relative import ("from .models import X")
        and names is a list of imported names from the module
    """
    try:
        code = py_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return set(), []
    try:
        tree = ast.parse(code)
    except Exception:
        return set(), []

    top_imports: Set[str] = set()
    from_imports: List[Tuple[str, int, List[str]]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name:
                    # For direct imports like 'import x.y.z', track the full path
                    top_imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            lvl = getattr(node, "level", 0)
            # Collect all imported names from this import statement
            imported_names = [alias.name for alias in node.names if alias.name]
            from_imports.append((mod, lvl, imported_names))

            # For from-imports, track the full module path for better resolution
            if mod:
                top_imports.add(f"{'.' * lvl}{mod}" if lvl > 0 else mod)

    return top_imports, from_imports


# ---------- Resolve modules to files (LOCAL ONLY) ----------


def resolve_absolute_module_to_path(code_root: Path, module: str) -> Optional[Path]:
    """Resolve absolute module (e.g., 'app.foo.bar') to a file path under code_root."""
    if not module:
        return None
    rel = Path(*module.split("."))
    candidate = (code_root / rel).with_suffix(".py")
    if candidate.exists():
        return candidate
    pkg_init = code_root / rel / "__init__.py"
    if pkg_init.exists():
        return pkg_init
    return None


def resolve_relative_module_to_path(
    base_file: Path, level: int, module: str, code_root: Path
) -> Optional[Path]:
    """
    Resolve a relative import (e.g., from .models import X).
    `level` indicates how many package levels to go up from base_file's package.
    """
    base = base_file.parent
    for _ in range(max(0, level - 1)):
        base = base.parent
    if module:
        rel = Path(*module.split("."))
        py = (base / rel).with_suffix(".py")
        if py.exists():
            return py
        init = base / rel / "__init__.py"
        if init.exists():
            return init
    else:
        # "from . import something" refers to the package itself
        init = base / "__init__.py"
        if init.exists():
            return init
    return None


# ---------- Essentials heuristics ----------


def looks_like_essential_path(p: Path) -> bool:
    name = p.name.lower()
    if name in LIKELY_ESSENTIAL_FILENAMES:
        return True
    for kw in ESSENTIAL_KEYWORDS:
        if kw in name:
            return True
    if name == "__init__.py":
        return True
    return False


def classify_role_from_name(p: Path) -> str:
    n = p.name.lower()
    if "interface" in n:
        return "Interfaces / contracts"
    if "serializer" in n:
        return "Serializers"
    if "validator" in n:
        return "Validators"
    if "model" in n:
        return "Models / ORM"
    if "schema" in n or "dto" in n:
        return "Schemas / DTOs"
    if "feature" in n or "flags" in n:
        return "Feature flags"
    if "base" in n or "abstract" in n:
        return "Base / abstract classes"
    if n == "__init__.py":
        return "Package init / exports"
    return "Core module"


def extract_anchors(py_path: Path, max_anchors: int) -> List[Anchor]:
    """Top-level classes, functions, and feature flag constants with line ranges."""
    anchors: List[Anchor] = []
    try:
        src = py_path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(src)
    except Exception:
        return anchors

    for node in getattr(tree, "body", []):
        if isinstance(node, ast.ClassDef):
            anchors.append(
                Anchor(
                    kind="class",
                    name=node.name,
                    start=getattr(node, "lineno", 1),
                    end=getattr(node, "end_lineno", None),
                )
            )
        elif isinstance(node, ast.FunctionDef):
            anchors.append(
                Anchor(
                    kind="def",
                    name=node.name,
                    start=getattr(node, "lineno", 1),
                    end=getattr(node, "end_lineno", None),
                )
            )
        elif isinstance(node, ast.Assign):
            names = []
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.append(t.id)
            for nm in names:
                if nm in FEATURE_FLAG_NAMES:
                    anchors.append(
                        Anchor(
                            kind="const",
                            name=nm,
                            start=getattr(node, "lineno", 1),
                            end=getattr(node, "end_lineno", None),
                        )
                    )

    anchors.sort(key=lambda a: a.start)
    return anchors[:max_anchors]


# ---------- Third-party detection (names only) ----------


def third_party_deps_for_file(
    py_path: Path, code_root: Path, local_roots: Set[str]
) -> Set[str]:
    """Guess third-party deps imported by py_path.

    We consider ONLY the top-level package segment when deciding if something is
    third-party, so local modules like 'core.actions.x' are treated as first-party
    if 'core' is in local_roots.
    """
    tops, froms = parse_imports(py_path)
    deps: Set[str] = set()

    # Collect candidate top-level modules from direct imports
    for mod in tops:
        if not mod:
            continue
        # Skip relative imports represented with leading dots (from our tracking of from-imports)
        if mod.startswith("."):
            continue
        # If we can resolve the module under code_root, it's first-party
        if resolve_absolute_module_to_path(code_root, mod):
            continue
        top = mod.split(".", 1)[0]
        if top and (
            top in local_roots or resolve_absolute_module_to_path(code_root, top)
        ):
            continue
        if top:
            deps.add(top)

    # Also consider absolute from-imports (ignore relatives)
    for mod, lvl, _names in froms:
        if lvl != 0 or not mod:
            continue
        # If we can resolve the module under code_root, it's first-party
        if resolve_absolute_module_to_path(code_root, mod):
            continue
        top = mod.split(".", 1)[0]
        if top and (
            top in local_roots or resolve_absolute_module_to_path(code_root, top)
        ):
            continue
        if top:
            deps.add(top)

    return deps


def describe_dep(name: str) -> str:
    role = THIRDPARTY_ROLE_HINTS.get(name.lower(), "Third-party dependency")
    try:
        ver = metadata.version(name)
        return f"{name}=={ver} — {role}"
    except Exception:
        return f"{name} — {role}"


# ---------- Traversal ----------


def build_360_context(
    target: Path,
    code_root: Path,
    max_depth: int,
    max_files: int,
    max_anchors: int,
    exclude_tests: bool,
    exclude_migrations: bool,
) -> Tuple[List[FileSummary], List[Path], int, Set[Path]]:
    """
    Traverse imports from target up to max_depth.
    Return:
      - essentials: included file summaries
      - far_nodes: paths beyond depth (not inlined unless requested)
      - visited_count: number of distinct files visited
      - visited_set: actual visited set (for stats)
    """

    def _skippable(p: Path) -> bool:
        parts = set(x.lower() for x in p.parts)
        if exclude_tests and ("tests" in parts or "__tests__" in parts):
            return True
        if exclude_migrations and "migrations" in parts:
            return True
        # skip obvious non-source dirs
        if any(
            seg in parts
            for seg in {".venv", "venv", "__pycache__", ".mypy_cache", ".pytest_cache"}
        ):
            return True
        return False

    visited: Set[Path] = set()
    queue: List[VisitNode] = [VisitNode(path=target, depth=0)]

    essentials: List[FileSummary] = []
    far_nodes: List[Path] = []

    if target.exists() and not _skippable(target):
        essentials.append(summarize_file(target, 0, max_anchors))
        visited.add(target)

    while queue and len(visited) < max_files:
        node = queue.pop(0)
        if _skippable(node.path):
            continue

        tops, froms = parse_imports(node.path)
        candidates: List[Path] = []

        # Process direct imports (import x.y.z)
        for mod in tops:
            # Try to resolve the full module path first
            cand = resolve_absolute_module_to_path(code_root, mod)
            if cand and cand.exists() and cand not in visited and not _skippable(cand):
                if node.depth >= max_depth:
                    far_nodes.append(cand)
                else:
                    candidates.append(cand)
            else:
                # If full path resolution fails, try with just the top-level package
                top_level = mod.split(".")[0]
                if top_level != mod:  # Only try if it was a dotted import
                    cand = resolve_absolute_module_to_path(code_root, top_level)
                    if (
                        cand
                        and cand.exists()
                        and cand not in visited
                        and not _skippable(cand)
                    ):
                        if node.depth >= max_depth:
                            far_nodes.append(cand)
                        else:
                            candidates.append(cand)

        # Process from-imports (from x.y.z import ...)
        for mod, lvl, _ in froms:
            if node.depth >= max_depth:
                # For far nodes, just collect them without traversing
                cand = (
                    resolve_relative_module_to_path(node.path, lvl, mod, code_root)
                    if lvl > 0
                    else resolve_absolute_module_to_path(code_root, mod)
                )
                if (
                    cand
                    and cand.exists()
                    and cand not in visited
                    and not _skippable(cand)
                ):
                    far_nodes.append(cand)
                continue

            if lvl > 0:
                # Relative import (from .x.y import ...)
                cand = resolve_relative_module_to_path(node.path, lvl, mod, code_root)
                if (
                    cand
                    and cand not in candidates
                    and cand not in visited
                    and not _skippable(cand)
                ):
                    candidates.append(cand)
            elif mod:  # Absolute from-import (from x.y import ...)
                cand = resolve_absolute_module_to_path(code_root, mod)
                if (
                    cand
                    and cand not in candidates
                    and cand not in visited
                    and not _skippable(cand)
                ):
                    candidates.append(cand)

            # Also try to import the parent package if this is a deep import
            if "." in mod:
                parent_mod = mod.rsplit(".", 1)[0]
                cand = resolve_absolute_module_to_path(code_root, parent_mod)
                if (
                    cand
                    and cand not in candidates
                    and cand not in visited
                    and not _skippable(cand)
                ):
                    if node.depth >= max_depth:
                        far_nodes.append(cand)
                    else:
                        candidates.append(cand)

        for cand in candidates:
            if not cand.exists() or cand in visited or _skippable(cand):
                continue
            visited.add(cand)
            next_depth = node.depth + 1

            # Include ALL visited local modules within depth to ensure complete context
            essentials.append(summarize_file(cand, next_depth, max_anchors))

            queue.append(VisitNode(path=cand, depth=next_depth))

        if len(visited) >= max_files:
            break

    # Deduplicate far_nodes while preserving order
    seen_far: Set[Path] = set()
    uniq_far: List[Path] = []
    for p in far_nodes:
        if p not in seen_far:
            uniq_far.append(p)
            seen_far.add(p)

    return essentials, uniq_far, len(visited), visited


def summarize_file(p: Path, depth: int, max_anchors: int) -> FileSummary:
    role = classify_role_from_name(p)
    anchors = extract_anchors(p, max_anchors=max_anchors)
    return FileSummary(path=p, role=role, anchors=anchors, depth=depth)


# ---------- Rendering (FULL CODE) ----------


def _rel(base: Path, p: Path) -> str:
    try:
        return p.resolve().relative_to(base.resolve()).as_posix()
    except Exception:
        return p.as_posix()


def _normalize_newlines(text: str) -> str:
    """
    Normalize all line endings to LF to avoid double-spacing artifacts when rendering
    Markdown code fences or when tools treat CRLF as an extra blank line.
    """
    # Convert CRLF/CR to LF
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _read_with_cap(p: Path, max_bytes: int) -> Tuple[str, bool, int]:
    """Return (content, truncated?, bytes_included)."""
    data = p.read_bytes()
    if len(data) <= max_bytes:
        # Decode and normalize to LF to prevent extra blank lines in output
        decoded = data.decode("utf-8", errors="replace")
        return _normalize_newlines(decoded), False, len(data)
    # Truncated path: decode the head and normalize newlines as well
    head = data[:max_bytes].decode("utf-8", errors="replace")
    head = _normalize_newlines(head)
    note = f"\n\n# [Truncated at {max_bytes} bytes to fit context]\n"
    return head + note, True, max_bytes


def _lang_for(p: Path) -> str:
    return "python"


def render_markdown_full(
    target: Path,
    depth: int,
    code_root: Path,
    essentials: List[FileSummary],
    far_nodes: List[Path],
    third_party_index: Dict[Path, Set[str]],
    include_far_code: bool,
    max_bytes_per_file: int,
    stats: BuildStats,
) -> str:
    rel_t = _rel(code_root, target)
    lines: List[str] = []
    lines.append(
        f"I'm working on this project, here are some parts of it so you have some context\n\n## 360° Context — `{rel_t}` (depth {depth})\n"
    )

    # Target first (full code)
    tgt = next((e for e in essentials if e.path == target), None)
    if tgt:
        lines.append("### Target file (full code)")
        lines.extend(_render_file_block(code_root, tgt, max_bytes_per_file, stats))
        lines.append("")

    # Essentials by increasing depth (full code)
    essentials_sorted = sorted(
        (e for e in essentials if e.path != target),
        key=lambda e: (e.depth, e.path.as_posix()),
    )
    if essentials_sorted:
        lines.append("### Essentials (first-order only, full code)\n")
        current_d = -1
        for e in essentials_sorted:
            if e.depth != current_d:
                current_d = e.depth
                lines.append(f"- **Depth {current_d}**")
            lines.extend(_render_file_block(code_root, e, max_bytes_per_file, stats))
        lines.append("")

    # Far nodes
    if far_nodes:
        lines.append("### Far nodes (beyond depth)")
        if not include_far_code:
            lines.append(
                "_Summary only (enable `--include-far-code` to inline code)_:\n"
            )
            for p in far_nodes[:50]:
                lines.append(f"- `{_rel(code_root, p)}`")
            if len(far_nodes) > 50:
                lines.append(f"- … (+{len(far_nodes) - 50} more)")
            lines.append("")
        else:
            lines.append(
                "_Full code inlined for far nodes (use with care; can be large)_:\n"
            )
            for p in far_nodes:
                fsu = summarize_file(
                    p, depth + 1, max_anchors=DEFAULT_MAX_ANCHORS_PER_FILE
                )
                lines.extend(
                    _render_file_block(code_root, fsu, max_bytes_per_file, stats)
                )
            lines.append("")

    # # Third-party deps (compact)
    # all_deps: Set[str] = set()
    # for deps in third_party_index.values():
    #     all_deps |= deps
    # if all_deps:
    #     lines.append("### Third-party dependencies (compact)\n")
    #     for name in sorted(all_deps):
    #         lines.append(f"- {describe_dep(name)}")
    #     lines.append("")

    lines.append("# **YOUR TASK IS DEFINED BELOW**\n\n")

    return "".join(lines).rstrip() + "\n"


def _render_file_block(
    code_root: Path, fsu: FileSummary, max_bytes: int, stats: BuildStats
) -> List[str]:
    r = _rel(code_root, fsu.path)
    lines: List[str] = []
    lines.append(f"#### `{r}` — {fsu.role} (depth {fsu.depth})")
    if fsu.anchors:
        for a in fsu.anchors:
            rng = f"{a.start}-{a.end}" if a.end else f"{a.start}"
            lines.append(f"- anchor: {a.kind} `{a.name}` — lines {rng}")
    content, truncated, bytes_included = _read_with_cap(fsu.path, max_bytes)
    stats.total_bytes_inlined += bytes_included
    if truncated:
        stats.files_truncated += 1
    lines.append("")
    lines.append(f"```{_lang_for(fsu.path)}")
    lines.append(content)
    lines.append("```")
    lines.append("")
    return lines


# ---------- CLI ----------


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Build a 360° context around a target Python file (full code markdown + terminal stats)."
    )
    ap.add_argument(
        "--target",
        required=True,
        help="Path to the target Python file (e.g., src/app/foo.py)",
    )
    ap.add_argument(
        "--repo-root",
        default=DEFAULT_REPO_ROOT,
        help="Repository root (default: current directory)",
    )
    ap.add_argument(
        "--depth",
        type=int,
        default=DEFAULT_DEPTH,
        help=f"Max traversal depth (default: {DEFAULT_DEPTH})",
    )
    ap.add_argument(
        "--max-files",
        type=int,
        default=DEFAULT_MAX_FILES,
        help=f"Safety cap on files visited (default: {DEFAULT_MAX_FILES})",
    )
    ap.add_argument(
        "--max-anchors",
        type=int,
        default=DEFAULT_MAX_ANCHORS_PER_FILE,
        help=f"Max anchors per file (metadata only; default: {DEFAULT_MAX_ANCHORS_PER_FILE})",
    )
    ap.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help="Output path for Markdown (or '-' for stdout)",
    )
    ap.add_argument(
        "--include-far-code",
        action="store_true",
        help="Inline full code for far nodes beyond depth",
    )
    ap.add_argument(
        "--max-bytes-per-file",
        type=int,
        default=DEFAULT_MAX_BYTES_PER_FILE,
        help="Per-file cap before truncation (default: 500k)",
    )
    ap.add_argument(
        "--exclude-tests",
        action="store_true",
        help="Exclude tests/__tests__ from traversal",
    )
    ap.add_argument(
        "--exclude-migrations",
        action="store_true",
        help="Exclude Django-style migrations from traversal",
    )
    args = ap.parse_args()

    repo_root = Path(args.repo_root).resolve()
    code_root = detect_code_root(repo_root)

    target = (repo_root / args.target).resolve()
    if not target.exists() or not target.is_file():
        print(f"[error] Target not found: {target}", file=sys.stderr)
        return 2
    if target.suffix != ".py":
        print(f"[error] Target must be a .py file: {target}", file=sys.stderr)
        return 2

    essentials, far_nodes, visited_count, visited_set = build_360_context(
        target=target,
        code_root=code_root,
        max_depth=args.depth,
        max_files=args.max_files,
        max_anchors=args.max_anchors,
        exclude_tests=args.exclude_tests,
        exclude_migrations=args.exclude_migrations,
    )

    # Third-party deps (compact): gather per included file (including target)
    local_roots = discover_local_packages(code_root)
    third_index: Dict[Path, Set[str]] = {}
    for fs in essentials:
        third_index[fs.path] = third_party_deps_for_file(
            fs.path, code_root, local_roots
        )

    # Prepare stats (filled during render)
    stats = BuildStats(
        visited_count=visited_count,
        included_count=len(essentials),
        far_nodes_count=len(far_nodes),
        third_party_unique=len(
            set().union(*third_index.values()) if third_index else set()
        ),
    )

    md = render_markdown_full(
        target=target,
        depth=args.depth,
        code_root=code_root,
        essentials=essentials,
        far_nodes=far_nodes,
        third_party_index=third_index,
        include_far_code=args.include_far_code,
        max_bytes_per_file=args.max_bytes_per_file,
        stats=stats,
    )

    # ---- TERMINAL STATS (stderr) ----
    print("\n== recursive_context.py :: STATS ==", file=sys.stderr)
    print(f"Repo root:           {repo_root}", file=sys.stderr)
    print(f"Code root:           {code_root}", file=sys.stderr)
    print(f"Target:              {target}", file=sys.stderr)
    print(f"Depth cap:           {args.depth}", file=sys.stderr)
    print(f"Visited files:       {stats.visited_count}", file=sys.stderr)
    print(f"Included (markdown): {stats.included_count}", file=sys.stderr)
    print(f"Far nodes:           {stats.far_nodes_count}", file=sys.stderr)
    print(f"3rd-party unique:    {stats.third_party_unique}", file=sys.stderr)
    print(f"Bytes inlined:       {stats.total_bytes_inlined}", file=sys.stderr)
    print(f"Files truncated:     {stats.files_truncated}", file=sys.stderr)
    if args.exclude_tests:
        print("Note: tests excluded", file=sys.stderr)
    if args.exclude_migrations:
        print("Note: migrations excluded", file=sys.stderr)
    # ---- OUTPUT: Markdown to file or stdout (stdout only contains the Markdown) ----
    if args.output.strip() == "-" or not args.output.strip():
        sys.stdout.write(md)
    else:
        out_path = Path(args.output).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(md, encoding="utf-8")
        print(f"[ok] Wrote 360° context → {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
