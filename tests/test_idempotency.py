from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from meridian.tools import core_ops
from meridian.tools.context import ToolContext
from tests.conftest import make_state


@pytest.fixture
def ctx(tmp_path: Path) -> ToolContext:
    return ToolContext(workspace=tmp_path, state=make_state())


def _make_file(ctx: ToolContext, name: str, content: str) -> str:
    p = ctx.workspace / name
    p.write_text(content)
    return name


# --- edit_apply idempotency ---

def test_edit_apply_idempotent(ctx: ToolContext) -> None:
    """Calling op_edit_apply twice with identical args must not double-apply the edit."""
    fname = _make_file(ctx, "foo.py", "x = 1\n")
    args = {"path": fname, "old_string": "x = 1", "new_string": "x = 2"}

    r1 = asyncio.run(core_ops.op_edit_apply(ctx, args))
    content_after_first = (ctx.workspace / fname).read_text()

    r2 = asyncio.run(core_ops.op_edit_apply(ctx, args))
    content_after_second = (ctx.workspace / fname).read_text()

    # Both calls succeed.
    assert r1 == r2
    # File content is the same after both calls — second call was a no-op.
    assert content_after_first == content_after_second
    assert "x = 2" in content_after_first


def test_edit_apply_different_args_not_cached(ctx: ToolContext) -> None:
    """Different args produce independent results — cache key must be arg-specific."""
    fname = _make_file(ctx, "bar.py", "a = 1\nb = 2\n")
    args_a = {"path": fname, "old_string": "a = 1", "new_string": "a = 10"}
    args_b = {"path": fname, "old_string": "b = 2", "new_string": "b = 20"}

    asyncio.run(core_ops.op_edit_apply(ctx, args_a))
    asyncio.run(core_ops.op_edit_apply(ctx, args_b))

    content = (ctx.workspace / fname).read_text()
    assert "a = 10" in content
    assert "b = 20" in content


# --- exec_test idempotency ---

def test_exec_test_idempotent(ctx: ToolContext) -> None:
    """Running the same command twice returns the cached result; subprocess runs once."""
    run_count = 0
    original_shell = asyncio.create_subprocess_shell

    async def counting_shell(cmd, **kwargs):
        nonlocal run_count
        run_count += 1
        return await original_shell(cmd, **kwargs)

    args = {"command": "echo hello"}

    import unittest.mock as mock

    with mock.patch("meridian.tools.core_ops.asyncio.create_subprocess_shell", counting_shell):
        r1 = asyncio.run(core_ops.op_exec_test(ctx, args))
        r2 = asyncio.run(core_ops.op_exec_test(ctx, args))

    assert r1 == r2
    assert run_count == 1
