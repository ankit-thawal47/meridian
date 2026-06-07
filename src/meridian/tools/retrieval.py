"""Top-k tool selector for large registries (Property 1 at scale).

Below RETRIEVAL_THRESHOLD tools we eager-load everything. Above it we show only
the top-k most relevant tools per turn, scored by keyword overlap between the
query and each tool's description — no embeddings needed for the MVP.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

RETRIEVAL_THRESHOLD = 20  # tools; below this, eager-load all
TOP_K = 12

_WORD = re.compile(r"[a-z0-9_]+")


def _tokens(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def _describe(tool: Any) -> str:
    # Real SDK tools carry their text in ``description``; test doubles use ``__doc__``.
    parts = [
        str(getattr(tool, "name", "")),
        str(getattr(tool, "description", "") or ""),
        str(getattr(tool, "__doc__", "") or ""),
    ]
    return " ".join(parts)


def select_tools(all_tools: list[Any], query: str, k: int = TOP_K) -> list[Any]:
    """Return the k most relevant tools for query via keyword overlap."""
    if len(all_tools) <= RETRIEVAL_THRESHOLD:
        return all_tools
    query_terms = set(_tokens(query))
    if not query_terms:
        return all_tools[:k]
    scored: list[tuple[int, int, Any]] = []
    for idx, tool in enumerate(all_tools):
        desc_terms = _tokens(_describe(tool))
        score = sum(1 for t in desc_terms if t in query_terms)
        scored.append((-score, idx, tool))  # negative score → descending, stable by idx
    scored.sort()
    return [tool for _, _, tool in scored[:k]]


def count_guard(tools: list[Any], threshold: int = RETRIEVAL_THRESHOLD) -> None:
    """Warn when the eager-loaded count exceeds the threshold (selection risk)."""
    if len(tools) > threshold:
        logger.warning(
            "tool registry has %d tools (> %d); enable top-k retrieval to "
            "preserve selection quality",
            len(tools),
            threshold,
        )
