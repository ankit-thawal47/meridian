"""Per-task tool context.

Tools are built fresh per task as closures over a ToolContext. This gives each
task its own confined workspace (Property 2 — no shared global tool state) and a
handle to fold structured conclusions into TaskState (Property 3). Large raw
outputs are written to a blob store and referenced, never inlined (Property 3).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from meridian.agent.task_state import TaskState


@dataclass
class ToolContext:
    workspace: Path  # the task's confined directory (git worktree in later phases)
    state: TaskState

    def __post_init__(self) -> None:
        self.workspace = Path(self.workspace).resolve()
        self._blobs = self.workspace / ".meridian" / "blobs"
        self._blobs.mkdir(parents=True, exist_ok=True)
        # Idempotency cache: (tool, args) digest → prior ToolOutcome dict (Property 4 / W2).
        self._call_cache: dict[str, Any] = {}

    def safe_path(self, rel: str) -> Path:
        """Resolve ``rel`` and guarantee it stays inside the workspace.

        Raises ValueError on traversal — the construct that makes confinement
        real rather than advisory.
        """
        candidate = (self.workspace / rel).resolve()
        if candidate != self.workspace and self.workspace not in candidate.parents:
            raise ValueError(f"path escapes workspace: {rel}")
        return candidate

    def store_blob(self, text: str) -> str:
        """Persist a large raw output and return an opaque reference."""
        ref = f"blob:{uuid.uuid4().hex}"
        (self._blobs / ref.split(":", 1)[1]).write_text(text)
        return ref

    def get_cached(self, key: str) -> Any | None:
        return self._call_cache.get(key)

    def set_cached(self, key: str, result: Any) -> None:
        self._call_cache[key] = result
