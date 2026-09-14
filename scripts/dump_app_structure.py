"""Dump the structural skeleton of app.py: banners, top-level classes/defs,
methods, decorators, with start-end line numbers.

Indentation-aware so we can anchor split boundaries precisely.
"""

import ast
import sys
from pathlib import Path

TARGET = Path(__file__).resolve().parents[1] / "app.py"


def main() -> None:
    """Test the main path."""
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    src = TARGET.read_text(encoding="utf-8")
    lines = src.splitlines()

    print(f"FILE: {TARGET}")
    print(f"TOTAL LINES: {len(lines)}")
    print("=" * 72)

    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            end = getattr(node, "end_lineno", node.lineno)
            decorators = [
                _deco_name(d) for d in getattr(node, "decorator_list", [])
            ]
            print(f"\nCLASS {node.name}  lines {node.lineno}..{end}")
            if decorators:
                print(f"  decorators: {', '.join(decorators)}")
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    mend = getattr(item, "end_lineno", item.lineno)
                    mdeco = [
                        _deco_name(d)
                        for d in getattr(item, "decorator_list", [])
                    ]
                    extra = f"  [deco: {', '.join(mdeco)}]" if mdeco else ""
                    print(f"  method {item.name}  {item.lineno}..{mend}{extra}")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = getattr(node, "end_lineno", node.lineno)
            deco = [_deco_name(d) for d in getattr(node, "decorator_list", [])]
            extra = f"  [deco: {', '.join(deco)}]" if deco else ""
            print(f"\nFUNC {node.name}  {node.lineno}..{end}{extra}")
        elif isinstance(node, ast.Assign):
            names = []
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.append(t.id)
                elif isinstance(t, ast.Tuple):
                    names.extend(e.id for e in t.elts if isinstance(e, ast.Name))
            if names and node.lineno <= 70:
                print(f"\nASSIGN @{node.lineno}: {', '.join(names)}")
        elif isinstance(node, ast.Import) or isinstance(node, ast.ImportFrom):
            print(f"import @{node.lineno}")

    print("\n" + "=" * 72)
    print("BANNER / SECTION COMMENT LINES (star-heavy or ===-style):")
    for i, ln in enumerate(lines, start=1):
        if ln.startswith("#") and ("---" in ln or "===" in ln or "|" in ln):
            print(f"  {i}: {ln.strip()}")


def _deco_name(d: ast.expr) -> str:
    """Test the  deco name path."""
    if isinstance(d, ast.Name):
        return d.id
    if isinstance(d, ast.Call):
        return _deco_name(d.func)
    if isinstance(d, ast.Attribute):
        return f"{_deco_name(d.value)}.{d.attr}"
    if isinstance(d, ast.Subscript):
        return f"{_deco_name(d.value)}[...]"
    return ast.dump(d)


if __name__ == "__main__":
    main()
