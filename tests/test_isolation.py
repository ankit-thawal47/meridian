"""W3 isolation tests — SecuritySubagent definition and spawn failure handling."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest import mock

import pytest

from meridian.agent.subagents import (
    _ALLOWED_TOOLS,
    build_security_subagent_definition,
)
from meridian.tools import vcs_ops
from meridian.tools.context import ToolContext
from meridian.tools.schemas import ToolStatus
from tests.conftest import make_state


@pytest.fixture
def ctx(tmp_path: Path) -> ToolContext:
    return ToolContext(workspace=tmp_path, state=make_state())


# --- AgentDefinition contract ---

def test_security_subagent_tools_read_only() -> None:
    defn = build_security_subagent_definition()
    assert set(defn.tools or []) == set(_ALLOWED_TOOLS)
    assert "edit_apply" not in (defn.tools or [])
    assert "exec_test" not in (defn.tools or [])


def test_security_subagent_disallowed_includes_write_tools() -> None:
    defn = build_security_subagent_definition()
    disallowed = set(defn.disallowedTools or [])
    assert "edit_apply" in disallowed
    assert "exec_test" in disallowed


def test_security_subagent_disallowed_includes_vcs_tools() -> None:
    defn = build_security_subagent_definition()
    disallowed = set(defn.disallowedTools or [])
    assert "vcs_branch" in disallowed
    assert "vcs_commit" in disallowed
    assert "vcs_open_pr" in disallowed


def test_security_subagent_max_turns_capped() -> None:
    defn = build_security_subagent_definition()
    assert defn.maxTurns is not None
    assert defn.maxTurns <= 20


def test_security_subagent_has_description() -> None:
    defn = build_security_subagent_definition()
    assert defn.description and len(defn.description) > 10


# --- review_spawn_security: SDK crash → typed error ---

def test_spawn_security_sdk_crash_returns_typed_error(ctx: ToolContext) -> None:
    """SDK crash → ToolOutcome(status=error, deterministic=False)."""
    import json

    _sdk_mock = mock.MagicMock(
        query=mock.AsyncMock(side_effect=RuntimeError("boom"))
    )
    with mock.patch.dict("sys.modules", {"claude_agent_sdk": _sdk_mock}):
        result = asyncio.run(vcs_ops.op_review_spawn_security(ctx, {"focus": "check"}))

    content = result["content"][0]["text"]
    outcome = json.loads(content)
    assert outcome["status"] == ToolStatus.error
    assert outcome["deterministic"] is False


# --- parent context not contaminated ---

def test_parent_call_cache_unchanged_after_spawn_failure(ctx: ToolContext) -> None:
    """After a subagent crash, parent ToolContext._call_cache must be unchanged."""
    ctx._call_cache["existing"] = {"data": "preserved"}  # type: ignore[attr-defined]

    _sdk_mock = mock.MagicMock(
        query=mock.AsyncMock(side_effect=RuntimeError("boom"))
    )
    with mock.patch.dict("sys.modules", {"claude_agent_sdk": _sdk_mock}):
        asyncio.run(vcs_ops.op_review_spawn_security(ctx, {}))

    assert ctx._call_cache.get("existing") == {"data": "preserved"}  # type: ignore[attr-defined]
