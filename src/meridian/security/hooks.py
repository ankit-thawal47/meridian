"""SDK PreToolUse / PostToolUse hooks for security policy (Property 4 / W1).

path_guard_hook  — PreToolUse: deny writes to protected paths (.git, .env, etc.)
secret_scrub_hook — PostToolUse: replace secrets in tool output before the model
                    sees them or they are persisted in a span.

Both hooks are registered via ClaudeAgentOptions.hooks in sdk_session.build_options.
"""

from __future__ import annotations

import fnmatch
import json
import re
from typing import Any, cast

# Glob patterns for paths the agent must never write to.
_PROTECTED_GLOBS = [
    ".git",
    ".git/*",
    ".env",
    ".env.*",
    ".github",
    ".github/*",
    "*.pem",
    "*.key",
    "pyproject.toml",
    "Makefile",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
]

# Patterns that identify secrets. Each group-1 match is redacted.
_SECRET_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(AKIA[0-9A-Z]{16})"),  # AWS access key ID
    re.compile(r"(ASIA[0-9A-Z]{16})"),  # AWS temporary access key
    re.compile(r"(github_pat_[A-Za-z0-9_]{82})"),  # GitHub fine-grained PAT
    re.compile(r"(ghp_[A-Za-z0-9]{36})"),  # GitHub classic PAT
    re.compile(r"(ghs_[A-Za-z0-9]{36})"),  # GitHub Actions token
    re.compile(r"(sk-[A-Za-z0-9]{48})"),  # OpenAI secret key
    re.compile(r"(xoxb-[0-9]+-[A-Za-z0-9-]+)"),  # Slack bot token
    re.compile(r"(xoxp-[0-9]+-[0-9]+-[0-9]+-[A-Za-z0-9]+)"),  # Slack user token
]

_REDACTED = "***REDACTED***"


def _is_protected(path: str) -> bool:
    name = path.lstrip("/")
    return any(fnmatch.fnmatch(name, pat) for pat in _PROTECTED_GLOBS)


def _scrub(text: str) -> str:
    for pat in _SECRET_PATTERNS:
        text = pat.sub(_REDACTED, text)
    return text


async def path_guard_hook(
    inp: Any, tool_use_id: str | None, ctx: Any
) -> dict[str, Any]:
    if inp.get("hook_event_name") != "PreToolUse":
        return {"continue_": True}
    path = (inp.get("tool_input") or {}).get("path", "")
    if path and _is_protected(path):
        return {
            "continue_": False,
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": f"write to protected path blocked: {path}",
            },
        }
    return {"continue_": True}


async def secret_scrub_hook(
    inp: Any, tool_use_id: str | None, ctx: Any
) -> dict[str, Any]:
    if inp.get("hook_event_name") != "PostToolUse":
        return {"continue_": True}
    raw = json.dumps(inp.get("tool_response", ""))
    scrubbed = _scrub(raw)
    if scrubbed == raw:
        return {"continue_": True}
    try:
        updated = json.loads(scrubbed)
    except json.JSONDecodeError:
        updated = scrubbed
    return {
        "continue_": True,
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "updatedToolOutput": updated,
        },
    }


def build_security_hooks() -> Any:
    """Return the hooks dict for ClaudeAgentOptions.hooks.

    Typed as Any to avoid threading the verbose HookCallback/HookMatcher
    union through the whole module; the SDK validates at runtime.
    """
    from claude_agent_sdk import HookCallback, HookMatcher

    return {
        "PreToolUse": [HookMatcher(hooks=[cast(HookCallback, path_guard_hook)])],
        "PostToolUse": [HookMatcher(hooks=[cast(HookCallback, secret_scrub_hook)])],
    }
