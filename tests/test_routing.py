from __future__ import annotations

import asyncio
from types import SimpleNamespace

from meridian.agent.routing import route_model
from meridian.config import Settings
from meridian.observability.tracing import InMemoryTraceSink, SpanRecord
from meridian.worker import orchestrator

from .conftest import make_state


def _settings() -> Settings:
    return Settings(model="frontier-x", model_fast="fast-x")


def test_mechanical_tool_gets_fast_model() -> None:
    assert route_model("repo_read", _settings()) == "fast-x"


def test_reasoning_tool_gets_frontier_model() -> None:
    assert route_model("edit_apply", _settings()) == "frontier-x"


def test_span_includes_model_attribute() -> None:
    st = make_state()
    sink = InMemoryTraceSink()
    block = SimpleNamespace(name="repo_read", input={"path": "a"})
    msg = SimpleNamespace(content=[block])
    asyncio.run(orchestrator._handle_message(st, msg, sink, _settings()))
    assert sink.spans[0].attributes["gen_ai.request.model"] == "fast-x"


def test_span_has_duration_ms_field() -> None:
    span = SpanRecord(task_id="t", kind="tool_call", name="repo_read")
    assert span.duration_ms == 0.0
