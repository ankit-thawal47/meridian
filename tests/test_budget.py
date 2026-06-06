from __future__ import annotations

from meridian.context.budget import (
    REGION_CEILINGS,
    TOTAL_BUDGET,
    RegionBudget,
    estimate_tokens,
)


def test_estimate_tokens_nonzero() -> None:
    assert estimate_tokens("hello world") > 0


def test_allocate_truncates_over_ceiling() -> None:
    budget = RegionBudget({"task_state": 10})
    text = "x" * 1000
    out = budget.allocate("task_state", text)
    assert len(out) < len(text)


def test_allocate_fits_under_ceiling() -> None:
    budget = RegionBudget({"task_state": 1000})
    text = "small"
    assert budget.allocate("task_state", text) == text


def test_within_budget_total() -> None:
    assert sum(REGION_CEILINGS.values()) <= TOTAL_BUDGET
    budget = RegionBudget()
    for region in REGION_CEILINGS:
        budget.allocate(region, "x" * (REGION_CEILINGS[region] * 4))
    assert budget.within_budget()


def test_render_context_stays_within_budget() -> None:
    from meridian.agent.task_state import TaskState

    state = TaskState(task_id="t", repo="r", issue_ref="#1", goal="x" * 5000)
    state.set_plan([f"step {i}" for i in range(100)])
    for i in range(50):
        state.record_finding("s", f"finding {i}: " + "x" * 200)
    rendered = state.render_context()
    assert estimate_tokens(rendered) <= TOTAL_BUDGET
