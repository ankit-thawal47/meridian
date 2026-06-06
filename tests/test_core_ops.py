from __future__ import annotations

import asyncio
import json
from typing import Any

from meridian.tools import core_ops
from meridian.tools.context import ToolContext


def _payload(result: dict[str, Any]) -> dict[str, Any]:
    return json.loads(result["content"][0]["text"])


def test_edit_then_read(ctx: ToolContext) -> None:
    (ctx.workspace / "hello.py").write_text("def f():\n    return 1\n")
    edit = _payload(
        asyncio.run(
            core_ops.op_edit_apply(
                ctx, {"path": "hello.py", "old_string": "return 1", "new_string": "return 2"}
            )
        )
    )
    assert edit["status"] == "ok"
    assert "hello.py" in ctx.state.files_touched  # state mutated by the tool (Property 3)

    read = _payload(asyncio.run(core_ops.op_repo_read(ctx, {"path": "hello.py"})))
    assert "return 2" in read["payload"]["content"]


def test_edit_rejects_nonunique(ctx: ToolContext) -> None:
    (ctx.workspace / "dup.py").write_text("x = 1\nx = 1\n")
    out = _payload(
        asyncio.run(
            core_ops.op_edit_apply(
                ctx, {"path": "dup.py", "old_string": "x = 1", "new_string": "x = 2"}
            )
        )
    )
    assert out["status"] == "error"
    assert out["deterministic"] is True  # don't retry; feed back to the model


def test_edit_confinement(ctx: ToolContext) -> None:
    out = _payload(asyncio.run(core_ops.op_repo_read(ctx, {"path": "../../../etc/passwd"})))
    assert out["status"] == "error"


def test_search_finds_query(ctx: ToolContext) -> None:
    (ctx.workspace / "m.py").write_text("alpha\nbeta TARGET gamma\n")
    out = _payload(asyncio.run(core_ops.op_repo_search(ctx, {"query": "TARGET"})))
    assert out["status"] == "ok"
    assert out["payload"]["hits"]
    assert out["payload"]["hits"][0]["path"] == "m.py"


def test_exec_test_captures_result(ctx: ToolContext) -> None:
    out = _payload(asyncio.run(core_ops.op_exec_test(ctx, {"command": "echo hi"})))
    assert out["status"] == "ok"
    assert out["payload"]["passed"] is True
    assert out["payload"]["exit_code"] == 0
    assert out["payload"]["stdout_ref"].startswith("blob:")  # raw output by reference
    assert "echo hi" in ctx.state.tests_run


def test_state_update(ctx: ToolContext) -> None:
    asyncio.run(core_ops.op_state_update(ctx, {"plan": ["a", "b"]}))
    asyncio.run(core_ops.op_state_update(ctx, {"mark_done": 0, "finding": "did a"}))
    assert ctx.state.plan[0].done is True
    assert any(f.summary == "did a" for f in ctx.state.findings)
