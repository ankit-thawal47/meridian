"""Token budget regions and enforcement (Property 3).

Regions: system, repo_map, task_state, recent_outputs. Each region has a
ceiling; the total stays within TOTAL_BUDGET so the context window can never
grow unbounded across a long horizon.
"""

from __future__ import annotations

REGION_CEILINGS = {
    "system": 2_000,
    "repo_map": 8_000,
    "task_state": 6_000,
    "recent_outputs": 10_000,
}
TOTAL_BUDGET = 30_000  # conservative; override via env


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token."""
    return max(1, len(text) // 4)


class RegionBudget:
    """Tracks how many tokens each region has consumed."""

    def __init__(self, ceilings: dict[str, int] | None = None) -> None:
        self.ceilings = dict(ceilings if ceilings is not None else REGION_CEILINGS)
        self._used: dict[str, int] = {region: 0 for region in self.ceilings}

    def allocate(self, region: str, text: str) -> str:
        """Truncate text so it fits within the region ceiling; record usage."""
        ceiling = self.ceilings.get(region, 0)
        if estimate_tokens(text) <= ceiling:
            self._used[region] = estimate_tokens(text)
            return text
        marker = "\n…[truncated]"
        keep = max(0, ceiling * 4 - len(marker))
        truncated = text[:keep] + marker
        self._used[region] = estimate_tokens(truncated)
        return truncated

    def remaining(self, region: str) -> int:
        return self.ceilings.get(region, 0) - self._used.get(region, 0)

    def total_used(self) -> int:
        return sum(self._used.values())

    def within_budget(self) -> bool:
        return self.total_used() <= TOTAL_BUDGET
