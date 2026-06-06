"""Retry classification + Full Jitter backoff (Property 4 — W2).

Two concerns:
1. classify_outcome / classify_exception — split failures into Transient (retry)
   vs Terminal (feed back to model, never retry). Research VIII.1-2.
2. full_jitter — AWS Full Jitter algorithm prevents synchronized retry storms.
   sleep = random(0, min(cap, base * 2^attempt)). Research VIII.1.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import StrEnum

from claude_agent_sdk import CLIConnectionError, CLINotFoundError

from meridian.tools.schemas import ToolOutcome, ToolStatus


class FailureKind(StrEnum):
    transient = "transient"
    terminal = "terminal"


def classify_outcome(outcome: ToolOutcome) -> FailureKind:
    if outcome.status == ToolStatus.ok:
        return FailureKind.terminal  # not a failure; caller should not retry
    return FailureKind.terminal if outcome.deterministic else FailureKind.transient


def classify_exception(exc: BaseException) -> FailureKind:
    # CLINotFoundError extends CLIConnectionError — check the subclass first.
    # CLI not found is a configuration problem — terminal.
    if isinstance(exc, CLINotFoundError):
        return FailureKind.terminal
    # Other SDK connection errors are transient (process restart, pipe break).
    if isinstance(exc, CLIConnectionError):
        return FailureKind.transient
    # OSError / TimeoutError from subprocess are transient.
    if isinstance(exc, (TimeoutError, OSError)):
        return FailureKind.transient
    # Anything else (RuntimeError from the SDK, unexpected exceptions) — terminal
    # so we don't spin forever on deterministic bugs.
    return FailureKind.terminal


def full_jitter(attempt: int, base: float = 1.0, cap: float = 30.0) -> float:
    """AWS Full Jitter: random(0, min(cap, base * 2**attempt))."""
    return random.uniform(0, min(cap, base * (2**attempt)))


@dataclass
class RetryPolicy:
    max_attempts: int = 3
    base_s: float = 1.0
    cap_s: float = 30.0
