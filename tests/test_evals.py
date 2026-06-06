from __future__ import annotations

from evals.run_evals import (
    eval_p1_no_hardwired_graph,
    eval_p2_isolation_negative,
    eval_p3_budget_invariant,
    eval_p4_retry_classification,
    eval_p5_contract_tests,
)


def test_p1_no_hardwired_graph() -> None:
    assert eval_p1_no_hardwired_graph() is True


def test_p2_isolation_negative() -> None:
    assert eval_p2_isolation_negative() is True


def test_p3_budget_invariant() -> None:
    assert eval_p3_budget_invariant() is True


def test_p4_retry_classification() -> None:
    assert eval_p4_retry_classification() is True


def test_p5_contract_tests() -> None:
    assert eval_p5_contract_tests() is True
