"""Pure GitHub-issue operations (issue_* namespace).

Each ``op_issue_*`` takes (ctx, args) and returns an MCP content dict, sharing the
``ok``/``err`` envelope from core_ops. ``op_issue_describe`` and ``op_issue_related``
are local (no network). The mutating ops (comment/label/close) call the GitHub
Issues API and are wrapped in ``RateLimitedClient`` so concurrency is capped and
Retry-After is honoured (research §VIII.2).
"""

from __future__ import annotations

import re
from typing import Any

from meridian.reliability.rate_limit import RateLimitedClient, record_retry_after
from meridian.tools.context import ToolContext
from meridian.tools.core_ops import _run, _skip_path, err, ok

_GITHUB_RESOURCE = "github_api"
_WORD_RX = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")


def _state_attr(ctx: ToolContext, *names: str) -> str:
    for n in names:
        v = getattr(ctx.state, n, None)
        if v:
            return str(v)
    return ""


async def _owner_repo(ctx: ToolContext) -> str | None:
    rc, out = await _run("git", "remote", "get-url", "origin", cwd=str(ctx.workspace))
    if rc == 0:
        m = re.search(r"github\.com[:/]([^/]+/[^/.]+)", out)
        if m:
            return m.group(1)
    repo = _state_attr(ctx, "repo")
    return repo if "/" in repo else None


def _issue_number(ctx: ToolContext, args: dict[str, Any]) -> str | None:
    if args.get("number"):
        return str(args["number"])
    ref = _state_attr(ctx, "issue_url", "issue_ref")
    m = re.search(r"(\d+)", ref)
    return m.group(1) if m else None


def _github_token() -> str:
    from meridian.config import get_settings

    return getattr(get_settings(), "github_token", "") or ""


async def _github(method: str, path: str, json_body: dict[str, Any] | None) -> tuple[int, str]:
    """Make a rate-limited GitHub API call; honour Retry-After on 429."""
    import httpx

    token = _github_token()
    async with RateLimitedClient(_GITHUB_RESOURCE, concurrency=3):
        async with httpx.AsyncClient(
            base_url="https://api.github.com",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
            timeout=30,
        ) as client:
            resp = await client.request(method, path, json=json_body)
    if resp.status_code == 429:
        retry_after = resp.headers.get("Retry-After", "60")
        try:
            record_retry_after(_GITHUB_RESOURCE, float(int(retry_after)))
        except (TypeError, ValueError):
            record_retry_after(_GITHUB_RESOURCE, 60.0)
    return resp.status_code, resp.text


async def op_issue_describe(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    title = _state_attr(ctx, "issue_title", "goal")
    body = _state_attr(ctx, "issue_body")
    ref = _state_attr(ctx, "issue_url", "issue_ref")
    return ok(f"issue: {title[:60]}",
              {"title": title, "body": body, "ref": ref})


async def op_issue_comment(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    if not _github_token():
        return err("github_token not configured", deterministic=True)
    body = str(args.get("body") or "").strip()
    if not body:
        return err("comment body is required", deterministic=True)
    owner_repo = await _owner_repo(ctx)
    number = _issue_number(ctx, args)
    if not owner_repo or not number:
        return err("could not resolve owner/repo or issue number", deterministic=True)
    status, text = await _github(
        "POST", f"/repos/{owner_repo}/issues/{number}/comments", {"body": body})
    if status >= 400:
        return err(f"github comment failed: {status} {text[:200]}", deterministic=status < 500)
    ctx.state.record_finding("issue_comment", f"commented on #{number}")
    return ok(f"commented on issue #{number}", {"number": number, "status": status})


async def op_issue_label(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    if not _github_token():
        return err("github_token not configured", deterministic=True)
    labels = args.get("labels")
    if not isinstance(labels, list) or not labels:
        return err("labels must be a non-empty list", deterministic=True)
    owner_repo = await _owner_repo(ctx)
    number = _issue_number(ctx, args)
    if not owner_repo or not number:
        return err("could not resolve owner/repo or issue number", deterministic=True)
    status, text = await _github(
        "PATCH", f"/repos/{owner_repo}/issues/{number}",
        {"labels": [str(label) for label in labels]})
    if status >= 400:
        return err(f"github label failed: {status} {text[:200]}", deterministic=status < 500)
    ctx.state.record_finding("issue_label", f"labelled #{number}: {labels}")
    return ok(f"labelled issue #{number}", {"number": number, "labels": labels})


async def op_issue_related(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    title = str(args.get("query") or _state_attr(ctx, "issue_title", "goal"))
    terms = {t.lower() for t in _WORD_RX.findall(title)}
    if not terms:
        return ok("no searchable terms in issue title", {"files": []})
    scored: list[tuple[int, str]] = []
    for path in ctx.workspace.rglob("*"):
        if not path.is_file() or _skip_path(path, ctx.workspace):
            continue
        if path.suffix not in {".py", ".ts", ".js", ".md"}:
            continue
        name = path.stem.lower()
        score = sum(1 for t in terms if t in name)
        try:
            head = path.read_text(errors="replace")[:4000].lower()
            score += sum(1 for t in terms if t in head)
        except (OSError, UnicodeDecodeError):
            pass
        if score:
            scored.append((score, str(path.relative_to(ctx.workspace))))
    scored.sort(key=lambda x: x[0], reverse=True)
    return ok(f"{len(scored)} files related to issue",
              {"files": [p for _, p in scored[:20]]})


async def op_issue_close(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    if not _github_token():
        return err("github_token not configured", deterministic=True)
    owner_repo = await _owner_repo(ctx)
    number = _issue_number(ctx, args)
    if not owner_repo or not number:
        return err("could not resolve owner/repo or issue number", deterministic=True)
    status, text = await _github(
        "PATCH", f"/repos/{owner_repo}/issues/{number}", {"state": "closed"})
    if status >= 400:
        return err(f"github close failed: {status} {text[:200]}", deterministic=status < 500)
    ctx.state.record_finding("issue_close", f"closed #{number}")
    return ok(f"closed issue #{number}", {"number": number, "status": status})
