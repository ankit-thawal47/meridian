"""Issue-text quarantine (Property 2 / Security W1).

Untrusted issue content is wrapped in explicit delimiters before it enters the
agent prompt. The model is instructed (via SYSTEM_PROMPT) that everything between
the markers is DATA to act on, never instructions to follow — CaMeL dual-channel
pattern (Research VI.1, VI.3).
"""

from __future__ import annotations

ISSUE_START = "===ISSUE_CONTENT_START==="
ISSUE_END = "===ISSUE_CONTENT_END==="


def wrap_issue_text(raw: str) -> str:
    return f"{ISSUE_START}\n{raw}\n{ISSUE_END}"
