"""Pure documentation operations (doc_* namespace).

Each ``op_doc_*`` takes (ctx, args) and returns an MCP content dict, sharing the
``ok``/``err`` envelope from core_ops. These read project documentation —
markdown/rST sections, doc-wide search, OpenAPI specs, README and CHANGELOG — so
the agent can ground its work in stated intent rather than guessing from code.
"""

from __future__ import annotations

import json
import re
import shutil
from typing import Any

from meridian.tools.context import ToolContext
from meridian.tools.core_ops import _run, _skip_path, err, ok
from meridian.tools.schemas import DocSection

_DOC_EXTS = {".md", ".rst"}
_HEADING_RX = re.compile(r"^(#{1,2})\s+(.*)$")


async def op_doc_read(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    try:
        p = ctx.safe_path(args["path"])
    except (ValueError, KeyError) as e:
        return err(str(e), deterministic=True)
    if p.suffix not in _DOC_EXTS:
        return err(f"not a doc file (.md/.rst): {args.get('path')}", deterministic=True)
    if not p.is_file():
        return err(f"not a file: {args['path']}", deterministic=True)
    sections: list[DocSection] = []
    heading = "(preamble)"
    buf: list[str] = []
    for line in p.read_text(errors="replace").splitlines():
        m = _HEADING_RX.match(line)
        if m:
            if buf or heading != "(preamble)":
                sections.append(DocSection(heading=heading, content="\n".join(buf).strip()[:4000]))
            heading = m.group(2).strip()
            buf = []
        else:
            buf.append(line)
    if buf or heading != "(preamble)":
        sections.append(DocSection(heading=heading, content="\n".join(buf).strip()[:4000]))
    return ok(f"{len(sections)} sections in {args['path']}",
              {"path": args["path"], "sections": [s.model_dump() for s in sections]})


async def op_doc_search(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("query") or "").strip()
    if not query:
        return err("query is required", deterministic=True)
    hits: list[dict[str, Any]] = []
    rg = shutil.which("rg")
    if rg:
        rc, out = await _run(
            "rg", "-n", "--no-heading", "-g", "*.md", "-g", "*.rst", query,
            cwd=str(ctx.workspace),
        )
        for line in out.splitlines()[:100]:
            parts = line.split(":", 2)
            if len(parts) == 3:
                hits.append({"path": parts[0], "line": int(parts[1]),
                             "snippet": parts[2].strip()[:200]})
    else:
        for path in ctx.workspace.rglob("*"):
            if not path.is_file() or path.suffix not in _DOC_EXTS:
                continue
            if _skip_path(path, ctx.workspace):
                continue
            try:
                for i, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
                    if query.lower() in line.lower():
                        hits.append({"path": str(path.relative_to(ctx.workspace)),
                                     "line": i, "snippet": line.strip()[:200]})
            except (OSError, UnicodeDecodeError):
                continue
    return ok(f"{len(hits)} doc hits for '{query}'", {"hits": hits[:100]})


async def op_doc_api_spec(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    candidates = ["openapi.json", "openapi.yaml", "swagger.json"]
    spec_path = None
    for name in candidates:
        for found in ctx.workspace.rglob(name):
            if not _skip_path(found, ctx.workspace):
                spec_path = found
                break
        if spec_path:
            break
    if not spec_path:
        return err("no openapi/swagger spec found", deterministic=True)
    raw = spec_path.read_text(errors="replace")
    paths_obj: dict[str, Any] = {}
    try:
        if spec_path.suffix == ".json":
            paths_obj = json.loads(raw).get("paths", {})
        else:
            import yaml  # type: ignore
            paths_obj = (yaml.safe_load(raw) or {}).get("paths", {})
    except Exception:
        # Fall back to a crude path count by scanning for path-like keys.
        paths_obj = {}
    endpoints = list(paths_obj.keys())[:20]
    return ok(f"spec {spec_path.name}: {len(paths_obj)} paths",
              {"path": str(spec_path.relative_to(ctx.workspace)),
               "path_count": len(paths_obj), "endpoints": endpoints})


async def op_doc_readme(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    for name in ("README.md", "README.rst", "README"):
        p = ctx.workspace / name
        if p.is_file():
            text = p.read_text(errors="replace")
            return ok(f"read {name} ({len(text)} chars)",
                      {"path": name, "content": text[:8000],
                       "truncated": len(text) > 8000})
    return err("README not found in workspace root", deterministic=True)


async def op_doc_changelog(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    for name in ("CHANGELOG.md", "CHANGELOG.rst", "CHANGELOG"):
        p = ctx.workspace / name
        if p.is_file():
            text = p.read_text(errors="replace")
            content = text[-500:] if len(text) > 500 else text
            return ok(f"read {name} ({len(text)} chars)",
                      {"path": name, "content": content,
                       "truncated": len(text) > 500})
    return err("CHANGELOG not found in workspace root", deterministic=True)
