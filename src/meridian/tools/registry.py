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

from meridian.tools.context import ToolContext
from meridian.tools.core_tools import CORE_TOOL_NAMES, build_core_tools
from meridian.tools.retrieval import count_guard

SERVER_NAME = "meridian"


@dataclass
class ToolRegistry:
    server: Any  # McpSdkServerConfig
    tool_names: list[str]  # fully-qualified mcp__<server>__<tool> names


def build_registry(ctx: ToolContext) -> ToolRegistry:
    tools = build_core_tools(ctx)
    count_guard(tools)
    server = create_sdk_mcp_server(name=SERVER_NAME, version="0.1.0", tools=tools)
    names = [f"mcp__{SERVER_NAME}__{n}" for n in CORE_TOOL_NAMES]
    return ToolRegistry(server=server, tool_names=names)
