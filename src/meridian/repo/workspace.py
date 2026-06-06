"""Per-task workspace preparation (Property 2 — isolation foundation).

Phase 0: materialize a confined working copy of the target repo under
``workspace_dir/<task_id>``. A local path is copied; an ``https`` URL is cloned.
Phase 1 upgrades this to a dedicated git worktree per task/subagent so multiple
tasks on the same repo never collide.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from meridian.config import get_settings


async def prepare_workspace(task_id: str, repo: str) -> Path:
    root = get_settings().workspace_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    dest = root / task_id
    if dest.exists():
        shutil.rmtree(dest)

    if repo.startswith("http://") or repo.startswith("https://"):
        proc = await asyncio.create_subprocess_exec(
            "git",
            "clone",
            "--depth",
            "1",
            repo,
            str(dest),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, err = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"git clone failed: {err.decode(errors='replace')[:500]}")
    else:
        src = Path(repo).resolve()
        if not src.is_dir():
            raise RuntimeError(f"local repo path not found: {repo}")
        shutil.copytree(src, dest, ignore=shutil.ignore_patterns(".git"))
    return dest


def cleanup_workspace(task_id: str) -> None:
    dest = get_settings().workspace_dir.resolve() / task_id
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
