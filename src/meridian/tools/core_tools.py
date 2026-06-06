"""SDK decoration layer for the five core tools (Property 1 & 5).

Thin: each tool is a @tool closure delegating to a pure ``op_*`` in core_ops.
Descriptions live here (a decoration/registry concern) and state *what the tool
does, when to use it, when not, and its side effects* so selection stays
unambiguous as the registry grows.
"""

from __future__ import annotations

from typing import Any

from claude_agent_sdk import tool

from meridian.tools import core_ops
from meridian.tools.context import ToolContext

CORE_TOOL_NAMES = ["repo_read", "repo_search", "edit_apply", "exec_test", "state_update"]


def build_core_tools(ctx: ToolContext) -> list[Any]:
    @tool(
        "repo_read",
        "Read the full contents of one file. Use to inspect a specific file before "
        "editing. Input: {path}. Not for searching (use repo_search) or writing "
        "(use edit_apply).",
        {"path": str},
    )
    async def repo_read(args: dict[str, Any]) -> dict[str, Any]:
        return await core_ops.op_repo_read(ctx, args)

    @tool(
        "repo_search",
        "Search the repository for a substring and return matching files/lines. Use "
        "to locate code relevant to the issue. Input: {query, max_results?}. Returns "
        "a budgeted slice, never the whole tree.",
        {"query": str, "max_results": int},
    )
    async def repo_search(args: dict[str, Any]) -> dict[str, Any]:
        return await core_ops.op_repo_search(ctx, args)

    @tool(
        "edit_apply",
        "Apply a single exact-string replacement to a file; old_string must match "
        "exactly and uniquely. Use to implement the fix. Input: {path, old_string, "
        "new_string}. The only tool that writes files.",
        {"path": str, "old_string": str, "new_string": str},
    )
    async def edit_apply(args: dict[str, Any]) -> dict[str, Any]:
        return await core_ops.op_edit_apply(ctx, args)

    @tool(
        "exec_test",
        "Run the repo's tests (or a given command) and return a typed result. Use to "
        "validate a fix. Input: {command?} (default 'pytest -q'). Failures are "
        "deterministic feedback, not transient errors.",
        {"command": str},
    )
    async def exec_test(args: dict[str, Any]) -> dict[str, Any]:
        return await core_ops.op_exec_test(ctx, args)

    @tool(
        "state_update",
        "Update authoritative task state: set/replace the plan, mark a step done, "
        "and/or record a durable finding. Use to keep plan and conclusions current. "
        "Input: {plan?: [str], mark_done?: int, finding?: str}.",
        {"plan": list, "mark_done": int, "finding": str},
    )
    async def state_update(args: dict[str, Any]) -> dict[str, Any]:
        return await core_ops.op_state_update(ctx, args)

    return [repo_read, repo_search, edit_apply, exec_test, state_update]
