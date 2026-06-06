"""SDK decoration layer for all Meridian tools (Property 1 & 5).

Thin: each tool is a @tool closure delegating to a pure ``op_*`` in core_ops
or vcs_ops. Descriptions live here and state *what the tool does, when to use
it, when not, and its side effects* so selection stays unambiguous as the
registry grows.

Tool namespaces:
  repo_*   — read the repository
  edit_*   — modify files
  exec_*   — run commands / tests
  state_*  — update authoritative task state
  vcs_*    — git operations (branch, commit, PR)
  review_* — validation and security review
"""

from __future__ import annotations

from typing import Any

from claude_agent_sdk import tool

from meridian.tools import core_ops, vcs_ops
from meridian.tools.context import ToolContext

CORE_TOOL_NAMES = [
    "repo_read",
    "repo_search",
    "edit_apply",
    "exec_test",
    "state_update",
    "vcs_branch",
    "vcs_commit",
    "vcs_open_pr",
    "review_lint",
    "review_spawn_security",
]


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

    @tool(
        "vcs_branch",
        "Create a new git branch in the workspace. Use before editing to keep changes "
        "isolated from the default branch. Input: {branch}. Not for committing "
        "(use vcs_commit) or opening a PR (use vcs_open_pr).",
        {"branch": str},
    )
    async def vcs_branch(args: dict[str, Any]) -> dict[str, Any]:
        return await vcs_ops.op_vcs_branch(ctx, args)

    @tool(
        "vcs_commit",
        "Stage all workspace changes and commit with a message. Use after editing to "
        "checkpoint work. Input: {message}. Fails if nothing to commit.",
        {"message": str},
    )
    async def vcs_commit(args: dict[str, Any]) -> dict[str, Any]:
        return await vcs_ops.op_vcs_commit(ctx, args)

    @tool(
        "vcs_open_pr",
        "Open a pull request for the current branch. Pushes to origin if a GitHub "
        "token is configured; returns a PRDraft either way. Input: {title, body, "
        "base?, blocking?}. Pass blocking=true to prevent PR open when a security "
        "report is blocking.",
        {"title": str, "body": str, "base": str, "blocking": bool},
    )
    async def vcs_open_pr(args: dict[str, Any]) -> dict[str, Any]:
        return await vcs_ops.op_vcs_open_pr(ctx, args)

    @tool(
        "review_lint",
        "Run ruff linting on the workspace (or a given path) and return a pass/fail "
        "result with lint output. Use before opening a PR. Input: {path?}.",
        {"path": str},
    )
    async def review_lint(args: dict[str, Any]) -> dict[str, Any]:
        return await vcs_ops.op_review_lint(ctx, args)

    @tool(
        "review_spawn_security",
        "Spawn the SecuritySubagent to review the workspace for vulnerabilities. "
        "Returns a typed SecurityReport with findings and a blocking flag. Use before "
        "vcs_open_pr. Input: {focus?}. Not for editing (use edit_apply) or linting "
        "(use review_lint).",
        {"focus": str},
    )
    async def review_spawn_security(args: dict[str, Any]) -> dict[str, Any]:
        return await vcs_ops.op_review_spawn_security(ctx, args)

    return [
        repo_read,
        repo_search,
        edit_apply,
        exec_test,
        state_update,
        vcs_branch,
        vcs_commit,
        vcs_open_pr,
        review_lint,
        review_spawn_security,
    ]
