"""Tests for the 40 new tool ops (Task 1): repo/edit/exec/state extensions plus
the analysis_*, doc_*, and issue_* namespaces. Pure ops are exercised directly
against a confined workspace, mirroring test_core_ops.py.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from meridian.tools import analysis_ops, core_ops, doc_ops, issue_ops
from meridian.tools.context import ToolContext


def _p(result: dict[str, Any]) -> dict[str, Any]:
    return json.loads(result["content"][0]["text"])


def _run(coro: Any) -> dict[str, Any]:
    return _p(asyncio.run(coro))


@pytest.fixture
def populated(ctx: ToolContext) -> ToolContext:
    w: Path = ctx.workspace
    (w / "src").mkdir()
    (w / "tests").mkdir()
    (w / "src" / "foo.py").write_text(
        "import os\nimport sys\n\n# TODO: tidy\n"
        "def handle(x):\n    if x:\n        return 1\n    return sys.argv\n"
    )
    (w / "README.md").write_text("# Proj\nhi\n## Setup\nrun\n")
    (w / "CHANGELOG.md").write_text("v1\n")
    return ctx


# --- repo.* ----------------------------------------------------------------
def test_repo_list_and_glob(populated: ToolContext) -> None:
    listing = _run(core_ops.op_repo_list(populated, {"path": "src"}))
    assert listing["status"] == "ok"
    assert any(e["name"] == "foo.py" for e in listing["payload"]["entries"])

    glob = _run(core_ops.op_repo_glob(populated, {"pattern": "src/*.py"}))
    assert "src/foo.py" in glob["payload"]["files"]


def test_repo_stat_and_outline(populated: ToolContext) -> None:
    st = _run(core_ops.op_repo_stat(populated, {"path": "src/foo.py"}))
    assert st["payload"]["is_file"] is True
    assert st["payload"]["size_bytes"] > 0

    outline = _run(core_ops.op_repo_outline(populated, {"path": "src/foo.py"}))
    names = [i["name"] for i in outline["payload"]["outline"]]
    assert "handle" in names


# --- edit.* ----------------------------------------------------------------
def test_edit_create_insert_rename_delete(ctx: ToolContext) -> None:
    created = _run(core_ops.op_edit_create(ctx, {"path": "a.txt", "content": "body"}))
    assert created["status"] == "ok"
    dup = _run(core_ops.op_edit_create(ctx, {"path": "a.txt", "content": "x"}))
    assert dup["status"] == "error"  # already exists

    ins = _run(core_ops.op_edit_insert(ctx, {"path": "a.txt", "line": 1, "text": "top"}))
    assert ins["status"] == "ok"
    assert (ctx.workspace / "a.txt").read_text().startswith("top\n")

    mv = _run(core_ops.op_edit_rename(ctx, {"path": "a.txt", "new_path": "b.txt"}))
    assert mv["status"] == "ok"
    assert (ctx.workspace / "b.txt").exists()

    rm = _run(core_ops.op_edit_delete(ctx, {"path": "b.txt"}))
    assert rm["status"] == "ok"
    assert not (ctx.workspace / "b.txt").exists()


# --- exec.* ----------------------------------------------------------------
def test_exec_run_blocks_injection(ctx: ToolContext) -> None:
    out = _run(core_ops.op_exec_run(ctx, {"command": "echo hi; rm -rf /"}))
    assert out["status"] == "error"


def test_exec_run_executes_simple_command(ctx: ToolContext) -> None:
    out = _run(core_ops.op_exec_run(ctx, {"command": "python --version"}))
    assert out["payload"]["exit_code"] == 0


# --- state.* ---------------------------------------------------------------
def test_state_metric_artifact_get(ctx: ToolContext) -> None:
    _run(core_ops.op_state_record_metric(ctx, {"key": "cov", "value": 90}))
    _run(core_ops.op_state_add_artifact(ctx, {"name": "report", "path": "r.md"}))
    snap = _run(core_ops.op_state_get(ctx, {}))
    sources = {f["source"] for f in snap["payload"]["state"]["findings"]}
    assert {"metric", "artifact"} <= sources


def test_state_annotate_requires_valid_step(ctx: ToolContext) -> None:
    out = _run(core_ops.op_state_annotate(ctx, {"step": 0, "note": "x"}))
    assert out["status"] == "error"  # no plan yet
    ctx.state.set_plan(["do thing"])
    out2 = _run(core_ops.op_state_annotate(ctx, {"step": 0, "note": "started"}))
    assert out2["status"] == "ok"


# --- analysis.* ------------------------------------------------------------
def test_analysis_todos_and_imports(populated: ToolContext) -> None:
    todos = _run(analysis_ops.op_analysis_todos(populated, {}))
    assert any(t["kind"] == "TODO" for t in todos["payload"]["todos"])

    imports = _run(analysis_ops.op_analysis_imports(populated, {"path": "src/foo.py"}))
    assert set(imports["payload"]["modules"]) >= {"os", "sys"}


def test_analysis_test_gaps_and_size(populated: ToolContext) -> None:
    gaps = _run(analysis_ops.op_analysis_test_gaps(populated, {}))
    assert "src/foo.py" in gaps["payload"]["untested"]

    size = _run(analysis_ops.op_analysis_size(populated, {}))
    assert size["payload"]["totals_by_ext"][".py"] > 0


def test_analysis_security_grep_flags_secret(ctx: ToolContext) -> None:
    (ctx.workspace / "cfg.py").write_text('password = "hunter2"\n')
    hits = _run(analysis_ops.op_analysis_security_grep(ctx, {}))
    assert any(h["path"] == "cfg.py" for h in hits["payload"]["hits"])


# --- doc.* -----------------------------------------------------------------
def test_doc_read_sections_and_rejects_code(populated: ToolContext) -> None:
    doc = _run(doc_ops.op_doc_read(populated, {"path": "README.md"}))
    headings = [s["heading"] for s in doc["payload"]["sections"]]
    assert "Setup" in headings

    bad = _run(doc_ops.op_doc_read(populated, {"path": "src/foo.py"}))
    assert bad["status"] == "error"  # not a doc file


def test_doc_readme_and_changelog(populated: ToolContext) -> None:
    assert _run(doc_ops.op_doc_readme(populated, {}))["status"] == "ok"
    assert _run(doc_ops.op_doc_changelog(populated, {}))["status"] == "ok"


# --- issue.* ---------------------------------------------------------------
def test_issue_describe_reads_state(ctx: ToolContext) -> None:
    out = _run(issue_ops.op_issue_describe(ctx, {}))
    assert out["payload"]["ref"] == "#1"  # from make_state issue_ref


def test_issue_related_matches_filenames(populated: ToolContext) -> None:
    out = _run(issue_ops.op_issue_related(populated, {"query": "foo handle"}))
    assert "src/foo.py" in out["payload"]["files"]


def test_issue_comment_requires_token(ctx: ToolContext) -> None:
    out = _run(issue_ops.op_issue_comment(ctx, {"body": "hi"}))
    assert out["status"] == "error"  # no github_token configured
