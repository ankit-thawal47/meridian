"""Model routing (Property 4 — cost-aware execution).

Mechanical tools (read/search/lint) run on the fast, cheap model; everything
that requires reasoning runs on the frontier model.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from meridian.config import Settings

MECHANICAL_TOOLS = {"repo_read", "repo_search", "review_lint"}


def route_model(tool_name: str, settings: Settings) -> str:
    """Return the model to use for a given tool call."""
    if tool_name in MECHANICAL_TOOLS:
        return settings.model_fast
    return settings.model
