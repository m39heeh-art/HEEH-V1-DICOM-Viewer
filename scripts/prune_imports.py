"""Prune unused imports from shared analysis modules.

The active UI is canonical in ``app.py``; compatibility exports are not
generated modules and are intentionally excluded from this maintenance pass.
"""

from __future__ import annotations

import argparse
import ast
import builtins
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MODULES = [
    ("core/tissue_classifier.py", "core.tissue_classifier"),
    ("core/volume_visualizer.py", "core.volume_visualizer"),
    ("core/image_quality_metrics.py", "core.image_quality_metrics"),
    ("core/base_analysis.py", "core.base_analysis"),
    ("core/system_config.py", "core.system_config"),
    ("core/quantitative_engine.py", "core.quantitative_engine"),
    ("core/structural_engine.py", "core.structural_engine"),
    ("core/loaders.py", "core.loaders"),
    ("utils/medical_ai_vision.py", "utils.medical_ai_vision"),
    ("engines/analysis_orchestrator.py", "engines.analysis_orchestrator"),
    ("engines/onnx_inference.py", "engines.onnx_inference"),
]

CONSTANTS_PATH = "core/constants.py"
CONSTANTS_MODULE = "core.constants"

FORCE_KEEP = {}
TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
BUILTINS = set(dir(builtins))


def decode(raw: bytes) -> str:
    """Decode raw bytes as UTF-8, falling back to cp1252."""
    return raw.decode("utf-8", errors="surrogateescape")


def encode(text: str) -> bytes:
    """Encode text back to UTF-8 bytes."""
    return text.encode("utf-8")


def is_docstring(stmt) -> bool:
    """Return whether the AST statement is a string literal."""
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(getattr(stmt, "value", None), ast.Constant)
        and isinstance(stmt.value.value, str)
    )


def target_names(targets) -> set[str]:
    """Return the names bound by an import statement."""
    names = set()
    for target in targets:
        if isinstance(target, ast.Name):
            names.add(target.id)
        else:
            for node in ast.walk(target):
                if isinstance(node, ast.Name):
                    names.add(node.id)
    return names


def bound_names(stmt) -> set[str]:
    """Return names defined at module or function scope."""
    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return {stmt.name}
    if isinstance(stmt, (ast.Import, ast.ImportFrom)):
        return {a.asname or a.name for a in stmt.names}
    if isinstance(stmt, ast.Assign):
        return target_names(stmt.targets)
    if isinstance(stmt, ast.AnnAssign):
        return target_names([stmt.target])
    if isinstance(stmt, ast.NamedExpr):
        return target_names([stmt.target])
    if isinstance(stmt, ast.ExceptHandler):
        return {stmt.name} if stmt.name else set()
    return set()


def module_defined(tree, start: int) -> set[str]:
    """Return the set of names defined in an AST module."""
    names = set()
    for stmt in tree.body[start:]:
        names |= bound_names(stmt)
    return names


def walk_usage(node, out: list[str]) -> None:
    """Return names referenced anywhere under the node."""
    if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        body = node.body or []
        if body and is_docstring(body[0]):
            body = body[1:]
        for stmt in body:
            walk_usage(stmt, out)
        for field, value in ast.iter_fields(node):
            if field == "body":
                continue
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, ast.AST):
                        walk_usage(item, out)
            elif isinstance(value, ast.AST):
                walk_usage(value, out)
        return
    if isinstance(node, ast.Name):
        out.append(node.id)
        return
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        out.extend(TOKEN_RE.findall(node.value))
        return
    for field, value in ast.iter_fields(node):
        if isinstance(value, list):
            for item in value:
                if isinstance(item, ast.AST):
                    walk_usage(item, out)
        elif isinstance(value, ast.AST):
            walk_usage(value, out)


def used_names(tree) -> set[str]:
    """Return names used within the module top-level block."""
    out = []
    walk_usage(tree, out)
    return set(out)


def header_end(tree) -> int:
    """Return the line index where the header block ends."""
    for i, node in enumerate(tree.body):
        if i == 0 and is_docstring(node):
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        return i
    return len(tree.body)


def stmt_lines(lines: list[str], node) -> list[str]:
    """Return the line-span (start, end) of an AST statement."""
    start = node.lineno - 1
    end = getattr(node, "end_lineno", node.lineno)
    return lines[start:end]


def format_alias(alias) -> str:
    """Format an import alias pair as name or name as alias."""
    if alias.asname:
        return f"{alias.name} as {alias.asname}"
    return alias.name


def render_from_import(node, keep: set[str]) -> str:
    """Render a from-import statement line."""
    parts = [format_alias(a) for a in node.names if (a.asname or a.name) in keep]
    module = getattr(node, "module", "") or ""
    level = "." * int(getattr(node, "level", 0))
    return f"from {level}{module} import {', '.join(parts)}"


def render_import(node, keep: set[str]) -> str:
    """Render a plain import statement line."""
    parts = [format_alias(a) for a in node.names if (a.asname or a.name) in keep]
    return f"import {', '.join(parts)}"


def plan_module(rel_path: str, dotted: str, defined_map: dict[str, set[str]]):
    """Compute the pruned import block for one module."""
    raw = (ROOT / rel_path).read_bytes()
    text = decode(raw)
    lines = text.splitlines()
    if not lines:
        return None
    tree = ast.parse(text)
    hend = header_end(tree)
    if hend >= len(tree.body):
        return None
    used = used_names(tree)
    defined = module_defined(tree, hend)
    needed = {n for n in used if n not in BUILTINS and n not in defined}

    emitted = set()
    keeps = []
    dropped = 0
    trimmed = 0

    for node in tree.body[:hend]:
        if is_docstring(node):
            keeps.append((node, None))
            continue
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            keeps.append((node, None))
            continue
        bound = [(a.asname or a.name) for a in node.names]
        keep_names = [b for b in bound if b in needed and b not in emitted]
        if keep_names:
            emitted.update(keep_names)
            single = node.lineno == getattr(node, "end_lineno", node.lineno)
            if single and isinstance(node, ast.ImportFrom):
                selected = set(keep_names)
                rendered = render_from_import(node, selected)
                if len([a for a in node.names if (a.asname or a.name) in selected]) < len(node.names):
                    trimmed += 1
                keeps.append((node, rendered))
            elif single:
                selected = set(keep_names)
                rendered = render_import(node, selected)
                if len(selected) < len(node.names):
                    trimmed += 1
                keeps.append((node, rendered))
            else:
                keeps.append((node, None))
            continue
        forced = FORCE_KEEP.get(rel_path, set())
        if any(b in forced for b in bound):
            emitted.update(b for b in bound if b in forced)
            keeps.append((node, None))
            continue
        dropped += 1

    missing = {n for n in needed if n not in emitted}
    groups = {}
    unresolved = []
    for name in sorted(missing):
        providers = []
        if name in defined_map.get(CONSTANTS_PATH, set()):
            providers.append(CONSTANTS_MODULE)
        for rel, mod in MODULES:
            if mod == dotted:
                continue
            if name in defined_map.get(rel, set()):
                providers.append(mod)
        if not providers or len(providers) > 1:
            unresolved.append(name)
            continue
        groups.setdefault(providers[0], []).append(name)

    add_lines = []
    for mod in sorted(groups, key=lambda m: (m == CONSTANTS_MODULE, m)):
        add_lines.append(f"from {mod} import {', '.join(sorted(groups[mod]))}")

    header_lines = []
    last_end = 0
    for node, rendered in keeps:
        chunk = [rendered] if rendered else stmt_lines(lines, node)
        header_lines.extend(chunk)
        last_end = max(last_end, getattr(node, "end_lineno", node.lineno) - 1)

    if add_lines:
        header_lines.append("")
        header_lines.extend(add_lines)

    inter = []
    for i in range(last_end + 1, tree.body[hend].lineno - 1):
        s = lines[i]
        if s.strip() == "" or s.strip().startswith("#"):
            inter.append(s)

    while header_lines and header_lines[-1].strip() == "":
        header_lines.pop()

    collapsed = []
    prev_blank = False
    for s in header_lines + inter:
        blank = s.strip() == ""
        if blank and prev_blank:
            continue
        collapsed.append(s)
        prev_blank = blank

    joined = collapsed
    while joined and joined[-1].strip() == "":
        joined.pop()
    joined.append("")
    joined.extend(lines[tree.body[hend].lineno - 1:])

    new_text = "\n".join(joined).rstrip("\n") + "\n"
    changed = new_text != text
    return {
        "rel": rel_path,
        "changed": changed,
        "text": text,
        "new_text": new_text,
        "kept": len([1 for node, _r in keeps if not is_docstring(node)]),
        "dropped": dropped,
        "trimmed": trimmed,
        "additions": add_lines,
        "unresolved": unresolved,
    }


def main() -> int:
    """Run the import-pruning pass over the repo modules.

    Resolve every dotted import back to a module that actually defines the
    symbol, then (with --apply) rewrite the import blocks accordingly.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write changes; default is a dry run")
    parser.add_argument("--module", default=None, help="only prune this module (path or dotted name)")
    args = parser.parse_args()

    defined_map = {}
    for rel, _dotted in MODULES:
        tree = ast.parse(decode((ROOT / rel).read_bytes()))
        defined_map[rel] = module_defined(tree, 0)
    tree = ast.parse(decode((ROOT / CONSTANTS_PATH).read_bytes()))
    defined_map[CONSTANTS_PATH] = module_defined(tree, 0)

    changed_total = 0
    unresolved_total = []
    for rel, dotted in MODULES:
        if args.module and args.module not in (rel, dotted):
            continue
        result = plan_module(rel, dotted, defined_map)
        if result is None:
            print(f"SKIP  {rel}  (no content statements)")
            continue
        tag = "EDIT" if result["changed"] else "OK  "
        print(f"{tag}  {rel}")
        print(f"     kept={result['kept']} dropped={result['dropped']} trimmed={result['trimmed']}")
        for addition in result["additions"]:
            print(f"  + {addition}")
        for name in result["unresolved"]:
            print(f"  ? unresolved name: {name}")
            unresolved_total.append((rel, name))
        if result["changed"]:
            changed_total += 1
            if args.apply:
                (ROOT / rel).write_bytes(encode(result["new_text"]))

    print(f"\n{dict(total_modules=len(MODULES), processed=changed_total + sum(1 for rel, _d in MODULES if args.module in (rel, _d) or not args.module), changed=changed_total)}")
    if unresolved_total:
        print("UNRESOLVED (manual review needed):")
        for rel, name in unresolved_total:
            print(f"  {rel}: {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
