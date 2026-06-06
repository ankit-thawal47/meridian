from __future__ import annotations

import pytest

from meridian.tools.context import ToolContext


def test_safe_path_allows_inside(ctx: ToolContext) -> None:
    (ctx.workspace / "a.txt").write_text("x")
    assert ctx.safe_path("a.txt") == (ctx.workspace / "a.txt").resolve()
    assert ctx.safe_path("sub/b.txt") == (ctx.workspace / "sub" / "b.txt").resolve()


def test_safe_path_blocks_traversal(ctx: ToolContext) -> None:
    # Confinement is enforced by construction (Property 2 / 10).
    with pytest.raises(ValueError):
        ctx.safe_path("../escape.txt")
    with pytest.raises(ValueError):
        ctx.safe_path("../../etc/passwd")


def test_store_blob_persists_and_refs(ctx: ToolContext) -> None:
    ref = ctx.store_blob("a lot of raw output")
    assert ref.startswith("blob:")
    stored = (ctx.workspace / ".meridian" / "blobs" / ref.split(":", 1)[1]).read_text()
    assert stored == "a lot of raw output"
