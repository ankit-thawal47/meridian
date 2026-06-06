"""Intake: validate a request, persist a Task, enqueue the agent job.

The control plane never runs the agent inline — it only creates durable state
and hands off to an arq worker. Idempotency on (repo, issue_ref) is added with
GitHub webhooks in Phase 4.
"""

from __future__ import annotations

import uuid

from arq.connections import ArqRedis
from sqlalchemy.ext.asyncio import AsyncSession

from meridian.persistence.repository import create_task


async def submit_task(
    session: AsyncSession, redis: ArqRedis, *, repo: str, issue_ref: str, goal: str
) -> str:
    task_id = uuid.uuid4().hex
    await create_task(session, task_id=task_id, repo=repo, issue_ref=issue_ref, goal=goal)
    await redis.enqueue_job("run_meridian_task", task_id)
    return task_id
