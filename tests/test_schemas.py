from __future__ import annotations

from meridian.tools.schemas import (
    PRDraft,
    SecurityReport,
    Severity,
    TestResult,
    ToolOutcome,
    ToolStatus,
)


def test_tool_outcome_roundtrip() -> None:
    out = ToolOutcome(summary="ok", payload={"a": 1})
    back = ToolOutcome.model_validate_json(out.model_dump_json())
    assert back.status is ToolStatus.ok
    assert back.deterministic is True
    assert back.payload == {"a": 1}


def test_testresult_failure_contract() -> None:
    t = TestResult(passed=False, summary="boom", failures=["boom"], exit_code=1)
    assert t.passed is False and t.failures == ["boom"] and t.exit_code == 1


def test_security_report_defaults() -> None:
    r = SecurityReport()
    assert r.blocking is False
    assert r.max_severity is Severity.info
    assert r.findings == []


def test_prdraft_contract() -> None:
    pr = PRDraft(title="Fix", body="...", branch="meridian/fix-1")
    assert pr.branch == "meridian/fix-1"
