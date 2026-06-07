"""SDK @tool wrappers for the doc_* namespace (project documentation).

Thin closures over the pure ``op_doc_*`` functions in doc_ops. Descriptions name
the sibling to use instead so documentation reads never collide with code reads.
"""

from __future__ import annotations

from typing import Any

from claude_agent_sdk import tool

from meridian.tools import doc_ops
from meridian.tools.context import ToolContext

DOC_TOOL_NAMES = [
    "doc_read",
    "doc_search",
    "doc_api_spec",
    "doc_readme",
    "doc_changelog",
]


def build_doc_tools(ctx: ToolContext) -> list[Any]:
    @tool(
        "doc_read",
        "Read a .md/.rst doc and split it into H1/H2 sections {heading, content}. Use "
        "to read structured documentation. Input: {path}. NOT for source files (use "
        "repo_read) or the root README (use doc_readme).",
        {"path": str},
    )
    async def doc_read(args: dict[str, Any]) -> dict[str, Any]:
        return await doc_ops.op_doc_read(ctx, args)

    @tool(
        "doc_search",
        "Search only documentation (.md/.rst) for a query and return {path, line, "
        "snippet}. Use to find docs about a topic. Input: {query}. NOT for code search "
        "(use repo_search/exec_grep).",
        {"query": str},
    )
    async def doc_search(args: dict[str, Any]) -> dict[str, Any]:
        return await doc_ops.op_doc_search(ctx, args)

    @tool(
        "doc_api_spec",
        "Find and summarise an OpenAPI/Swagger spec (path count + first 20 endpoints). "
        "Use to learn the HTTP API surface. Input: {} . NOT for prose docs (use "
        "doc_read) or code (use repo_read).",
        {},
    )
    async def doc_api_spec(args: dict[str, Any]) -> dict[str, Any]:
        return await doc_ops.op_doc_api_spec(ctx, args)

    @tool(
        "doc_readme",
        "Read README.md from the workspace root. Use to get project overview/setup. "
        "Input: {} . NOT for arbitrary docs (use doc_read) or the changelog (use "
        "doc_changelog).",
        {},
    )
    async def doc_readme(args: dict[str, Any]) -> dict[str, Any]:
        return await doc_ops.op_doc_readme(ctx, args)

    @tool(
        "doc_changelog",
        "Read CHANGELOG from the workspace root (last 500 chars if large). Use to see "
        "recent release notes. Input: {} . NOT for the README (use doc_readme) or git "
        "history (use repo_log).",
        {},
    )
    async def doc_changelog(args: dict[str, Any]) -> dict[str, Any]:
        return await doc_ops.op_doc_changelog(ctx, args)

    return [doc_read, doc_search, doc_api_spec, doc_readme, doc_changelog]
