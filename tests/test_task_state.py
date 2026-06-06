from __future__ import annotations

from meridian.agent.task_state import TaskState

from .conftest import make_state


def test_render_contains_goal_plan_and_findings() -> None:
    st = make_state()
    st.set_plan(["analyze", "fix"])
    st.record_finding("repo_search", "found the bug in auth.py")
    txt = st.render_context()
    assert "GOAL: g" in txt
    assert "[ ] analyze" in txt
    assert "found the bug in auth.py" in txt


def test_state_is_authoritative_roundtrip() -> None:
    # The full task must be reconstructable from TaskState alone (Property 3).
    st = make_state()
    st.set_plan(["a"])
    st.touch_file("auth.py")
    st.record_test("pytest -q")
    st.record_finding("exec_test", "tests fail on null token")
    restored = TaskState.model_validate_json(st.model_dump_json())
    assert restored.files_touched == ["auth.py"]
    assert restored.tests_run == ["pytest -q"]
    assert len(restored.findings) == 1
    assert restored.plan[0].description == "a"


def test_render_caps_findings() -> None:
    st = make_state()
    for i in range(40):
        st.record_finding("s", f"finding-{i}")
    txt = st.render_context(max_findings=25)
    assert txt.count("- (s)") == 25
