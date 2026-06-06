"""TaskState — the authoritative, compact record of a task (Property 3).

This object, not the chat history, is the source of truth for *what has
happened*. After every tool call the orchestrator folds a structured summary
in here and discards the raw output. The full task must be reconstructable
from TaskState alone — that is the coherence guarantee.

``render_context()`` emits the compact text injected into the agent each turn,
budgeted by region so the context window can never grow unbounded.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(UTC)


class TaskStatus(StrEnum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    budget_exceeded = "budget_exceeded"


class PlanStep(BaseModel):
    description: str
    done: bool = False


class Finding(BaseModel):
    """A durable, structured conclusion distilled from raw tool output."""

    source: str  # tool name that produced it
    summary: str
    at: datetime = Field(default_factory=_now)


class TaskState(BaseModel):
    task_id: str
    repo: str
    issue_ref: str
    goal: str

    status: TaskStatus = TaskStatus.pending
    plan: list[PlanStep] = Field(default_factory=list)
    files_touched: list[str] = Field(default_factory=list)
    tests_run: list[str] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)

    turns: int = 0
    cost_usd: float = 0.0
    updated_at: datetime = Field(default_factory=_now)

    # --- mutation helpers (keep state compact + authoritative) ---
    def record_finding(self, source: str, summary: str) -> None:
        self.findings.append(Finding(source=source, summary=summary))
        self._touch()

    def touch_file(self, path: str) -> None:
        if path not in self.files_touched:
            self.files_touched.append(path)
        self._touch()

    def record_test(self, name: str) -> None:
        if name not in self.tests_run:
            self.tests_run.append(name)
        self._touch()

    def set_plan(self, steps: list[str]) -> None:
        self.plan = [PlanStep(description=s) for s in steps]
        self._touch()

    def _touch(self) -> None:
        self.updated_at = _now()

    def render_context(self, max_findings: int = 25) -> str:
        """Compact, budgeted text snapshot injected into the agent each turn.

        Only structured conclusions appear here — never raw tool output.
        Findings are capped by count and the region is truncated to its token
        ceiling via RegionBudget, so the snapshot can never grow unbounded.
        """
        from meridian.context.budget import RegionBudget

        plan_lines = (
            "\n".join(f"  [{'x' if s.done else ' '}] {s.description}" for s in self.plan)
            or "  (no plan yet)"
        )
        recent = self.findings[-max_findings:]
        finding_lines = "\n".join(f"  - ({f.source}) {f.summary}" for f in recent) or "  (none)"
        rendered = (
            f"GOAL: {self.goal}\n"
            f"REPO: {self.repo}  ISSUE: {self.issue_ref}\n"
            f"STATUS: {self.status.value}  TURNS: {self.turns}  COST_USD: {self.cost_usd:.3f}\n"
            f"PLAN:\n{plan_lines}\n"
            f"FILES_TOUCHED: {', '.join(self.files_touched) or '(none)'}\n"
            f"TESTS_RUN: {', '.join(self.tests_run) or '(none)'}\n"
            f"FINDINGS (last {len(recent)}):\n{finding_lines}\n"
        )
        return RegionBudget().allocate("task_state", rendered)
