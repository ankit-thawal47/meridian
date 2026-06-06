from __future__ import annotations

import logging

from meridian.tools.retrieval import TOP_K, count_guard, select_tools


class FakeTool:
    def __init__(self, name: str, doc: str) -> None:
        self.name = name
        self.__doc__ = doc


def _make_tools(n: int) -> list[FakeTool]:
    return [FakeTool(f"tool_{i}", f"does thing number {i}") for i in range(n)]


def test_select_all_when_under_threshold() -> None:
    tools = _make_tools(20)
    assert select_tools(tools, "anything") == tools


def test_select_topk_when_over_threshold() -> None:
    tools = _make_tools(25)
    selected = select_tools(tools, "thing number 3")
    assert len(selected) == TOP_K


def test_relevant_tool_ranked_first() -> None:
    tools = _make_tools(25)
    tools.append(FakeTool("auth_fix", "repair the authentication login token flow"))
    selected = select_tools(tools, "authentication login token", k=1)
    assert selected[0].name == "auth_fix"


def test_count_guard_warns_over_threshold(caplog) -> None:
    tools = _make_tools(25)
    with caplog.at_level(logging.WARNING):
        count_guard(tools)
    assert any("tool registry" in r.message for r in caplog.records)
