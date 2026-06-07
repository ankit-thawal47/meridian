"""VCS and review tool operations (W7 — Composable Tool Chains).

op_vcs_branch   — create a feature branch in the workspace
op_vcs_commit   — stage all changes and commit with a message
op_vcs_open_pr  — push branch + open GitHub PR (degrades when no token)
op_review_lint  — run ruff (if available) and return lint summary
op_review_spawn_security — spawn SecuritySubagent, return typed SecurityReport

All functions follow the (ctx, args) → MCP content-dict pattern from core_ops
so they are directly unit-testable without the agent runtime.
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
from typing import Any

from meridian.tools.context import ToolContext
from meridian.tools.core_ops import err, ok
from meridian.tools.schemas import PRDraft, SecurityReport, ToolOutcome, ToolStatus


async def _git(args: list[str], cwd: str) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, stderr_ = await proc.communicate()
    combined = (out + stderr_).decode(errors="replace").strip()
    return proc.returncode or 0, combined


async def op_vcs_branch(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    branch = str(args.get("branch") or "").strip()
    if not branch:
        return err("branch name is required", deterministic=True)
    rc, msg = await _git(["checkout", "-b", branch], cwd=str(ctx.workspace))
    if rc != 0:
        return err(f"git checkout -b failed: {msg[:300]}", deterministic=True)
    ctx.state.record_finding("vcs_branch", f"created branch {branch}")
    return ok(f"created branch {branch}", {"branch": branch})


async def op_vcs_commit(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    message = str(args.get("message") or "").strip()
    if not message:
        return err("commit message is required", deterministic=True)

    # Stage all changes.
    rc_add, msg_add = await _git(["add", "-A"], cwd=str(ctx.workspace))
    if rc_add != 0:
        return err(f"git add failed: {msg_add[:300]}", deterministic=True)

    # Check if there is anything to commit.
    rc_status, status_out = await _git(["status", "--porcelain"], cwd=str(ctx.workspace))
    if rc_status == 0 and not status_out.strip():
        return err("nothing to commit — working tree is clean", deterministic=True)

    rc_commit, msg_commit = await _git(["commit", "-m", message], cwd=str(ctx.workspace))
    if rc_commit != 0:
        return err(f"git commit failed: {msg_commit[:300]}", deterministic=True)

    ctx.state.record_finding("vcs_commit", f"committed: {message[:80]}")
    return ok(f"committed: {message[:80]}", {"message": message})


async def op_vcs_open_pr(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    title = str(args.get("title") or "").strip()
    body = str(args.get("body") or "").strip()
    base = str(args.get("base") or "main").strip()
    blocking = args.get("blocking")
    # Accept both bool True and string "true" from model output.
    if blocking is True or str(blocking).lower() == "true":
        return err(
            "PR blocked: a high/critical security finding was reported — resolve it first",
            deterministic=True,
        )

    if not title:
        return err("title is required", deterministic=True)

    # Determine current branch.
    rc_br, branch = await _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=str(ctx.workspace))
    if rc_br != 0:
        branch = "unknown"
    branch = branch.strip()

    # Collect diff stat for the PR body.
    rc_diff, diff_stat = await _git(
        ["diff", "--stat", f"origin/{base}...HEAD"],
        cwd=str(ctx.workspace),
    )
    if rc_diff != 0:
        diff_stat = "(diff stat unavailable)"

    draft = PRDraft(title=title, body=body, branch=branch, diff_stat=diff_stat[:2000])

    # Push if a remote and github_token are configured.
    from meridian.config import get_settings

    s = get_settings()
    github_token = getattr(s, "github_token", "")
    if github_token:
        rc_push, push_msg = await _git(
            ["push", "-u", "origin", branch], cwd=str(ctx.workspace)
        )
        if rc_push != 0:
            return err(f"git push failed: {push_msg[:300]}", deterministic=False)

        # Derive owner/repo from remote URL.
        rc_remote, remote_url = await _git(
            ["remote", "get-url", "origin"], cwd=str(ctx.workspace)
        )
        if rc_remote == 0:
            m = re.search(r"github\.com[:/]([^/]+/[^/.]+)", remote_url)
            if m:
                owner_repo = m.group(1)
                await _create_github_pr(github_token, owner_repo, draft, base)

    ctx.state.record_finding("vcs_open_pr", f"PR ready: {title}")
    return ok(f"PR ready: {title}", draft.model_dump())


async def _create_github_pr(
    token: str, owner_repo: str, draft: PRDraft, base: str
) -> None:
    import httpx

    from meridian.reliability.rate_limit import RateLimitedClient, record_retry_after

    # Cap concurrent GitHub calls and honour any prior Retry-After (research §VIII.2).
    async with RateLimitedClient("github_api", concurrency=3):
        async with httpx.AsyncClient(
            base_url="https://api.github.com",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
            timeout=30,
        ) as client:
            resp = await client.post(
                f"/repos/{owner_repo}/pulls",
                json={
                    "title": draft.title,
                    "body": draft.body,
                    "head": draft.branch,
                    "base": base,
                },
            )

    if resp.status_code == 429:
        # Honour the server's Retry-After rather than guessing a sleep duration.
        retry_after = resp.headers.get("Retry-After", "60")
        try:
            seconds = float(int(retry_after))
        except (TypeError, ValueError):
            seconds = 60.0
        record_retry_after("github_api", seconds)
        raise RuntimeError(f"github rate limited (429); retry after {seconds:.0f}s")


async def op_review_lint(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    ruff = shutil.which("ruff")
    if not ruff:
        return ok("ruff not found — lint skipped", {"passed": True, "output": ""})

    target = str(args.get("path") or ".").strip() or "."
    proc = await asyncio.create_subprocess_exec(
        ruff,
        "check",
        target,
        cwd=str(ctx.workspace),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, _ = await proc.communicate()
    text = out.decode(errors="replace").strip()
    passed = proc.returncode == 0
    summary = (text[:1000] if text else "no issues") if not passed else "no issues"
    finding = "lint passed" if passed else f"lint issues: {summary[:80]}"
    ctx.state.record_finding("review_lint", finding)
    return ok(f"lint {'passed' if passed else 'failed'}", {"passed": passed, "output": summary})


def _parse_security_report(text: str) -> SecurityReport:
    """Extract a SecurityReport from the last JSON object in text."""
    # Try to find the last JSON object in the text.
    matches = list(re.finditer(r"\{[^{}]*\}", text, re.DOTALL))
    # Walk backwards for the richest match.
    for m in reversed(matches):
        try:
            data = json.loads(m.group())
            return SecurityReport.model_validate(data)
        except Exception:
            continue
    # Also try the whole text.
    try:
        return SecurityReport.model_validate(json.loads(text))
    except Exception:
        pass
    return SecurityReport()


async def op_review_spawn_security(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    focus = str(args.get("focus") or "Review all modified files for security issues.").strip()

    try:
        from claude_agent_sdk import query as sdk_query

        from meridian.agent.subagents import build_security_subagent_options

        sub_options = build_security_subagent_options(ctx)
        result_text: str | None = None

        async for msg in sdk_query(prompt=focus, options=sub_options):
            if hasattr(msg, "result"):
                result_text = str(msg.result or "")

        report = _parse_security_report(result_text or "")
    except Exception as exc:
        outcome = ToolOutcome(
            status=ToolStatus.error,
            deterministic=False,
            summary=f"security subagent failed: {exc!r}",
        )
        return {"content": [{"type": "text", "text": outcome.model_dump_json()}]}

    ctx.state.record_finding(
        "review_spawn_security",
        f"max_severity={report.max_severity} blocking={report.blocking}"
        f" findings={len(report.findings)}",
    )
    return ok(
        f"security review: max_severity={report.max_severity} blocking={report.blocking}",
        report.model_dump(),
    )
