#!/usr/bin/env python3
# python dev_utils/recursive_context_ts.py — TypeScript/React 360° context builder (v2: UI + direct imports)
# ---------------------------------------------------------------------
# Adds:
#  - --include-direct-imports (default ON): inline ALL depth-1 local imports.
#  - --include-ui (default ON) + --essential-dirs: include components/pages/... as essentials.
# Other behavior retained: full real code in Markdown; terminal stats on stderr.
# ---------------------------------------------------------------------

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

DEFAULT_REPO_ROOT = "."
DEFAULT_DEPTH = 2
DEFAULT_MAX_FILES = 400
DEFAULT_MAX_ANCHORS = 20
DEFAULT_OUTPUT = "-"
DEFAULT_MAX_BYTES_PER_FILE = 500_000

TS_EXTS = (".ts", ".tsx", ".js", ".jsx", ".d.ts")
STYLE_EXTS = {".css", ".scss", ".sass", ".less"}
ASSET_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico", ".ttf", ".woff", ".woff2"}

ESSENTIAL_KEYWORDS = (
    "interface", "interfaces",
    "type", "types",
    "model", "models",
    "schema", "schemas",
    "validator", "validators",
    "base", "abstract",
    "feature", "flags",
)
ESSENTIAL_FILENAMES = {
    "interfaces.ts", "interfaces.tsx",
    "interface.ts",
    "types.ts", "types.tsx",
    "models.ts", "models.tsx",
    "schema.ts", "schemas.ts",
    "validator.ts", "validators.ts",
    "base.ts", "abstract.ts",
    "feature_flags.ts", "flags.ts",
    "index.d.ts",
}

# Default UI-ish directories to treat as essentials (configurable via CLI)
DEFAULT_ESSENTIAL_DIRS = {"components", "pages", "routes", "context", "hooks", "widgets", "ui", "layouts"}

ROLE_HINTS: Dict[str, str] = {
    "react": "UI library",
    "react-dom": "DOM renderer",
    "react-router-dom": "Routing",
    "axios": "HTTP client",
    "zustand": "State management",
    "jotai": "State management",
    "redux": "State management",
    "@reduxjs/toolkit": "Redux utilities",
    "@tanstack/react-query": "Data fetching/cache",
    "@testing-library/react": "React testing utilities",
    "vitest": "Test runner",
    "jest": "Test runner",
    "zod": "Validation/schema",
    "yup": "Validation/schema",
    "clsx": "Class names utility",
    "lodash": "Utility library",
    "dayjs": "Date utils",
    "date-fns": "Date utils",
    "react-hook-form": "Form handling",
    "vite": "Dev server/bundler",
}

FEATURE_FLAG_NAME_RE = re.compile(r"(?:FEATURE|FLAGS|FEATURE_FLAGS|featureFlags)")

@dataclass
class Anchor:
    kind: str
    name: str
    start: int
    end: Optional[int]

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
    third_party_unique: int = 0
    total_bytes_inlined: int = 0
    files_truncated: int = 0

def detect_code_root(repo_root: Path) -> Path:
    src = repo_root / "src"
    return src if src.exists() and src.is_dir() else repo_root

def read_tsconfig(repo_root: Path) -> Tuple[Optional[Path], Dict[str, List[str]], Optional[Path]]:
    base_url: Optional[Path] = None
    paths: Dict[str, List[str]] = {}
    tsconfig = repo_root / "tsconfig.json"
    if tsconfig.exists():
        try:
            cfg = json.loads(tsconfig.read_text(encoding="utf-8"))
            co = (cfg.get("compilerOptions") or {})
            bu = co.get("baseUrl")
            if bu:
                base_url = (repo_root / bu).resolve()
            raw_paths = co.get("paths") or {}
            for k, v in raw_paths.items():
                if isinstance(v, list):
                    paths[k] = v
                elif isinstance(v, str):
                    paths[k] = [v]
        except Exception:
            pass
    at_alias_root = (repo_root / "src").resolve() if (repo_root / "src").exists() else None
    return base_url, paths, at_alias_root

def read_package_json(repo_root: Path) -> Dict[str, str]:
    pj = repo_root / "package.json"
    if pj.exists():
        try:
            data = json.loads(pj.read_text(encoding="utf-8"))
            deps = {}
            for sect in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
                deps.update(data.get(sect) or {})
            return {str(k): str(v) for k, v in deps.items()}
        except Exception:
            return {}
    return {}

IMPORT_SPEC_RE = re.compile(
    r"""(?P<kind>\bimport\b|\bexport\b)\s+[^'";]*?\bfrom\b\s*['"](?P<spec>[^'"]+)['"]\s*;?|
        (?P<side>\bimport\b)\s*['"](?P<spec2>[^'"]+)['"]\s*;?
    """,
    re.VERBOSE,
)

def strip_ts_comments(text: str) -> str:
    text = re.sub(r"//.*?$", "", text, flags=re.MULTILINE)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return text

def parse_ts_imports(ts_path: Path) -> Tuple[List[str], List[str]]:
    try:
        src = ts_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return [], []
    code = strip_ts_comments(src)
    local_specs: List[str] = []
    third_specs: List[str] = []
    for m in IMPORT_SPEC_RE.finditer(code):
        spec = m.group("spec") or m.group("spec2")
        if not spec:
            continue
        if spec.startswith("./") or spec.startswith("../") or spec.startswith("@/") or spec.startswith("/"):
            local_specs.append(spec)
        else:
            third_specs.append(spec)
    return local_specs, third_specs

def resolve_with_exts(candidate: Path) -> Optional[Path]:
    if candidate.suffix in TS_EXTS and candidate.exists():
        return candidate
    for ext in TS_EXTS:
        f = candidate.with_suffix(ext)
        if f.exists():
            return f
    if candidate.exists() and candidate.is_dir():
        for ext in TS_EXTS:
            idx = candidate / f"index{ext}"
            if idx.exists():
                return idx
    return None

def apply_ts_paths(spec: str, base_url: Optional[Path], paths: Dict[str, List[str]]) -> List[Path]:
    out: List[Path] = []
    if not paths or not base_url:
        return out
    for pattern, targets in paths.items():
        if "*" in pattern:
            prefix, suffix = pattern.split("*", 1)
            if spec.startswith(prefix) and spec.endswith(suffix):
                middle = spec[len(prefix) : len(spec) - len(suffix)]
                for t in targets:
                    out.append((base_url / t.replace("*", middle)).resolve())
        else:
            if spec == pattern:
                for t in targets:
                    out.append((base_url / t).resolve())
    return out

def is_under(path_obj: Path, root: Path) -> bool:
    try:
        path_obj.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False

def resolve_import(from_file: Path, spec: str, code_root: Path,
                   base_url: Optional[Path], paths: Dict[str, List[str]],
                   at_alias_root: Optional[Path]) -> Optional[Path]:
    if spec.startswith("./") or spec.startswith("../"):
        base = (from_file.parent / spec).resolve()
        hit = resolve_with_exts(base)
        return hit if hit and is_under(hit, code_root) else None
    if at_alias_root and (spec == "@" or spec.startswith("@/")):
        tail = "" if spec == "@" else spec[2:]
        base = (at_alias_root / tail).resolve()
        hit = resolve_with_exts(base)
        if hit and is_under(hit, code_root):
            return hit
    if base_url:
        base = (base_url / spec).resolve()
        hit = resolve_with_exts(base)
        if hit and is_under(hit, code_root):
            return hit
    for cand in apply_ts_paths(spec, base_url, paths):
        hit = resolve_with_exts(cand)
        if hit and is_under(hit, code_root):
            return hit
    base = (code_root / spec).resolve()
    hit = resolve_with_exts(base)
    return hit if hit and is_under(hit, code_root) else None

def looks_like_essential_path(p: Path, include_services: bool, include_ui: bool,
                              essential_dirs: Set[str]) -> bool:
    base = p.name.lower()
    if base in ESSENTIAL_FILENAMES:
        return True
    stem = base.rsplit(".", 1)[0] if "." in base else base
    if any(kw in stem for kw in ESSENTIAL_KEYWORDS):
        return True
    dirs = {seg.lower() for seg in p.parts}
    if include_services and "services" in dirs:
        return True
    if include_ui and (dirs & essential_dirs):
        return True
    return False

def classify_role_from_name(p: Path, include_services: bool, include_ui: bool,
                            essential_dirs: Set[str]) -> str:
    base = p.name.lower()
    stem = base.rsplit(".", 1)[0] if "." in base else base
    dirs = {seg.lower() for seg in p.parts}
    if base in ESSENTIAL_FILENAMES: return "Essential module"
    if "interface" in stem or "types" in stem: return "Interfaces / Types"
    if "model" in stem: return "Models"
    if "schema" in stem: return "Schemas"
    if "validator" in stem: return "Validators"
    if "base" in stem or "abstract" in stem: return "Base / Abstract"
    if "feature" in stem or "flag" in stem: return "Feature flags"
    if include_services and "services" in dirs: return "Service (API contracts)"
    if include_ui and (dirs & essential_dirs): return "UI component/module"
    return "Core module"

ANCHOR_PATTERNS = [
    (r"^\s*export\s+interface\s+([A-Za-z0-9_]+)", "interface"),
    (r"^\s*export\s+type\s+([A-Za-z0-9_]+)\s*=", "type"),
    (r"^\s*export\s+class\s+([A-Za-z0-9_]+)", "class"),
    (r"^\s*export\s+function\s+([A-Za-z0-9_]+)\s*\(", "function"),
    (r"^\s*export\s+enum\s+([A-Za-z0-9_]+)", "enum"),
    (r"^\s*export\s+const\s+([A-Za-z0-9_]+)\s*=", "const"),
    (r"^\s*export\s+let\s+([A-Za-z0-9_]+)\s*=", "const"),
    (r"^\s*export\s+var\s+([A-Za-z0-9_]+)\s*=", "const"),
]

def extract_ts_anchors(ts_path: Path, max_anchors: int) -> List[Anchor]:
    try:
        src = ts_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []
    code = strip_ts_comments(src)
    lines = code.splitlines()
    starts: List[Tuple[int, str, str]] = []
    for idx, line in enumerate(lines, start=1):
        for pat, kind in ANCHOR_PATTERNS:
            m = re.match(pat, line)
            if m:
                starts.append((idx, kind, m.group(1)))
                break
        if "const " in line and FEATURE_FLAG_NAME_RE.search(line):
            m2 = re.search(r"const\s+([A-Za-z0-9_]+)\s*=", line)
            if m2:
                starts.append((idx, "const", m2.group(1)))
    anchors: List[Anchor] = []
    for i, (start_line, kind, name) in enumerate(starts):
        end_line = None
        if i + 1 < len(starts):
            end_line = max(start_line, starts[i + 1][0] - 1)
        anchors.append(Anchor(kind=kind, name=name, start=start_line, end=end_line))
    anchors.sort(key=lambda a: a.start)
    return anchors[:max_anchors]

def third_party_for_file(ts_path: Path) -> List[str]:
    _, third_specs = parse_ts_imports(ts_path)
    pkgs: List[str] = []
    for spec in third_specs:
        if spec.startswith("@"):
            parts = spec.split("/")
            pkgs.append("/".join(parts[:2]) if len(parts) >= 2 else spec)
        else:
            pkgs.append(spec.split("/", 1)[0])
    return pkgs

def is_skippable(p: Path, include_styles: bool, include_tests: bool) -> bool:
    parts_lower = [seg.lower() for seg in p.parts]
    if not include_tests and any(seg in ("__tests__", "tests") for seg in parts_lower):
        return True
    if any(seg in (".git", "node_modules", "coverage", ".next", "dist", "build") for seg in parts_lower):
        return True
    ext = p.suffix.lower()
    if (ext in STYLE_EXTS and not include_styles) or ext in ASSET_EXTS:
        return True
    return False

def build_360(
    target: Path,
    code_root: Path,
    depth_cap: int,
    max_files: int,
    max_anchors: int,
    include_services: bool,
    include_ui: bool,
    essential_dirs: Set[str],
    include_tests: bool,
    include_styles: bool,
    include_direct_imports: bool,
    base_url: Optional[Path],
    paths: Dict[str, List[str]],
    at_alias_root: Optional[Path],
) -> Tuple[List[FileSummary], List[Path], int, Set[Path]]:
    visited: Set[Path] = set()
    queue: List[VisitNode] = [VisitNode(path=target, depth=0)]
    essentials: List[FileSummary] = []
    far_nodes: List[Path] = []

    def include_summary_for(p: Path, d: int):
        essentials.append(
            FileSummary(
                path=p,
                role=classify_role_from_name(p, include_services, include_ui, essential_dirs),
                anchors=extract_ts_anchors(p, max_anchors),
                depth=d,
            )
        )

    if target.exists() and not is_skippable(target, include_styles, include_tests):
        include_summary_for(target, 0)
        visited.add(target)

    while queue and len(visited) < max_files:
        node = queue.pop(0)
        local_specs, _ = parse_ts_imports(node.path)

        next_files: List[Path] = []
        for spec in local_specs:
            resolved = resolve_import(node.path, spec, code_root, base_url, paths, at_alias_root)
            if resolved and is_under(resolved, code_root) and not is_skippable(resolved, include_styles, include_tests):
                next_files.append(resolved)

        if node.depth >= depth_cap:
            for nf in next_files:
                if nf not in visited:
                    far_nodes.append(nf)
            continue

        for nf in next_files:
            if nf in visited:
                continue
            visited.add(nf)
            next_depth = node.depth + 1

            # NEW: Always include direct (depth-1) imports if flag is on.
            if next_depth == 1 and include_direct_imports:
                include_summary_for(nf, next_depth)
            # Also include if it matches "essentials" heuristics/dirs.
            elif looks_like_essential_path(nf, include_services, include_ui, essential_dirs):
                include_summary_for(nf, next_depth)

            queue.append(VisitNode(path=nf, depth=next_depth))

        if len(visited) >= max_files:
            break

    # Dedup far nodes
    seen: Set[Path] = set()
    uniq_far: List[Path] = []
    for p in far_nodes:
        if p not in seen:
            uniq_far.append(p)
            seen.add(p)

    return essentials, uniq_far, len(visited), visited

def rel(base: Path, p: Path) -> str:
    try:
        return p.resolve().relative_to(base.resolve()).as_posix()
    except Exception:
        return p.as_posix()

def lang_for(p: Path) -> str:
    ext = p.suffix.lower()
    if ext == ".tsx": return "tsx"
    if ext in (".ts", ".d.ts"): return "ts"
    if ext == ".jsx": return "jsx"
    if ext == ".js": return "js"
    if ext in STYLE_EXTS: return ext[1:]
    return ""

def read_with_cap(p: Path, max_bytes: int) -> Tuple[str, bool, int]:
    data = p.read_bytes()
    if len(data) <= max_bytes:
        return data.decode("utf-8", errors="replace"), False, len(data)
    head = data[:max_bytes].decode("utf-8", errors="replace")
    note = f"\n\n/* [Truncated at {max_bytes} bytes to fit context] */\n"
    return head + note, True, max_bytes

def render_file_block(code_root: Path, fsu: FileSummary, max_bytes: int, stats: BuildStats) -> List[str]:
    r = rel(code_root, fsu.path)
    out: List[str] = []
    out.append(f"#### `{r}` — {fsu.role} (depth {fsu.depth})")
    if fsu.anchors:
        for a in fsu.anchors:
            rng = f"{a.start}-{a.end}" if a.end else f"{a.start}"
            out.append(f"- anchor: {a.kind} `{a.name}` — lines {rng}")
    content, truncated, bytes_included = read_with_cap(fsu.path, max_bytes)
    stats.total_bytes_inlined += bytes_included
    if truncated:
        stats.files_truncated += 1
    out.append("")
    lang = lang_for(fsu.path)
    fence = "```" + (lang if lang else "")
    out.append(fence)
    out.append(content)
    out.append("```")
    out.append("")
    return out

def third_party_for_file(ts_path: Path) -> List[str]:
    _, third_specs = parse_ts_imports(ts_path)
    pkgs: List[str] = []
    for spec in third_specs:
        if spec.startswith("@"):
            parts = spec.split("/")
            pkgs.append("/".join(parts[:2]) if len(parts) >= 2 else spec)
        else:
            pkgs.append(spec.split("/", 1)[0])
    return pkgs

def render_markdown_full(
    target: Path,
    code_root: Path,
    depth_cap: int,
    essentials: List[FileSummary],
    far_nodes: List[Path],
    include_far_code: bool,
    max_bytes_per_file: int,
    all_third_party: Set[str],
    pkg_versions: Dict[str, str],
    stats: BuildStats,
) -> str:
    lines: List[str] = []
    lines.append(f"I'm working on this project, here are some parts of it so you have some context\n\n")
    lines.append(f"## 360° Context — `{rel(code_root, target)}` (depth {depth_cap})\n")

    tgt = next((e for e in essentials if e.path == target), None)
    if tgt:
        lines.append("### Target file (full code)")
        lines.extend(render_file_block(code_root, tgt, max_bytes_per_file, stats))
        lines.append("")

    rest = sorted(
        (e for e in essentials if e.path != target),
        key=lambda e: (e.depth, e.path.as_posix()),
    )
    if rest:
        lines.append("### Essentials & Direct Imports (full code)\n")
        current = -1
        for e in rest:
            if e.depth != current:
                current = e.depth
                lines.append(f"- **Depth {current}**")
            lines.extend(render_file_block(code_root, e, max_bytes_per_file, stats))
        lines.append("")

    if far_nodes:
        lines.append("### Far nodes (beyond depth)")
        if not include_far_code:
            lines.append("_Summary only (enable `--include-far-code` to inline code)_:\n")
            for p in far_nodes[:50]:
                lines.append(f"- `{rel(code_root, p)}`")
            if len(far_nodes) > 50:
                lines.append(f"- … (+{len(far_nodes) - 50} more)")
            lines.append("")
        else:
            lines.append("_Full code inlined for far nodes (can be large)_:\n")
            for p in far_nodes:
                fsu = FileSummary(path=p, role="Beyond depth", anchors=extract_ts_anchors(p, DEFAULT_MAX_ANCHORS), depth=depth_cap+1)
                lines.extend(render_file_block(code_root, fsu, max_bytes_per_file, stats))
            lines.append("")

    # if all_third_party:
    #     lines.append("### Third-party dependencies (compact)\n")
    #     for name in sorted(all_third_party):
    #         version = pkg_versions.get(name, "unknown")
    #         role = ROLE_HINTS.get(name, "3rd-party dependency")
    #         lines.append(f"- {name}@{version} — {role}")
    #     lines.append("")
    lines.append("# **YOUR TASK IS DEFINED BELOW**\n\n")

    return "\n".join(lines).rstrip() + "\n"

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Build a 360° TypeScript/React context (full code markdown + terminal stats)."
    )
    ap.add_argument("--target", required=True, help="Path to target TS/TSX/JS/JSX file")
    ap.add_argument("--repo-root", default=DEFAULT_REPO_ROOT, help="Repository root (default: .)")
    ap.add_argument("--depth", type=int, default=DEFAULT_DEPTH, help=f"Max traversal depth (default: {DEFAULT_DEPTH})")
    ap.add_argument("--max-files", type=int, default=DEFAULT_MAX_FILES, help=f"Safety cap on files visited (default: {DEFAULT_MAX_FILES})")
    ap.add_argument("--max-anchors", type=int, default=DEFAULT_MAX_ANCHORS, help=f"Max anchors per file (metadata only; default: {DEFAULT_MAX_ANCHORS})")
    ap.add_argument("--output", default=DEFAULT_OUTPUT, help="Output Markdown path or '-' for stdout")
    ap.add_argument("--include-services", action="store_true", default=True, help="Treat services/* as essentials (default: true)")
    ap.add_argument("--no-include-services", dest="include_services", action="store_false")
    ap.add_argument("--include-ui", action="store_true", default=True, help="Treat UI dirs as essentials (default: true)")
    ap.add_argument("--no-include-ui", dest="include_ui", action="store_false")
    ap.add_argument("--essential-dirs", type=str, default=",".join(sorted(DEFAULT_ESSENTIAL_DIRS)),
                    help="Comma-separated dir names treated as essentials when --include-ui (default: components,pages,routes,context,hooks,layouts,widgets,ui)")
    ap.add_argument("--include-direct-imports", action="store_true", default=True,
                    help="Inline ALL depth-1 local imports (default: true)")
    ap.add_argument("--no-include-direct-imports", dest="include_direct_imports", action="store_false")
    ap.add_argument("--include-far-code", action="store_true", help="Inline full code for far nodes beyond depth")
    ap.add_argument("--max-bytes-per-file", type=int, default=DEFAULT_MAX_BYTES_PER_FILE, help="Per-file size cap before truncation (default: 500k)")
    ap.add_argument("--include-tests", action="store_true", default=True, help="Include __tests__/tests (default: true)")
    ap.add_argument("--no-include-tests", dest="include_tests", action="store_false")
    ap.add_argument("--include-styles", action="store_true", default=False, help="Include imported CSS/SCSS (default: false)")
    args = ap.parse_args()

    repo_root = Path(args.repo_root).resolve()
    code_root = detect_code_root(repo_root)
    target = (repo_root / args.target).resolve()

    if not target.exists() or not target.is_file():
        print(f"[error] Target not found: {target}", file=sys.stderr)
        return 2
    if target.suffix.lower() not in TS_EXTS:
        print(f"[error] Target must be a TS/TSX/JS/JSX file: {target}", file=sys.stderr)
        return 2

    base_url, paths, at_alias_root = read_tsconfig(repo_root)
    pkg_versions = read_package_json(repo_root)

    essential_dirs = {seg.strip().lower() for seg in (args.essential_dirs or "").split(",") if seg.strip()}

    essentials, far_nodes, visited_count, visited_set = build_360(
        target=target,
        code_root=code_root,
        depth_cap=args.depth,
        max_files=args.max_files,
        max_anchors=args.max_anchors,
        include_services=args.include_services,
        include_ui=args.include_ui,
        essential_dirs=essential_dirs or DEFAULT_ESSENTIAL_DIRS,
        include_tests=args.include_tests,
        include_styles=args.include_styles,
        include_direct_imports=args.include_direct_imports,
        base_url=base_url,
        paths=paths,
        at_alias_root=at_alias_root,
    )

    third: Set[str] = set()
    for fsu in essentials:
        for name in third_party_for_file(fsu.path):
            third.add(name)

    stats = BuildStats(
        visited_count=visited_count,
        included_count=len(essentials),
        far_nodes_count=len(far_nodes),
        third_party_unique=len(third),
    )

    md = render_markdown_full(
        target=target,
        code_root=code_root,
        depth_cap=args.depth,
        essentials=essentials,
        far_nodes=far_nodes,
        include_far_code=args.include_far_code,
        max_bytes_per_file=args.max_bytes_per_file,
        all_third_party=third,
        pkg_versions=pkg_versions,
        stats=stats,
    )

    print("\n== recursive_context_ts.py :: STATS ==", file=sys.stderr)
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
    if not args.include_tests:
        print("Note: tests excluded", file=sys.stderr)
    if not args.include_styles:
        print("Note: styles excluded", file=sys.stderr)
    if not args.include_direct_imports:
        print("Note: direct imports NOT force-included", file=sys.stderr)
    if not args.include_ui:
        print("Note: UI dirs NOT treated as essentials", file=sys.stderr)
    if base_url:
        print(f"tsconfig baseUrl:    {base_url}", file=sys.stderr)
    if paths:
        print(f"tsconfig paths:      {len(paths)} patterns", file=sys.stderr)
    if at_alias_root:
        print(f"@/ alias root:       {at_alias_root}", file=sys.stderr)

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
