"""arq worker: runs one Meridian task to a terminal status.

One job == one task == one agent run (the SDK loop). The job is the *job*-level
unit (arq handles its own retries/scheduling); the agent-step retry logic lives
inside the loop and is a separate concern (Property 4).
"""

from __future__ import annotations

from typing import Any

from arq.connections import RedisSettings

from meridian.agent.task_state import TaskState, TaskStatus
from meridian.config import get_settings
from meridian.observability.tracing import TraceSink
from meridian.persistence.db import init_db, session_factory
from meridian.persistence.repository import DbTraceSink, get_task, save_state
from meridian.repo.workspace import prepare_workspace
from meridian.tools.context import ToolContext
from meridian.worker.orchestrator import run_task


async def run_meridian_task(ctx: dict[str, Any], task_id: str) -> str:
    sm = session_factory()
    async with sm() as session:
        task = await get_task(session, task_id)
        if task is None:
            raise RuntimeError(f"task not found: {task_id}")
        repo, issue_ref, goal = task.repo, task.issue_ref, task.goal

    workspace = await prepare_workspace(task_id, repo)
    state = TaskState(
        task_id=task_id, repo=repo, issue_ref=issue_ref, goal=goal, status=TaskStatus.running
    )
    tool_ctx = ToolContext(workspace=workspace, state=state)

    # Build sink: Postgres always; Azure App Insights when configured.
    db_sink = DbTraceSink(sessionmaker=sm)
    s = get_settings()
    if s.azure_application_insights_connection_string:
        from meridian.observability.azure_sink import AzureAppInsightsSink

        class _FanOutSink:
            async def record(self, span: TraceSink) -> None:  # type: ignore[override]
                await db_sink.record(span)  # type: ignore[arg-type]
                await azure_sink.record(span)  # type: ignore[arg-type]

        azure_sink = AzureAppInsightsSink(s.azure_application_insights_connection_string)
        sink: TraceSink = _FanOutSink()  # type: ignore[assignment]
    else:
        sink = db_sink

    result = await run_task(tool_ctx, sink=sink)

    async with sm() as session:
        await save_state(session, result.state)
    return result.status.value


async def _on_startup(ctx: dict[str, Any]) -> None:
    await init_db()


class WorkerSettings:
    functions = [run_meridian_task]
    on_startup = _on_startup
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 10  # Phase 0 concurrency; Phase 4 makes this configurable/autoscaled
