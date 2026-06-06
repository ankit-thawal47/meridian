"""Pure tool operations — no SDK import, so they are directly unit-testable.

Each ``op_*`` takes (ctx, args) and returns the MCP content dict. ``core_tools``
wraps these in @tool closures for the SDK. Keeping the logic here means the
confinement, edit, and test-execution behavior can be tested without the agent
runtime (Property 4 — reproducible, verifiable scaffolding).
"""

from __future__ import annotations

import asyncio
import shutil
from typing import Any

from meridian.tools.context import ToolContext
from meridian.tools.schemas import (
    EditResult,
    FileContent,
    RepoSearchHit,
    RepoSlice,
    TestResult,
    ToolOutcome,
    ToolStatus,
)

MAX_FILE_CHARS = 60_000


def ok(summary: str, payload: dict[str, Any]) -> dict[str, Any]:
    outcome = ToolOutcome(status=ToolStatus.ok, summary=summary, payload=payload)
    return {"content": [{"type": "text", "text": outcome.model_dump_json()}]}


def err(summary: str, *, deterministic: bool) -> dict[str, Any]:
    outcome = ToolOutcome(status=ToolStatus.error, deterministic=deterministic, summary=summary)
    return {"content": [{"type": "text", "text": outcome.model_dump_json()}]}


async def op_repo_read(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    try:
        p = ctx.safe_path(args["path"])
    except ValueError as e:
        return err(str(e), deterministic=True)
    if not p.is_file():
        return err(f"not a file: {args['path']}", deterministic=True)
    text = p.read_text(errors="replace")
    fc = FileContent(
        path=args["path"], content=text[:MAX_FILE_CHARS], truncated=len(text) > MAX_FILE_CHARS
    )
    return ok(f"read {args['path']} ({len(text)} chars)", fc.model_dump())


async def op_repo_search(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    query = args["query"]
    max_results = int(args.get("max_results") or 50)
    hits: list[RepoSearchHit] = []
    rg = shutil.which("rg")
    if rg:
        proc = await asyncio.create_subprocess_exec(
            rg,
            "-n",
            "--no-heading",
            "-m",
            str(max_results),
            query,
            cwd=str(ctx.workspace),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await proc.communicate()
        for line in out.decode(errors="replace").splitlines()[:max_results]:
            parts = line.split(":", 2)
            if len(parts) == 3:
                hits.append(
                    RepoSearchHit(path=parts[0], line=int(parts[1]), snippet=parts[2][:200])
                )
    else:
        for path in ctx.workspace.rglob("*"):
            if not path.is_file() or ".meridian" in path.parts or ".git" in path.parts:
                continue
            try:
                for i, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
                    if query in line:
                        hits.append(
                            RepoSearchHit(
                                path=str(path.relative_to(ctx.workspace)),
                                line=i,
                                snippet=line[:200],
                            )
                        )
                        if len(hits) >= max_results:
                            break
            except (OSError, UnicodeDecodeError):
                continue
            if len(hits) >= max_results:
                break
    slice_ = RepoSlice(files=sorted({h.path for h in hits}), hits=hits)
    return ok(f"{len(hits)} hits for '{query}'", slice_.model_dump())


async def op_edit_apply(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    try:
        p = ctx.safe_path(args["path"])
    except ValueError as e:
        return err(str(e), deterministic=True)
    if not p.is_file():
        return err(f"not a file: {args['path']}", deterministic=True)
    text = p.read_text()
    old = args["old_string"]
    count = text.count(old)
    if count == 0:
        return err("old_string not found", deterministic=True)
    if count > 1:
        return err(f"old_string not unique ({count} matches)", deterministic=True)
    p.write_text(text.replace(old, args["new_string"], 1))
    ctx.state.touch_file(args["path"])
    return ok(f"edited {args['path']}", EditResult(path=args["path"], applied=True).model_dump())


async def op_exec_test(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    command = args.get("command") or "pytest -q"
    proc = await asyncio.create_subprocess_shell(
        command,
        cwd=str(ctx.workspace),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    out, _ = await proc.communicate()
    text = out.decode(errors="replace")
    ref = ctx.store_blob(text)
    ctx.state.record_test(command)
    tail = "\n".join(text.splitlines()[-15:])
    passed = proc.returncode == 0
    test_result = TestResult(
        passed=passed,
        summary=tail[:1000],
        failures=[] if passed else [tail[:1000]],
        stdout_ref=ref,
        exit_code=proc.returncode,
    )
    return ok(f"`{command}` -> {'PASS' if passed else 'FAIL'}", test_result.model_dump())


async def op_state_update(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    changed: list[str] = []
    if args.get("plan"):
        ctx.state.set_plan([str(s) for s in args["plan"]])
        changed.append(f"plan={len(ctx.state.plan)} steps")
    if args.get("mark_done") is not None:
        idx = int(args["mark_done"])
        if 0 <= idx < len(ctx.state.plan):
            ctx.state.plan[idx].done = True
            changed.append(f"step {idx} done")
    if args.get("finding"):
        ctx.state.record_finding("state_update", str(args["finding"]))
        changed.append("finding recorded")
    return ok("; ".join(changed) or "no-op", {"state": ctx.state.render_context()})
