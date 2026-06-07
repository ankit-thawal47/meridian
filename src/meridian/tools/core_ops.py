"""Pure tool operations — no SDK import, so they are directly unit-testable.

Each ``op_*`` takes (ctx, args) and returns the MCP content dict. ``core_tools``
wraps these in @tool closures for the SDK. Keeping the logic here means the
confinement, edit, and test-execution behavior can be tested without the agent
runtime (Property 4 — reproducible, verifiable scaffolding).
"""

from __future__ import annotations

import ast
import asyncio
import hashlib
import json
import shutil
from datetime import UTC, datetime
from typing import Any

from meridian.tools.context import ToolContext
from meridian.tools.schemas import (
    CommitEntry,
    DirListing,
    EditResult,
    FileContent,
    FileListEntry,
    MetricRecord,
    OutlineItem,
    RepoSearchHit,
    RepoSlice,
    TestResult,
    ToolOutcome,
    ToolStatus,
)

MAX_FILE_CHARS = 60_000

# Patterns that indicate an attempt to chain/inject extra shell commands.
_SHELL_INJECTION = (";", "&&", "||", "|", "`", "$(", ">", "<", "\n")


async def _run(
    program: str, *cli_args: str, cwd: str, timeout: float = 60.0
) -> tuple[int, str]:
    """Run a program (no shell) and return (exit_code, combined_output)."""
    proc = await asyncio.create_subprocess_exec(
        program,
        *cli_args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        return 124, f"timeout after {timeout:.0f}s"
    return proc.returncode or 0, out.decode(errors="replace")


def _skip_path(path: Any, workspace: Any) -> bool:
    parts = path.parts
    return ".meridian" in parts or ".git" in parts or "__pycache__" in parts


def _call_key(tool: str, args: dict[str, Any]) -> str:
    """Short digest used as the idempotency cache key."""
    payload = json.dumps({"tool": tool, "args": args}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


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
    key = _call_key("edit_apply", args)
    cached = ctx.get_cached(key)
    if cached is not None:
        return cached

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
    result = ok(f"edited {args['path']}", EditResult(path=args["path"], applied=True).model_dump())
    ctx.set_cached(key, result)
    return result


async def op_exec_test(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    command = args.get("command") or "pytest -q"
    key = _call_key("exec_test", {"command": command})
    cached = ctx.get_cached(key)
    if cached is not None:
        return cached

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
    result = ok(f"`{command}` -> {'PASS' if passed else 'FAIL'}", test_result.model_dump())
    ctx.set_cached(key, result)
    return result


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


# === repo.* (extended) =====================================================
async def op_repo_list(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    try:
        p = ctx.safe_path(args.get("path") or ".")
    except ValueError as e:
        return err(str(e), deterministic=True)
    if not p.is_dir():
        return err(f"not a directory: {args.get('path')}", deterministic=True)
    recursive = bool(args.get("recursive"))
    entries: list[FileListEntry] = []
    iterator = p.rglob("*") if recursive else p.iterdir()
    for child in iterator:
        if _skip_path(child, ctx.workspace):
            continue
        try:
            size = child.stat().st_size if child.is_file() else 0
        except OSError:
            size = 0
        entries.append(
            FileListEntry(
                name=str(child.relative_to(p)),
                type="dir" if child.is_dir() else "file",
                size=size,
            )
        )
        if len(entries) >= 500:
            break
    entries.sort(key=lambda e: (e.type != "dir", e.name))
    listing = DirListing(path=args.get("path") or ".", entries=entries)
    return ok(f"{len(entries)} entries in {args.get('path') or '.'}", listing.model_dump())


async def op_repo_glob(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    pattern = str(args.get("pattern") or "").strip()
    if not pattern:
        return err("pattern is required", deterministic=True)
    files = [
        str(m.relative_to(ctx.workspace))
        for m in ctx.workspace.glob(pattern)
        if m.is_file() and not _skip_path(m, ctx.workspace)
    ]
    files.sort()
    return ok(f"{len(files)} files match '{pattern}'", {"files": files[:500]})


async def op_repo_stat(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    try:
        p = ctx.safe_path(args["path"])
    except ValueError as e:
        return err(str(e), deterministic=True)
    if not p.exists():
        return err(f"path not found: {args['path']}", deterministic=True)
    st = p.stat()
    payload = {
        "path": args["path"],
        "size_bytes": st.st_size,
        "mtime_iso": datetime.fromtimestamp(st.st_mtime, UTC).isoformat(),
        "is_file": p.is_file(),
        "is_dir": p.is_dir(),
    }
    return ok(f"stat {args['path']}", payload)


async def op_repo_diff(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    git_args = ["diff", "--cached"] if args.get("staged") else ["diff", "HEAD"]
    rc, out = await _run("git", *git_args, cwd=str(ctx.workspace))
    if rc not in (0,):
        return err(f"git diff failed: {out[:300]}", deterministic=True)
    truncated = len(out) > 8000
    return ok(
        f"diff ({'staged' if args.get('staged') else 'HEAD'})",
        {"diff": out[:8000], "truncated": truncated},
    )


async def op_repo_log(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    n = int(args.get("n") or 10)
    rc, out = await _run("git", "log", f"-{n}", "--oneline", cwd=str(ctx.workspace))
    if rc != 0:
        return err(f"git log failed: {out[:300]}", deterministic=True)
    commits: list[CommitEntry] = []
    for line in out.splitlines():
        parts = line.split(" ", 1)
        if len(parts) == 2:
            commits.append(CommitEntry(hash=parts[0], message=parts[1]))
        elif parts and parts[0]:
            commits.append(CommitEntry(hash=parts[0], message=""))
    return ok(f"{len(commits)} commits", {"commits": [c.model_dump() for c in commits]})


async def op_repo_blame(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    try:
        p = ctx.safe_path(args["path"])
    except ValueError as e:
        return err(str(e), deterministic=True)
    if not p.is_file():
        return err(f"not a file: {args['path']}", deterministic=True)
    start = int(args.get("start") or 1)
    end = int(args.get("end") or start)
    rc, out = await _run(
        "git", "blame", "--porcelain", args["path"], "-L", f"{start},{end}",
        cwd=str(ctx.workspace),
    )
    if rc != 0:
        return err(f"git blame failed: {out[:300]}", deterministic=True)
    lines: list[dict[str, Any]] = []
    commit = author = ""
    lineno = start
    for raw in out.splitlines():
        if raw and not raw.startswith("\t") and len(raw.split()[0]) == 40:
            commit = raw.split()[0]
        elif raw.startswith("author "):
            author = raw[len("author "):]
        elif raw.startswith("\t"):
            lines.append(
                {"line": lineno, "author": author, "commit": commit, "content": raw[1:]}
            )
            lineno += 1
    return ok(f"blame {args['path']} L{start}-{end}", {"lines": lines})


async def op_repo_outline(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    try:
        p = ctx.safe_path(args["path"])
    except ValueError as e:
        return err(str(e), deterministic=True)
    if not p.is_file():
        return err(f"not a file: {args['path']}", deterministic=True)
    try:
        tree = ast.parse(p.read_text(errors="replace"))
    except SyntaxError as e:
        return err(f"could not parse {args['path']}: {e}", deterministic=True)
    items: list[OutlineItem] = []

    def _preview(node: ast.AST) -> str:
        doc = ast.get_docstring(node) or ""
        return doc.strip().splitlines()[0][:80] if doc.strip() else ""

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            items.append(
                OutlineItem(type="class", name=node.name, line=node.lineno,
                            docstring_preview=_preview(node))
            )
            for sub in node.body:
                if isinstance(sub, ast.FunctionDef | ast.AsyncFunctionDef):
                    items.append(
                        OutlineItem(type="method", name=f"{node.name}.{sub.name}",
                                    line=sub.lineno, docstring_preview=_preview(sub))
                    )
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            items.append(
                OutlineItem(type="function", name=node.name, line=node.lineno,
                            docstring_preview=_preview(node))
            )
    return ok(f"{len(items)} symbols in {args['path']}",
              {"outline": [i.model_dump() for i in items]})


# === edit.* (extended) =====================================================
async def op_edit_create(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    try:
        p = ctx.safe_path(args["path"])
    except ValueError as e:
        return err(str(e), deterministic=True)
    if p.exists():
        return err(f"file already exists: {args['path']}", deterministic=True)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(str(args.get("content") or ""))
    ctx.state.touch_file(args["path"])
    return ok(f"created {args['path']}",
              EditResult(path=args["path"], applied=True).model_dump())


async def op_edit_delete(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    try:
        p = ctx.safe_path(args["path"])
    except ValueError as e:
        return err(str(e), deterministic=True)
    if not p.is_file():
        return err(f"not a file: {args['path']}", deterministic=True)
    p.unlink()
    ctx.state.touch_file(args["path"])
    return ok(f"deleted {args['path']}",
              EditResult(path=args["path"], applied=True).model_dump())


async def op_edit_rename(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    try:
        src = ctx.safe_path(args["path"])
        dst = ctx.safe_path(args["new_path"])
    except (ValueError, KeyError) as e:
        return err(str(e), deterministic=True)
    if not src.exists():
        return err(f"source not found: {args['path']}", deterministic=True)
    if dst.exists():
        return err(f"destination exists: {args['new_path']}", deterministic=True)
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dst)
    ctx.state.touch_file(args["new_path"])
    return ok(f"renamed {args['path']} -> {args['new_path']}",
              EditResult(path=args["new_path"], applied=True).model_dump())


async def op_edit_insert(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    try:
        p = ctx.safe_path(args["path"])
    except ValueError as e:
        return err(str(e), deterministic=True)
    if not p.is_file():
        return err(f"not a file: {args['path']}", deterministic=True)
    lineno = int(args.get("line") or 1)
    if lineno < 1:
        return err("line must be >= 1 (1-indexed)", deterministic=True)
    text = str(args.get("text") or "")
    lines = p.read_text(errors="replace").splitlines(keepends=True)
    insert_at = min(lineno - 1, len(lines))
    block = text if text.endswith("\n") else text + "\n"
    lines.insert(insert_at, block)
    p.write_text("".join(lines))
    ctx.state.touch_file(args["path"])
    return ok(f"inserted at line {lineno} in {args['path']}",
              EditResult(path=args["path"], applied=True).model_dump())


# === exec.* (extended) =====================================================
async def op_exec_run(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    command = str(args.get("command") or "").strip()
    if not command:
        return err("command is required", deterministic=True)
    if any(tok in command for tok in _SHELL_INJECTION):
        return err(
            "command contains shell metacharacters; pass a single program with args",
            deterministic=True,
        )
    parts = command.split()
    rc, out = await _run(parts[0], *parts[1:], cwd=str(ctx.workspace))
    tail = "\n".join(out.splitlines()[-40:])
    return ok(f"`{command}` -> exit {rc}",
              {"stdout": tail, "stderr": "", "exit_code": rc})


async def op_exec_format(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    target = str(args.get("path") or ".").strip() or "."
    for tool_name, cli in (
        ("ruff", ["format", target]),
        ("black", [target]),
        ("prettier", ["--write", target]),
    ):
        if shutil.which(tool_name):
            rc, out = await _run(tool_name, *cli, cwd=str(ctx.workspace))
            return ok(f"{tool_name} format {'ok' if rc == 0 else 'failed'}",
                      {"passed": rc == 0, "tool": tool_name, "output": out[:1000]})
    return ok("no formatter found — skipped", {"passed": True, "tool": "", "output": ""})


async def op_exec_typecheck(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    target = str(args.get("path") or ".").strip() or "."
    for tool_name in ("mypy", "pyright"):
        if shutil.which(tool_name):
            rc, out = await _run(tool_name, target, cwd=str(ctx.workspace), timeout=120)
            error_count = out.lower().count("error:")
            return ok(f"{tool_name}: {error_count} errors",
                      {"passed": rc == 0, "tool": tool_name,
                       "error_count": error_count, "output": out[-1000:]})
    return ok("no type checker found — skipped",
              {"passed": True, "tool": "", "error_count": 0, "output": ""})


async def op_exec_coverage(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    if not shutil.which("pytest"):
        return ok("pytest not found — skipped", {"passed": True, "modules": {}})
    rc, out = await _run(
        "pytest", "--cov", "--cov-report=term-missing", "-q",
        cwd=str(ctx.workspace), timeout=300,
    )
    modules: dict[str, float] = {}
    for line in out.splitlines():
        cols = line.split()
        if len(cols) >= 4 and cols[-1].endswith("%"):
            try:
                modules[cols[0]] = float(cols[-1].rstrip("%"))
            except ValueError:
                continue
    ref = ctx.store_blob(out)
    return ok(f"coverage: {len(modules)} modules",
              {"passed": rc == 0, "modules": modules, "stdout_ref": ref})


async def op_exec_build(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    if (ctx.workspace / "Makefile").is_file() and shutil.which("make"):
        rc, out = await _run("make", cwd=str(ctx.workspace), timeout=300)
    elif (ctx.workspace / "package.json").is_file() and shutil.which("npm"):
        rc, out = await _run("npm", "run", "build", cwd=str(ctx.workspace), timeout=300)
    elif shutil.which("python"):
        rc, out = await _run("python", "-m", "build", cwd=str(ctx.workspace), timeout=300)
    else:
        return ok("no build system found — skipped", {"passed": True, "output": ""})
    tail = "\n".join(out.splitlines()[-30:])
    return ok(f"build {'ok' if rc == 0 else 'failed'}",
              {"passed": rc == 0, "output": tail})


async def op_exec_install(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    package = str(args.get("package") or "").strip()
    if not package:
        return err("package is required", deterministic=True)
    if any(tok in package for tok in _SHELL_INJECTION) or package.startswith("-"):
        return err("invalid package name", deterministic=True)
    if (ctx.workspace / "package.json").is_file() and shutil.which("npm"):
        rc, out = await _run("npm", "install", package, cwd=str(ctx.workspace), timeout=300)
    elif shutil.which("pip"):
        rc, out = await _run("pip", "install", package, cwd=str(ctx.workspace), timeout=300)
    else:
        return err("no package manager found", deterministic=True)
    return ok(f"install {package} {'ok' if rc == 0 else 'failed'}",
              {"passed": rc == 0, "output": out[-1000:]})


async def op_exec_grep(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    pattern = str(args.get("pattern") or "").strip()
    if not pattern:
        return err("pattern is required", deterministic=True)
    max_results = int(args.get("max_results") or 50)
    rg = shutil.which("rg")
    hits: list[RepoSearchHit] = []
    if rg:
        rc, out = await _run(
            "rg", "-n", "--no-heading", "-m", str(max_results), "--regexp", pattern,
            cwd=str(ctx.workspace),
        )
        for line in out.splitlines()[:max_results]:
            parts = line.split(":", 2)
            if len(parts) == 3:
                try:
                    hits.append(RepoSearchHit(path=parts[0], line=int(parts[1]),
                                              snippet=parts[2][:200]))
                except ValueError:
                    continue
    else:
        import re as _re
        try:
            rx = _re.compile(pattern)
        except _re.error as e:
            return err(f"invalid regex: {e}", deterministic=True)
        for path in ctx.workspace.rglob("*"):
            if not path.is_file() or _skip_path(path, ctx.workspace):
                continue
            try:
                for i, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
                    if rx.search(line):
                        hits.append(RepoSearchHit(
                            path=str(path.relative_to(ctx.workspace)), line=i,
                            snippet=line[:200]))
                        if len(hits) >= max_results:
                            break
            except (OSError, UnicodeDecodeError):
                continue
            if len(hits) >= max_results:
                break
    slice_ = RepoSlice(files=sorted({h.path for h in hits}), hits=hits)
    return ok(f"{len(hits)} regex hits for '{pattern}'", slice_.model_dump())


# === state.* (extended) ====================================================
async def op_state_get(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    return ok("state snapshot", {"state": json.loads(ctx.state.model_dump_json())})


async def op_state_record_metric(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    key = str(args.get("key") or "").strip()
    if not key:
        return err("key is required", deterministic=True)
    try:
        value = float(args.get("value"))
    except (TypeError, ValueError):
        return err("value must be numeric", deterministic=True)
    rec = MetricRecord(key=key, value=value)
    ctx.state.record_finding("metric", f"{rec.key}={rec.value}")
    return ok(f"metric {rec.key}={rec.value}", rec.model_dump())


async def op_state_add_artifact(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    name = str(args.get("name") or "").strip()
    path = str(args.get("path") or "").strip()
    if not name or not path:
        return err("name and path are required", deterministic=True)
    ctx.state.record_finding("artifact", f"{name}: {path}")
    return ok(f"artifact {name} -> {path}", {"name": name, "path": path})


async def op_state_annotate(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    try:
        idx = int(args["step"])
    except (KeyError, TypeError, ValueError):
        return err("step index is required", deterministic=True)
    note = str(args.get("note") or "").strip()
    if not note:
        return err("note is required", deterministic=True)
    if not (0 <= idx < len(ctx.state.plan)):
        return err(f"step {idx} out of range", deterministic=True)
    desc = ctx.state.plan[idx].description
    ctx.state.record_finding("annotation", f"step[{idx}] ({desc[:40]}): {note}")
    return ok(f"annotated step {idx}", {"step": idx, "note": note})
