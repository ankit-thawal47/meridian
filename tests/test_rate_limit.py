"""Tests for the async rate limiter (research §VIII.2).

Covers: concurrency cap via semaphore, Retry-After honouring (wait before the
next call), and the 429 → record_retry_after path in _create_github_pr.
"""
from __future__ import annotations

import asyncio
import time
from unittest import mock

import pytest

from meridian.reliability import rate_limit as rl


def test_record_and_wait_for_retry_after() -> None:
    rl.record_retry_after("unit_res", 0.2)

    async def go() -> float:
        t0 = time.monotonic()
        await rl.wait_for_resource("unit_res")
        return time.monotonic() - t0

    waited = asyncio.run(go())
    assert waited >= 0.18  # honoured the recorded delay


def test_no_wait_when_no_retry_after() -> None:
    async def go() -> float:
        t0 = time.monotonic()
        await rl.wait_for_resource("never_limited_res")
        return time.monotonic() - t0

    assert asyncio.run(go()) < 0.05


def test_semaphore_caps_concurrency() -> None:
    active = 0
    peak = 0

    async def worker() -> None:
        nonlocal active, peak
        async with rl.RateLimitedClient("cap_res", concurrency=2):
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.03)
            active -= 1

    async def go() -> None:
        await asyncio.gather(*[worker() for _ in range(6)])

    asyncio.run(go())
    assert peak <= 2  # never more than the configured concurrency


def test_github_pr_429_records_retry_after() -> None:
    from meridian.tools import vcs_ops
    from meridian.tools.schemas import PRDraft

    resp = mock.Mock()
    resp.status_code = 429
    resp.headers = {"Retry-After": "7"}

    client = mock.AsyncMock()
    client.post.return_value = resp
    client.__aenter__.return_value = client
    client.__aexit__.return_value = None

    draft = PRDraft(title="t", body="b", branch="feat", diff_stat="")

    with (
        mock.patch("httpx.AsyncClient", return_value=client),
        mock.patch.object(rl, "record_retry_after") as rec,
    ):
        with pytest.raises(RuntimeError, match="rate limited"):
            asyncio.run(vcs_ops._create_github_pr("tok", "o/r", draft, "main"))

    rec.assert_called_once_with("github_api", 7.0)
