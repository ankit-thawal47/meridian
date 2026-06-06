"""Typed tool I/O contracts (Property 5 — Composable Tool Chains).

Every tool returns a schema-validated object; free text is a *field*, never
the integration contract. Downstream tools consume these types directly, so
the output of one tool is the typed input of the next. Raw stdout/large blobs
are stored by reference (``*_ref``), never inlined into the context window.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Severity(StrEnum):
    info = "info"
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class ToolStatus(StrEnum):
    ok = "ok"
    error = "error"


# --- repo.* ----------------------------------------------------------------
class RepoSearchHit(BaseModel):
    path: str
    line: int
    snippet: str


class RepoSlice(BaseModel):
    """A budget-sized view of the repo — never the whole tree (Property 3)."""

    files: list[str] = Field(default_factory=list)
    hits: list[RepoSearchHit] = Field(default_factory=list)
    token_cost: int = 0


class FileContent(BaseModel):
    path: str
    content: str
    truncated: bool = False


# --- edit.* ----------------------------------------------------------------
class FileEdit(BaseModel):
    path: str
    old_string: str
    new_string: str


class EditResult(BaseModel):
    path: str
    applied: bool
    reason: str | None = None


# --- exec.* ----------------------------------------------------------------
class TestResult(BaseModel):
    __test__ = False  # not a pytest test class despite the name

    passed: bool
    summary: str
    failures: list[str] = Field(default_factory=list)
    # Raw stdout/stderr persisted by reference, not inlined (Property 3).
    stdout_ref: str | None = None
    exit_code: int | None = None


# --- review.* --------------------------------------------------------------
class SecurityFinding(BaseModel):
    path: str
    line: int | None = None
    severity: Severity
    title: str
    detail: str


class SecurityReport(BaseModel):
    findings: list[SecurityFinding] = Field(default_factory=list)
    max_severity: Severity = Severity.info
    blocking: bool = False


# --- vcs.* -----------------------------------------------------------------
class PRDraft(BaseModel):
    title: str
    body: str
    branch: str
    diff_stat: str = ""


# --- generic envelope ------------------------------------------------------
class ToolOutcome(BaseModel):
    """Uniform envelope every tool wraps its typed payload in.

    The orchestrator reads ``status`` to drive retry classification
    (Property 4) and folds ``summary`` into TaskState (Property 3).
    """

    status: ToolStatus = ToolStatus.ok
    # Whether a failure is deterministic (don't retry; feed back to model)
    # or transient (retryable). Only meaningful when status == error.
    deterministic: bool = True
    summary: str = ""
    payload: dict | None = None
