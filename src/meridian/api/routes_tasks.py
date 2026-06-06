"""Task API: submit, inspect status, read the trace; GitHub webhook intake."""

from __future__ import annotations

import hashlib
import hmac
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from meridian.config import get_settings
from meridian.control_plane.intake import submit_task
from meridian.persistence.db import get_session
from meridian.persistence.repository import get_spans, get_task, get_task_by_ref

router = APIRouter(prefix="/tasks", tags=["tasks"])
webhook_router = APIRouter(prefix="/webhook", tags=["webhook"])


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


def _verify_signature(secret: str, body: bytes, header: str | None) -> bool:
    """Constant-time HMAC-SHA256 check against the X-Hub-Signature-256 header."""
    if not header or not header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header)


@webhook_router.post("/github")
async def github_webhook(
    request: Request, session: AsyncSession = Depends(get_session)
) -> dict[str, str]:
    body = await request.body()
    secret = get_settings().github_webhook_secret
    if secret and not _verify_signature(
        secret, body, request.headers.get("X-Hub-Signature-256")
    ):
        raise HTTPException(401, "invalid signature")

    if request.headers.get("X-GitHub-Event") != "issues":
        return {"status": "ignored"}

    payload = json.loads(body or b"{}")
    if payload.get("action") != "opened":
        return {"status": "ignored"}

    repo_url = (payload.get("repository") or {}).get("clone_url", "")
    issue = payload.get("issue") or {}
    issue_ref = str(issue.get("number", ""))
    goal = f"{issue.get('title', '')}\n\n{issue.get('body', '') or ''}".strip()

    existing = await get_task_by_ref(session, repo=repo_url, issue_ref=issue_ref)
    if existing is not None:
        return {"status": "already_queued", "task_id": existing.id}

    task_id = await submit_task(
        session, request.app.state.redis, repo=repo_url, issue_ref=issue_ref, goal=goal
    )
    return {"status": "queued", "task_id": task_id}
