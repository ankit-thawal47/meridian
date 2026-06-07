"""Tool registry assembly (Property 1 — Model-Driven Tool Selection).

Builds the in-process MCP server exposing Meridian's tools for one task, and
returns the fully-qualified tool names the SDK should auto-approve. The model
selects from this registry every turn; there is no router or workflow graph.

As the registry grows toward 50+ tools, ``allowed_tool_names`` plus the
namespaced tool names (``repo_*``/``edit_*``/``exec_*``/``state_*``) keep
selection unambiguous. An LLM-judge ambiguity audit over the descriptions is
added in Phase 3.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server

from meridian.tools.analysis_tools import ANALYSIS_TOOL_NAMES, build_analysis_tools
from meridian.tools.context import ToolContext
from meridian.tools.core_tools import CORE_TOOL_NAMES, build_core_tools
from meridian.tools.doc_tools import DOC_TOOL_NAMES, build_doc_tools
from meridian.tools.issue_tools import ISSUE_TOOL_NAMES, build_issue_tools
from meridian.tools.retrieval import RETRIEVAL_THRESHOLD, count_guard, select_tools

SERVER_NAME = "meridian"


@dataclass
class ToolRegistry:
    server: Any  # McpSdkServerConfig
    tool_names: list[str]  # fully-qualified mcp__<server>__<tool> names


def build_registry(ctx: ToolContext) -> ToolRegistry:
    """Assemble the per-task MCP server.

    Below RETRIEVAL_THRESHOLD we eager-load every tool. Above it we retrieve only
    the top-k most relevant to the task (research §III.1: avoid the selection
    performance cliff). The MCP server and ``tool_names`` (the SDK whitelist) are
    kept in lock-step — a tool the SDK is allowed to call is always one the server
    actually defines.
    """
    all_tools = (
        build_core_tools(ctx)
        + build_analysis_tools(ctx)
        + build_doc_tools(ctx)
        + build_issue_tools(ctx)
    )
    all_names = (
        CORE_TOOL_NAMES + ANALYSIS_TOOL_NAMES + DOC_TOOL_NAMES + ISSUE_TOOL_NAMES
    )

    count_guard(all_tools)

    if len(all_tools) > RETRIEVAL_THRESHOLD:
        # Pick the top-k tools relevant to this task. issue_body/title are not
        # always present on TaskState, so fall back to the goal/issue_ref.
        query = (
            getattr(ctx.state, "issue_body", "")
            or getattr(ctx.state, "issue_title", "")
            or getattr(ctx.state, "goal", "")
            or getattr(ctx.state, "issue_ref", "")
            or ""
        )
        selected = select_tools(all_tools, query)
    else:
        selected = all_tools

    # tool_names must list exactly what the MCP server exposes.
    selected_set = {getattr(t, "name", None) for t in selected}
    selected_names = [n for n in all_names if n in selected_set]

    server = create_sdk_mcp_server(name=SERVER_NAME, version="0.1.0", tools=selected)
    names = [f"mcp__{SERVER_NAME}__{n}" for n in selected_names]
    return ToolRegistry(server=server, tool_names=names)
