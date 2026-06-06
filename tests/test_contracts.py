"""W7 contract tests — every tool output validates against its pydantic schema.

Covers: vcs_branch, vcs_commit, vcs_open_pr, review_lint, review_spawn_security.
Also covers the blocking-security-report gate that must prevent vcs_open_pr.
"""
from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from unittest import mock

import pytest

from meridian.tools import vcs_ops
from meridian.tools.context import ToolContext
from meridian.tools.schemas import PRDraft, SecurityReport, ToolOutcome, ToolStatus
from tests.conftest import make_state

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _has_git() -> bool:
    import shutil
    return shutil.which("git") is not None


def _make_git_repo(path: Path) -> None:
    """Initialise a git repo with one commit so branch/commit tools can run."""
    _g = lambda *args: subprocess.run(list(args), check=True, capture_output=True)  # noqa: E731
    _g("git", "init", str(path))
    _g("git", "-C", str(path), "config", "user.email", "test@test.com")
    _g("git", "-C", str(path), "config", "user.name", "Test")
    (path / "README.md").write_text("hello\n")
    _g("git", "-C", str(path), "add", ".")
    _g("git", "-C", str(path), "commit", "-m", "init")


@pytest.fixture
def git_ctx(tmp_path: Path) -> ToolContext:
    _make_git_repo(tmp_path)
    return ToolContext(workspace=tmp_path, state=make_state())


@pytest.fixture
def ctx(tmp_path: Path) -> ToolContext:
    return ToolContext(workspace=tmp_path, state=make_state())


def _parse_outcome(result: dict) -> ToolOutcome:
    text = result["content"][0]["text"]
    return ToolOutcome.model_validate(json.loads(text))


# ---------------------------------------------------------------------------
# vcs_branch
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _has_git(), reason="git not available")
def test_vcs_branch_output_is_valid_tool_outcome(git_ctx: ToolContext) -> None:
    raw = asyncio.run(vcs_ops.op_vcs_branch(git_ctx, {"branch": "feat/test-1"}))
    outcome = _parse_outcome(raw)
    assert outcome.status == ToolStatus.ok
    assert outcome.payload is not None
    assert outcome.payload.get("branch") == "feat/test-1"


@pytest.mark.skipif(not _has_git(), reason="git not available")
def test_vcs_branch_duplicate_returns_error(git_ctx: ToolContext) -> None:
    asyncio.run(vcs_ops.op_vcs_branch(git_ctx, {"branch": "feat/dup"}))
    outcome = _parse_outcome(asyncio.run(vcs_ops.op_vcs_branch(git_ctx, {"branch": "feat/dup"})))
    assert outcome.status == ToolStatus.error


def test_vcs_branch_missing_name_returns_error(ctx: ToolContext) -> None:
    outcome = _parse_outcome(asyncio.run(vcs_ops.op_vcs_branch(ctx, {})))
    assert outcome.status == ToolStatus.error


# ---------------------------------------------------------------------------
# vcs_commit
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _has_git(), reason="git not available")
def test_vcs_commit_output_is_valid_tool_outcome(git_ctx: ToolContext) -> None:
    # Modify a file so there is something to commit.
    (git_ctx.workspace / "README.md").write_text("changed\n")
    raw = asyncio.run(vcs_ops.op_vcs_commit(git_ctx, {"message": "test commit"}))
    outcome = _parse_outcome(raw)
    assert outcome.status == ToolStatus.ok
    assert outcome.payload is not None
    assert "test commit" in outcome.payload.get("message", "")


@pytest.mark.skipif(not _has_git(), reason="git not available")
def test_vcs_commit_nothing_to_commit_returns_error(git_ctx: ToolContext) -> None:
    outcome = _parse_outcome(asyncio.run(vcs_ops.op_vcs_commit(git_ctx, {"message": "empty"})))
    assert outcome.status == ToolStatus.error
    assert outcome.deterministic is True


def test_vcs_commit_missing_message_returns_error(ctx: ToolContext) -> None:
    outcome = _parse_outcome(asyncio.run(vcs_ops.op_vcs_commit(ctx, {})))
    assert outcome.status == ToolStatus.error


# ---------------------------------------------------------------------------
# vcs_open_pr
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _has_git(), reason="git not available")
def test_vcs_open_pr_returns_pr_draft(git_ctx: ToolContext) -> None:
    outcome = _parse_outcome(
        asyncio.run(vcs_ops.op_vcs_open_pr(git_ctx, {"title": "Fix bug", "body": "details"}))
    )
    assert outcome.status == ToolStatus.ok
    payload = outcome.payload
    assert payload is not None
    draft = PRDraft.model_validate(payload)
    assert draft.title == "Fix bug"
    assert draft.branch  # non-empty


def test_vcs_open_pr_blocking_report_returns_error(ctx: ToolContext) -> None:
    outcome = _parse_outcome(
        asyncio.run(
            vcs_ops.op_vcs_open_pr(ctx, {"title": "Fix", "body": "x", "blocking": True})
        )
    )
    assert outcome.status == ToolStatus.error
    assert "blocked" in outcome.summary.lower()


def test_vcs_open_pr_blocking_string_true_returns_error(ctx: ToolContext) -> None:
    outcome = _parse_outcome(
        asyncio.run(
            vcs_ops.op_vcs_open_pr(ctx, {"title": "Fix", "body": "x", "blocking": "true"})
        )
    )
    assert outcome.status == ToolStatus.error


def test_vcs_open_pr_missing_title_returns_error(ctx: ToolContext) -> None:
    outcome = _parse_outcome(asyncio.run(vcs_ops.op_vcs_open_pr(ctx, {"body": "x"})))
    assert outcome.status == ToolStatus.error


# ---------------------------------------------------------------------------
# review_lint
# ---------------------------------------------------------------------------

def test_review_lint_output_is_valid_tool_outcome(ctx: ToolContext) -> None:
    outcome = _parse_outcome(asyncio.run(vcs_ops.op_review_lint(ctx, {})))
    # Either passes (ruff not found or clean) or fails with error status.
    assert isinstance(outcome.status, ToolStatus)
    assert outcome.payload is not None
    assert "passed" in outcome.payload


# ---------------------------------------------------------------------------
# review_spawn_security: schema contract
# ---------------------------------------------------------------------------

def test_review_spawn_security_returns_security_report_schema(ctx: ToolContext) -> None:
    """Mock SDK query returns well-formed JSON; result must validate as SecurityReport."""

    async def fake_query(**kwargs):
        from types import SimpleNamespace

        yield SimpleNamespace(
            result='{"findings": [], "max_severity": "info", "blocking": false}'
        )

    with mock.patch.dict(
        "sys.modules",
        {"claude_agent_sdk": mock.MagicMock(
            query=fake_query,
            ClaudeAgentOptions=mock.MagicMock(),
            create_sdk_mcp_server=mock.MagicMock(),
            tool=mock.MagicMock(side_effect=lambda *a, **kw: lambda f: f),
            AgentDefinition=mock.MagicMock(),
        )},
    ):
        result = asyncio.run(vcs_ops.op_review_spawn_security(ctx, {}))

    outcome = _parse_outcome(result)
    assert outcome.status == ToolStatus.ok
    report = SecurityReport.model_validate(outcome.payload)
    assert not report.blocking
    assert report.findings == []
