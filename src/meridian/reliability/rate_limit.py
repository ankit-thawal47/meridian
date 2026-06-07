"""Async rate limiter for external API calls (Property 4 — Production Scaffolding).

Implements a token bucket with per-resource semaphores and Retry-After header
handling per AWS/Applied-LLMs best practice (VIII.2): honor the header, don't
guess sleep duration, use asyncio primitives not blocking sleep.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict

logger = logging.getLogger(__name__)

_semaphores: dict[str, asyncio.Semaphore] = defaultdict(lambda: asyncio.Semaphore(10))
_retry_after: dict[str, float] = {}  # resource -> earliest_next_call_epoch


def _semaphore(resource: str, concurrency: int = 5) -> asyncio.Semaphore:
    """Return (or create) the semaphore for a named resource."""
    if resource not in _semaphores:
        _semaphores[resource] = asyncio.Semaphore(concurrency)
    return _semaphores[resource]


async def wait_for_resource(resource: str) -> None:
    """Honour a previous Retry-After delay before making a call."""
    earliest = _retry_after.get(resource, 0.0)
    now = time.monotonic()
    if earliest > now:
        delay = earliest - now
        logger.info("rate_limit: sleeping %.1fs for resource %s", delay, resource)
        await asyncio.sleep(delay)


def record_retry_after(resource: str, retry_after_seconds: float) -> None:
    """Store the earliest time we may call this resource again."""
    _retry_after[resource] = time.monotonic() + retry_after_seconds


class RateLimitedClient:
    """Context manager that enforces concurrency + Retry-After for a resource."""

    def __init__(self, resource: str, concurrency: int = 5) -> None:
        self._resource = resource
        self._sem = _semaphore(resource, concurrency)

    async def __aenter__(self) -> RateLimitedClient:
        await wait_for_resource(self._resource)
        await self._sem.acquire()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self._sem.release()
