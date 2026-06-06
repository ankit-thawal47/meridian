"""Tracing primitives (Property 4 — every decision observable).

A SpanRecord is emitted for each model turn and tool call. A TraceSink persists
them; the orchestrator depends only on the protocol, so tests use an in-memory
sink and production uses the Postgres-backed one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class SpanRecord:
    task_id: str
    kind: str  # "model_turn" | "tool_call" | "result"
    name: str
    summary: str = ""
    cost_usd: float = 0.0
    outcome: str = "ok"
    ts: datetime = field(default_factory=_now)


class TraceSink(Protocol):
    async def record(self, span: SpanRecord) -> None: ...


@dataclass
class InMemoryTraceSink:
    spans: list[SpanRecord] = field(default_factory=list)

    async def record(self, span: SpanRecord) -> None:
        self.spans.append(span)
