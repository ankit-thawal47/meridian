"""Data access + a Postgres-backed TraceSink."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from meridian.agent.task_state import TaskState
from meridian.observability.tracing import SpanRecord
from meridian.persistence.models import Task, TraceSpan


async def create_task(
    session: AsyncSession, *, task_id: str, repo: str, issue_ref: str, goal: str
) -> Task:
    task = Task(id=task_id, repo=repo, issue_ref=issue_ref, goal=goal, status="pending", state={})
    session.add(task)
    await session.commit()
    return task


async def get_task(session: AsyncSession, task_id: str) -> Task | None:
    return await session.get(Task, task_id)


async def get_spans(session: AsyncSession, task_id: str) -> list[TraceSpan]:
    rows = await session.execute(
        select(TraceSpan).where(TraceSpan.task_id == task_id).order_by(TraceSpan.id)
    )
    return list(rows.scalars().all())


async def save_state(session: AsyncSession, state: TaskState) -> None:
    task = await session.get(Task, state.task_id)
    if task is None:
        return
    task.status = state.status.value
    task.cost_usd = state.cost_usd
    task.turns = state.turns
    task.state = state.model_dump(mode="json")
    await session.commit()


@dataclass
class DbTraceSink:
    """TraceSink that persists each span in its own short transaction."""

    sessionmaker: async_sessionmaker[AsyncSession]

    async def record(self, span: SpanRecord) -> None:
        async with self.sessionmaker() as session:
            session.add(
                TraceSpan(
                    task_id=span.task_id,
                    kind=span.kind,
                    name=span.name,
                    summary=span.summary,
                    cost_usd=span.cost_usd,
                    outcome=span.outcome,
                    ts=span.ts,
                )
            )
            await session.commit()
