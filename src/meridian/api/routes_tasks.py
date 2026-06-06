"""Task API: submit, inspect status, read the trace."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from meridian.control_plane.intake import submit_task
from meridian.persistence.db import get_session
from meridian.persistence.repository import get_spans, get_task

router = APIRouter(prefix="/tasks", tags=["tasks"])


class CreateTaskRequest(BaseModel):
    repo: str  # local path or https git URL
    issue_ref: str
    goal: str  # the issue text / what to fix


class CreateTaskResponse(BaseModel):
    task_id: str
    status: str = "queued"


class TaskView(BaseModel):
    task_id: str
    repo: str
    issue_ref: str
    status: str
    turns: int
    cost_usd: float
    state: dict


class SpanView(BaseModel):
    kind: str
    name: str
    summary: str
    cost_usd: float
    outcome: str


@router.post("", response_model=CreateTaskResponse)
async def create(
    body: CreateTaskRequest, request: Request, session: AsyncSession = Depends(get_session)
) -> CreateTaskResponse:
    task_id = await submit_task(
        session, request.app.state.redis, repo=body.repo, issue_ref=body.issue_ref, goal=body.goal
    )
    return CreateTaskResponse(task_id=task_id)


@router.get("/{task_id}", response_model=TaskView)
async def read(task_id: str, session: AsyncSession = Depends(get_session)) -> TaskView:
    task = await get_task(session, task_id)
    if task is None:
        raise HTTPException(404, "task not found")
    return TaskView(
        task_id=task.id,
        repo=task.repo,
        issue_ref=task.issue_ref,
        status=task.status,
        turns=task.turns,
        cost_usd=task.cost_usd,
        state=task.state or {},
    )


@router.get("/{task_id}/trace", response_model=list[SpanView])
async def trace(task_id: str, session: AsyncSession = Depends(get_session)) -> list[SpanView]:
    if await get_task(session, task_id) is None:
        raise HTTPException(404, "task not found")
    spans = await get_spans(session, task_id)
    return [
        SpanView(
            kind=s.kind, name=s.name, summary=s.summary, cost_usd=s.cost_usd, outcome=s.outcome
        )
        for s in spans
    ]
