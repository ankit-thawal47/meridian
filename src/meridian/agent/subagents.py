"""SecuritySubagent definition (W3 — Genuine Subagent Isolation).

The SecuritySubagent is a read-only reviewer: it can search and read the
workspace but is explicitly denied write tools (edit_apply, exec_test, vcs_*).
Its own context window is SDK-guaranteed separate from the parent task's window,
so no intermediate reasoning leaks into the parent (Research I.5, II.2).

Two exports:
  build_security_subagent_definition() — AgentDefinition for ClaudeAgentOptions.agents
  build_security_subagent_options(ctx)  — restricted ClaudeAgentOptions for programmatic spawn
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from meridian.tools.context import ToolContext

SECURITY_SUBAGENT_PROMPT = """\
You are a security reviewer. Your sole job is to inspect the provided codebase
changes or files for security vulnerabilities. You are read-only: use repo_read
and repo_search only. Do not modify anything.

Look for:
- Hardcoded secrets or credentials (tokens, passwords, API keys)
- Injection vulnerabilities (SQL, command, path traversal, SSRF)
- Insecure imports or dangerous subprocess usage
- Secrets in test fixtures or configuration files

After reviewing, output a JSON block (and ONLY the JSON block) matching this
exact schema on the final line of your response:

{"findings": [{"path": "...", "line": <int or null>,
"severity": "info|low|medium|high|critical", "title": "...", "detail": "..."}],
"max_severity": "info|low|medium|high|critical", "blocking": <true|false>}

Set blocking=true if any finding has severity "high" or "critical".
If no issues found, output: {"findings": [], "max_severity": "info", "blocking": false}
"""

# Tools the security subagent is permitted to call (read-only).
_ALLOWED_TOOLS = ["repo_read", "repo_search"]

# Tools the security subagent must never call.
_DISALLOWED_TOOLS = [
    "edit_apply",
    "exec_test",
    "vcs_branch",
    "vcs_commit",
    "vcs_open_pr",
    "review_lint",
    "state_update",
]


def build_security_subagent_definition() -> Any:
    """Return an AgentDefinition for ClaudeAgentOptions.agents registration."""
    from claude_agent_sdk import AgentDefinition

    return AgentDefinition(
        description="Read-only security reviewer — inspects code for vulnerabilities",
        prompt=SECURITY_SUBAGENT_PROMPT,
        tools=_ALLOWED_TOOLS,
        disallowedTools=_DISALLOWED_TOOLS,
        permissionMode="default",
        maxTurns=15,
    )


def build_security_subagent_options(ctx: ToolContext) -> Any:
    """Build restricted ClaudeAgentOptions for a programmatic sub-query.

    The subagent gets its own in-process MCP server wired to the same workspace
    but only exposing read-only tools. This is the second isolation layer: the
    AgentDefinition covers SDK-native invocation; these options cover explicit
    op_review_spawn_security() spawning.
    """
    from claude_agent_sdk import ClaudeAgentOptions, create_sdk_mcp_server, tool

    from meridian.config import get_settings

    # Build a read-only MCP server for the subagent — repo_read + repo_search only.
    @tool(
        "repo_read",
        "Read file contents. Input: {path}.",
        {"path": str},
    )
    async def _repo_read(args: dict[str, Any]) -> dict[str, Any]:
        from meridian.tools.core_ops import op_repo_read

        return await op_repo_read(ctx, args)

    @tool(
        "repo_search",
        "Search for a substring. Input: {query, max_results?}.",
        {"query": str, "max_results": int},
    )
    async def _repo_search(args: dict[str, Any]) -> dict[str, Any]:
        from meridian.tools.core_ops import op_repo_search

        return await op_repo_search(ctx, args)

    server = create_sdk_mcp_server(
        name="meridian_sec", version="0.1.0", tools=[_repo_read, _repo_search]
    )
    allowed = ["mcp__meridian_sec__repo_read", "mcp__meridian_sec__repo_search"]
    s = get_settings()
    return ClaudeAgentOptions(
        system_prompt=SECURITY_SUBAGENT_PROMPT,
        mcp_servers={"meridian_sec": server},
        allowed_tools=allowed,
        disallowed_tools=_DISALLOWED_TOOLS,
        permission_mode="default",
        max_turns=15,
        model=s.model_fast,
        setting_sources=[],
        cwd=str(ctx.workspace),
    )
