from __future__ import annotations

from pathlib import Path

import pytest

from meridian.agent.task_state import TaskState
from meridian.tools.context import ToolContext


def make_state() -> TaskState:
    return TaskState(task_id="t1", repo="repo", issue_ref="#1", goal="g")


@pytest.fixture
def ctx(tmp_path: Path) -> ToolContext:
    return ToolContext(workspace=tmp_path, state=make_state())
