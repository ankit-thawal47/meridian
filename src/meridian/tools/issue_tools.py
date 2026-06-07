"""SDK @tool wrappers for the issue_* namespace (GitHub issue interaction).

Thin closures over the pure ``op_issue_*`` functions in issue_ops. The mutating
tools call the rate-limited GitHub API; descriptions name the sibling to use
instead so issue ops never collide with PR ops (vcs_*) or local state (state_*).
"""

from __future__ import annotations

from typing import Any

from claude_agent_sdk import tool

from meridian.tools import issue_ops
from meridian.tools.context import ToolContext

ISSUE_TOOL_NAMES = [
    "issue_describe",
    "issue_comment",
    "issue_label",
    "issue_related",
    "issue_close",
]


def build_issue_tools(ctx: ToolContext) -> list[Any]:
    @tool(
        "issue_describe",
        "Return the issue's title and body from local task state (no API call). Use to "
        "recall what the issue asks for. Input: {} . NOT for posting a comment (use "
        "issue_comment) or finding related code (use issue_related).",
        {},
    )
    async def issue_describe(args: dict[str, Any]) -> dict[str, Any]:
        return await issue_ops.op_issue_describe(ctx, args)

    @tool(
        "issue_comment",
        "Post a comment to the GitHub issue (rate-limited; requires github_token). Use "
        "to report progress on the issue. Input: {body, number?}. NOT for labelling "
        "(use issue_label) or closing (use issue_close).",
        {"body": str, "number": int},
    )
    async def issue_comment(args: dict[str, Any]) -> dict[str, Any]:
        return await issue_ops.op_issue_comment(ctx, args)

    @tool(
        "issue_label",
        "Set labels on the GitHub issue (rate-limited; requires github_token). Use to "
        "categorise the issue. Input: {labels: [str], number?}. NOT for commenting (use "
        "issue_comment) or closing (use issue_close).",
        {"labels": list, "number": int},
    )
    async def issue_label(args: dict[str, Any]) -> dict[str, Any]:
        return await issue_ops.op_issue_label(ctx, args)

    @tool(
        "issue_related",
        "Find local files whose name/content matches words from the issue title. Use to "
        "locate code the issue is about. Input: {query?}. NOT for general code search "
        "(use repo_search) or reading the issue text (use issue_describe).",
        {"query": str},
    )
    async def issue_related(args: dict[str, Any]) -> dict[str, Any]:
        return await issue_ops.op_issue_related(ctx, args)

    @tool(
        "issue_close",
        "Close the GitHub issue (rate-limited; requires github_token). Use only after "
        "the work is merged/resolved. Input: {number?}. NOT for opening a PR (use "
        "vcs_open_pr) or commenting (use issue_comment).",
        {"number": int},
    )
    async def issue_close(args: dict[str, Any]) -> dict[str, Any]:
        return await issue_ops.op_issue_close(ctx, args)

    return [issue_describe, issue_comment, issue_label, issue_related, issue_close]
