"""Per-task workspace preparation (Property 2 — isolation foundation).

Phase 0: materialize a confined working copy of the target repo under
``workspace_dir/<task_id>``. A local path is copied; an ``https`` URL is cloned.
Phase 1 (W3): local git repos use ``git worktree add --detach`` so multiple
tasks on the same repo get isolated indices and HEAD references, preventing
concurrent-task collisions. A ``.meridian/workspace.json`` marker records the
workspace type so cleanup can call the right inverse operation.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

from meridian.config import get_settings

_MARKER_RELPATH = ".meridian/workspace.json"


async def _git(args: list[str], cwd: str | None = None) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    combined = (out + err).decode(errors="replace")
    return proc.returncode or 0, combined


def _write_marker(dest: Path, kind: str, source_repo: str) -> None:
    marker_path = dest / ".meridian"
    marker_path.mkdir(parents=True, exist_ok=True)
    (marker_path / "workspace.json").write_text(
        json.dumps({"kind": kind, "source_repo": source_repo})
    )


def _read_marker(dest: Path) -> dict | None:
    p = dest / _MARKER_RELPATH
    if p.exists():
        try:
            return json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return None


async def prepare_workspace(task_id: str, repo: str) -> Path:
    root = get_settings().workspace_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    dest = root / task_id
    if dest.exists():
        # Clean up any prior workspace for this task_id before re-creating.
        cleanup_workspace(task_id)

    if repo.startswith("http://") or repo.startswith("https://"):
        rc, msg = await _git(["clone", "--depth", "1", repo, str(dest)])
        if rc != 0:
            raise RuntimeError(f"git clone failed: {msg[:500]}")
        _write_marker(dest, "clone", repo)
    else:
        src = Path(repo).resolve()
        if not src.is_dir():
            raise RuntimeError(f"local repo path not found: {repo}")

        git_dir = src / ".git"
        if git_dir.exists() and shutil.which("git"):
            # True git worktree — isolated index + HEAD per task.
            rc, msg = await _git(["worktree", "add", "--detach", str(dest)], cwd=str(src))
            if rc != 0:
                raise RuntimeError(f"git worktree add failed: {msg[:500]}")
            _write_marker(dest, "worktree", str(src))
        else:
            shutil.copytree(src, dest, ignore=shutil.ignore_patterns(".git"))
            _write_marker(dest, "copy", str(src))

    return dest


def cleanup_workspace(task_id: str) -> None:
    dest = get_settings().workspace_dir.resolve() / task_id
    if not dest.exists():
        return

    marker = _read_marker(dest)
    if marker and marker.get("kind") == "worktree":
        source_repo = marker.get("source_repo", "")
        if source_repo and shutil.which("git"):
            import subprocess

            subprocess.run(
                ["git", "worktree", "remove", "--force", str(dest)],
                cwd=source_repo,
                capture_output=True,
            )
            return

    shutil.rmtree(dest, ignore_errors=True)
