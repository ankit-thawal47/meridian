"""Pure code-analysis operations (analysis_* namespace).

Each ``op_analysis_*`` takes (ctx, args) and returns an MCP content dict, sharing
the ``ok``/``err`` envelope from core_ops. These are static-analysis helpers used
during the investigate phase: TODO mining, dead-code detection, complexity, import
graphing, size accounting, security/perf grep, and test-gap detection. They degrade
gracefully when optional tools (vulture/radon) are absent, falling back to stdlib.
"""

from __future__ import annotations

import ast
import re
import shutil
from collections import defaultdict
from typing import Any

from meridian.tools.context import ToolContext
from meridian.tools.core_ops import _run, _skip_path, err, ok
from meridian.tools.schemas import ComplexityItem, TodoItem

_TODO_RX = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b[:\s]?(.*)")
_SECRET_RXS = [
    re.compile(r"""password\s*=\s*["'][^"']+["']""", re.I),
    re.compile(r"""api[_-]?key\s*=\s*["'][^"']+["']""", re.I),
    re.compile(r"""secret\s*=\s*["'][^"']+["']""", re.I),
    re.compile(r"""token\s*=\s*["'][^"']+["']""", re.I),
    re.compile(r"\beval\("),
    re.compile(r"\bexec\("),
    re.compile(r"subprocess\.(?:call|run|Popen)\([^)]*shell\s*=\s*True"),
    re.compile(r"""["']\s*\+\s*\w+\s*\+\s*["'].*(?:SELECT|INSERT|UPDATE|DELETE)""", re.I),
]
_CODE_EXTS = {".py", ".ts", ".js"}


def _iter_files(ctx: ToolContext, exts: set[str] | None = None) -> list[Any]:
    out = []
    for path in ctx.workspace.rglob("*"):
        if not path.is_file() or _skip_path(path, ctx.workspace):
            continue
        if exts is not None and path.suffix not in exts:
            continue
        out.append(path)
    return out


async def op_analysis_todos(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    items: list[TodoItem] = []
    for path in _iter_files(ctx, _CODE_EXTS):
        try:
            for i, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
                m = _TODO_RX.search(line)
                if m:
                    items.append(TodoItem(
                        path=str(path.relative_to(ctx.workspace)), line=i,
                        text=m.group(2).strip()[:200] or line.strip()[:200],
                        kind=m.group(1)))
        except (OSError, UnicodeDecodeError):
            continue
    return ok(f"{len(items)} TODO/FIXME markers",
              {"todos": [t.model_dump() for t in items[:200]]})


async def op_analysis_dead_code(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    target = str(args.get("path") or ".").strip() or "."
    if shutil.which("vulture"):
        rc, out = await _run("vulture", target, cwd=str(ctx.workspace))
        issues = [line for line in out.splitlines() if ":" in line][:200]
        return ok(f"vulture: {len(issues)} issues", {"tool": "vulture", "issues": issues})
    if shutil.which("autoflake"):
        rc, out = await _run("autoflake", "--check", "-r", target, cwd=str(ctx.workspace))
        issues = [line for line in out.splitlines() if line.strip()][:200]
        return ok(f"autoflake: {len(issues)} issues", {"tool": "autoflake", "issues": issues})
    # Fallback: AST-based unused-import detection per file.
    issues = []
    for path in _iter_files(ctx, {".py"}):
        try:
            tree = ast.parse(path.read_text(errors="replace"))
        except SyntaxError:
            continue
        imported: dict[str, int] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported[(alias.asname or alias.name).split(".")[0]] = node.lineno
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name != "*":
                        imported[alias.asname or alias.name] = node.lineno
        used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        used |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        rel = str(path.relative_to(ctx.workspace))
        for name, line in imported.items():
            if name not in used:
                issues.append(f"{rel}:{line}: unused import '{name}'")
    return ok(f"ast-fallback: {len(issues)} unused imports",
              {"tool": "ast", "issues": issues[:200]})


async def op_analysis_complexity(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    target = str(args.get("path") or ".").strip() or "."
    if shutil.which("radon"):
        rc, out = await _run("radon", "cc", "-s", target, cwd=str(ctx.workspace))
        return ok("radon complexity",
                  {"tool": "radon", "output": out[:4000]})
    # Fallback: count branch keywords per function via AST.
    items: list[ComplexityItem] = []
    paths = _iter_files(ctx, {".py"})
    if target != "." :
        try:
            tp = ctx.safe_path(target)
            paths = [tp] if tp.is_file() else _iter_files(ctx, {".py"})
        except ValueError:
            pass
    for path in paths:
        try:
            tree = ast.parse(path.read_text(errors="replace"))
        except (SyntaxError, OSError):
            continue
        rel = str(path.relative_to(ctx.workspace))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                score = 1 + sum(
                    isinstance(n, ast.If | ast.For | ast.While | ast.BoolOp | ast.ExceptHandler)
                    for n in ast.walk(node)
                )
                items.append(ComplexityItem(name=f"{rel}::{node.name}",
                                            complexity=score, line=node.lineno))
    items.sort(key=lambda c: c.complexity, reverse=True)
    return ok(f"ast-fallback: {len(items)} functions scored",
              {"tool": "ast", "functions": [c.model_dump() for c in items[:50]]})


async def op_analysis_imports(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    try:
        p = ctx.safe_path(args["path"])
    except (ValueError, KeyError) as e:
        return err(str(e), deterministic=True)
    if not p.is_file():
        return err(f"not a file: {args.get('path')}", deterministic=True)
    try:
        tree = ast.parse(p.read_text(errors="replace"))
    except SyntaxError as e:
        return err(f"could not parse: {e}", deterministic=True)
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    uniq = sorted(set(modules))
    return ok(f"{len(uniq)} imported modules in {args['path']}", {"modules": uniq})


async def op_analysis_size(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    sizes: list[tuple[str, int]] = []
    by_ext: dict[str, int] = defaultdict(int)
    for path in _iter_files(ctx, _CODE_EXTS):
        try:
            n = sum(1 for _ in path.open("r", errors="replace"))
        except OSError:
            continue
        sizes.append((str(path.relative_to(ctx.workspace)), n))
        by_ext[path.suffix] += n
    sizes.sort(key=lambda x: x[1], reverse=True)
    return ok(f"{len(sizes)} files, {sum(by_ext.values())} lines",
              {"top_files": [{"path": p, "lines": n} for p, n in sizes[:20]],
               "totals_by_ext": dict(by_ext)})


async def op_analysis_security_grep(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    hits: list[dict[str, Any]] = []
    for path in _iter_files(ctx, _CODE_EXTS):
        try:
            for i, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
                for rx in _SECRET_RXS:
                    if rx.search(line):
                        hits.append({"path": str(path.relative_to(ctx.workspace)),
                                     "line": i, "snippet": line.strip()[:200],
                                     "pattern": rx.pattern[:40]})
                        break
        except (OSError, UnicodeDecodeError):
            continue
    return ok(f"{len(hits)} security pattern hits", {"hits": hits[:200]})


async def op_analysis_perf_patterns(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    hits: list[dict[str, Any]] = []
    query_rx = re.compile(r"\.(?:query|filter|get|all|execute)\(", re.I)
    list_rx = re.compile(r"\blist\(\s*\w+\.(?:objects|query)")
    for path in _iter_files(ctx, _CODE_EXTS):
        try:
            lines = path.read_text(errors="replace").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        rel = str(path.relative_to(ctx.workspace))
        in_loop_until = -1
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith(("for ", "while ")):
                in_loop_until = i + 30
            reason = None
            if query_rx.search(line) and i <= in_loop_until:
                reason = "query inside loop (possible N+1)"
            elif list_rx.search(line):
                reason = "unbounded list() on ORM queryset"
            if reason:
                hits.append({"path": rel, "line": i, "snippet": stripped[:200],
                             "reason": reason})
    return ok(f"{len(hits)} perf-risk patterns", {"hits": hits[:200]})


async def op_analysis_test_gaps(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    src_dir = ctx.workspace / "src"
    tests_dir = ctx.workspace / "tests"
    if not src_dir.is_dir():
        return ok("no src/ directory — nothing to check", {"untested": []})
    test_names = set()
    if tests_dir.is_dir():
        test_names = {p.name for p in tests_dir.rglob("test_*.py")}
    untested: list[str] = []
    for path in src_dir.rglob("*.py"):
        if path.name == "__init__.py" or _skip_path(path, ctx.workspace):
            continue
        expected = f"test_{path.stem}.py"
        if expected not in test_names:
            untested.append(str(path.relative_to(ctx.workspace)))
    return ok(f"{len(untested)} source files lack a test",
              {"untested": untested[:200]})
