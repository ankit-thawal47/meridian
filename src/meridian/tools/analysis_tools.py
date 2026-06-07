"""SDK @tool wrappers for the analysis_* namespace (static code analysis).

Thin closures over the pure ``op_analysis_*`` functions in analysis_ops. Each
description states what it does, when to use it, and which sibling to use instead
so selection stays unambiguous as the registry grows past the retrieval threshold.
"""

from __future__ import annotations

from typing import Any

from claude_agent_sdk import tool

from meridian.tools import analysis_ops
from meridian.tools.context import ToolContext

ANALYSIS_TOOL_NAMES = [
    "analysis_todos",
    "analysis_dead_code",
    "analysis_complexity",
    "analysis_imports",
    "analysis_size",
    "analysis_security_grep",
    "analysis_perf_patterns",
    "analysis_test_gaps",
]


def build_analysis_tools(ctx: ToolContext) -> list[Any]:
    @tool(
        "analysis_todos",
        "Scan code for TODO/FIXME/HACK/XXX markers and return {path, line, text, kind}. "
        "Use to surface known-incomplete work. Input: {} . NOT for security issues (use "
        "analysis_security_grep) or missing tests (use analysis_test_gaps).",
        {},
    )
    async def analysis_todos(args: dict[str, Any]) -> dict[str, Any]:
        return await analysis_ops.op_analysis_todos(ctx, args)

    @tool(
        "analysis_dead_code",
        "Detect unused code/imports via vulture/autoflake, falling back to AST. Use to "
        "find removable code. Input: {path?}. NOT for cyclomatic complexity (use "
        "analysis_complexity) or import listing (use analysis_imports).",
        {"path": str},
    )
    async def analysis_dead_code(args: dict[str, Any]) -> dict[str, Any]:
        return await analysis_ops.op_analysis_dead_code(ctx, args)

    @tool(
        "analysis_complexity",
        "Compute per-function complexity via radon, falling back to branch-keyword "
        "counts. Use to find risky hotspots to refactor. Input: {path?}. NOT for dead "
        "code (use analysis_dead_code) or file size (use analysis_size).",
        {"path": str},
    )
    async def analysis_complexity(args: dict[str, Any]) -> dict[str, Any]:
        return await analysis_ops.op_analysis_complexity(ctx, args)

    @tool(
        "analysis_imports",
        "Parse one Python file with ast and list its imported modules. Use to map a "
        "file's dependencies. Input: {path}. NOT for the file's structure (use "
        "repo_outline) or unused imports (use analysis_dead_code).",
        {"path": str},
    )
    async def analysis_imports(args: dict[str, Any]) -> dict[str, Any]:
        return await analysis_ops.op_analysis_imports(ctx, args)

    @tool(
        "analysis_size",
        "Count lines per source file and report the top-20 largest files plus totals by "
        "extension. Use to find oversized files. Input: {} . NOT for complexity (use "
        "analysis_complexity) or directory listing (use repo_list).",
        {},
    )
    async def analysis_size(args: dict[str, Any]) -> dict[str, Any]:
        return await analysis_ops.op_analysis_size(ctx, args)

    @tool(
        "analysis_security_grep",
        "Grep for risky patterns: hardcoded secrets, eval/exec, shell=True, SQL string "
        "concat. Use for a fast static security pass. Input: {} . NOT for a deep agent "
        "review (use review_spawn_security) or perf issues (use analysis_perf_patterns).",
        {},
    )
    async def analysis_security_grep(args: dict[str, Any]) -> dict[str, Any]:
        return await analysis_ops.op_analysis_security_grep(ctx, args)

    @tool(
        "analysis_perf_patterns",
        "Grep for performance smells: queries inside loops (N+1), unbounded list() on "
        "querysets. Use to flag scaling risks. Input: {} . NOT for security (use "
        "analysis_security_grep) or complexity (use analysis_complexity).",
        {},
    )
    async def analysis_perf_patterns(args: dict[str, Any]) -> dict[str, Any]:
        return await analysis_ops.op_analysis_perf_patterns(ctx, args)

    @tool(
        "analysis_test_gaps",
        "Walk src/ and report source files that have no matching test_*.py in tests/. "
        "Use to find untested modules. Input: {} . NOT for coverage percentages (use "
        "exec_coverage) or running tests (use exec_test).",
        {},
    )
    async def analysis_test_gaps(args: dict[str, Any]) -> dict[str, Any]:
        return await analysis_ops.op_analysis_test_gaps(ctx, args)

    return [
        analysis_todos,
        analysis_dead_code,
        analysis_complexity,
        analysis_imports,
        analysis_size,
        analysis_security_grep,
        analysis_perf_patterns,
        analysis_test_gaps,
    ]
