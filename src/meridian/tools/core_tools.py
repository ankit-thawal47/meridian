"""SDK decoration layer for all Meridian tools (Property 1 & 5).

Thin: each tool is a @tool closure delegating to a pure ``op_*`` in core_ops
or vcs_ops. Descriptions live here and state *what the tool does, when to use
it, when not, and its side effects* so selection stays unambiguous as the
registry grows.

Tool namespaces:
  repo_*   — read the repository
  edit_*   — modify files
  exec_*   — run commands / tests
  state_*  — update authoritative task state
  vcs_*    — git operations (branch, commit, PR)
  review_* — validation and security review
"""

from __future__ import annotations

from typing import Any

from claude_agent_sdk import tool

from meridian.tools import core_ops, vcs_ops
from meridian.tools.context import ToolContext

CORE_TOOL_NAMES = [
    "repo_read",
    "repo_search",
    "repo_list",
    "repo_glob",
    "repo_stat",
    "repo_diff",
    "repo_log",
    "repo_blame",
    "repo_outline",
    "edit_apply",
    "edit_create",
    "edit_delete",
    "edit_rename",
    "edit_insert",
    "exec_test",
    "exec_run",
    "exec_format",
    "exec_typecheck",
    "exec_coverage",
    "exec_build",
    "exec_install",
    "exec_grep",
    "state_update",
    "state_get",
    "state_record_metric",
    "state_add_artifact",
    "state_annotate",
    "vcs_branch",
    "vcs_commit",
    "vcs_open_pr",
    "review_lint",
    "review_spawn_security",
]


def build_core_tools(ctx: ToolContext) -> list[Any]:
    @tool(
        "repo_read",
        "Read the full contents of one file. Use to inspect a specific file before "
        "editing. Input: {path}. Not for searching (use repo_search) or writing "
        "(use edit_apply).",
        {"path": str},
    )
    async def repo_read(args: dict[str, Any]) -> dict[str, Any]:
        return await core_ops.op_repo_read(ctx, args)

    @tool(
        "repo_search",
        "Search the repository for a substring and return matching files/lines. Use "
        "to locate code relevant to the issue. Input: {query, max_results?}. Returns "
        "a budgeted slice, never the whole tree.",
        {"query": str, "max_results": int},
    )
    async def repo_search(args: dict[str, Any]) -> dict[str, Any]:
        return await core_ops.op_repo_search(ctx, args)

    @tool(
        "repo_list",
        "List the entries (files and subdirs) at a directory path with their sizes. "
        "Use to discover what is in a folder. Input: {path?, recursive?}. NOT for "
        "matching a pattern (use repo_glob) or reading file text (use repo_read).",
        {"path": str, "recursive": bool},
    )
    async def repo_list(args: dict[str, Any]) -> dict[str, Any]:
        return await core_ops.op_repo_list(ctx, args)

    @tool(
        "repo_glob",
        "Find files whose path matches a glob pattern (e.g. 'src/**/*.py'). Use to "
        "enumerate files by name pattern. Input: {pattern}. NOT for content search "
        "(use repo_search/exec_grep) or directory listing (use repo_list).",
        {"pattern": str},
    )
    async def repo_glob(args: dict[str, Any]) -> dict[str, Any]:
        return await core_ops.op_repo_glob(ctx, args)

    @tool(
        "repo_stat",
        "Get metadata for one path: size_bytes, mtime_iso, is_file, is_dir. Use to "
        "check existence/size before reading. Input: {path}. NOT for reading content "
        "(use repo_read) or listing a directory (use repo_list).",
        {"path": str},
    )
    async def repo_stat(args: dict[str, Any]) -> dict[str, Any]:
        return await core_ops.op_repo_stat(ctx, args)

    @tool(
        "repo_diff",
        "Show the git diff of the working tree vs HEAD (or staged vs HEAD). Use to "
        "review uncommitted changes before committing. Input: {staged?}. NOT for "
        "commit history (use repo_log) or per-line authorship (use repo_blame).",
        {"staged": bool},
    )
    async def repo_diff(args: dict[str, Any]) -> dict[str, Any]:
        return await core_ops.op_repo_diff(ctx, args)

    @tool(
        "repo_log",
        "List the last N commits as {hash, message}. Use to understand recent history. "
        "Input: {n?} (default 10). NOT for the current uncommitted diff (use repo_diff) "
        "or line-level authorship (use repo_blame).",
        {"n": int},
    )
    async def repo_log(args: dict[str, Any]) -> dict[str, Any]:
        return await core_ops.op_repo_log(ctx, args)

    @tool(
        "repo_blame",
        "Show git blame for a line range of a file: author and commit per line. Use to "
        "find who last changed specific lines. Input: {path, start, end}. NOT for whole "
        "history (use repo_log) or current changes (use repo_diff).",
        {"path": str, "start": int, "end": int},
    )
    async def repo_blame(args: dict[str, Any]) -> dict[str, Any]:
        return await core_ops.op_repo_blame(ctx, args)

    @tool(
        "repo_outline",
        "Parse a Python file and return its classes/functions/methods with line numbers "
        "and docstring previews. Use to map a file's structure before editing. Input: "
        "{path}. NOT for reading full content (use repo_read) or imports (use "
        "analysis_imports).",
        {"path": str},
    )
    async def repo_outline(args: dict[str, Any]) -> dict[str, Any]:
        return await core_ops.op_repo_outline(ctx, args)

    @tool(
        "edit_apply",
        "Apply a single exact-string replacement to a file; old_string must match "
        "exactly and uniquely. Use to implement the fix. Input: {path, old_string, "
        "new_string}. The only tool that writes files.",
        {"path": str, "old_string": str, "new_string": str},
    )
    async def edit_apply(args: dict[str, Any]) -> dict[str, Any]:
        return await core_ops.op_edit_apply(ctx, args)

    @tool(
        "edit_create",
        "Create a NEW file with optional content; errors if the file already exists. "
        "Use to add a new file. Input: {path, content?}. NOT for changing an existing "
        "file (use edit_apply) or inserting into one (use edit_insert).",
        {"path": str, "content": str},
    )
    async def edit_create(args: dict[str, Any]) -> dict[str, Any]:
        return await core_ops.op_edit_create(ctx, args)

    @tool(
        "edit_delete",
        "Delete an existing file from the workspace. Use to remove a file. Input: "
        "{path}. NOT for moving a file (use edit_rename) or clearing content (use "
        "edit_apply).",
        {"path": str},
    )
    async def edit_delete(args: dict[str, Any]) -> dict[str, Any]:
        return await core_ops.op_edit_delete(ctx, args)

    @tool(
        "edit_rename",
        "Rename or move a file within the workspace. Use to relocate/rename a file. "
        "Input: {path, new_path}. NOT for deleting (use edit_delete) or editing content "
        "(use edit_apply).",
        {"path": str, "new_path": str},
    )
    async def edit_rename(args: dict[str, Any]) -> dict[str, Any]:
        return await core_ops.op_edit_rename(ctx, args)

    @tool(
        "edit_insert",
        "Insert text at a specific 1-indexed line in a file, shifting existing lines "
        "down. Use to add lines without matching surrounding text. Input: {path, line, "
        "text}. NOT for replacing text (use edit_apply) or creating a file (use "
        "edit_create).",
        {"path": str, "line": int, "text": str},
    )
    async def edit_insert(args: dict[str, Any]) -> dict[str, Any]:
        return await core_ops.op_edit_insert(ctx, args)

    @tool(
        "exec_test",
        "Run the repo's tests (or a given command) and return a typed result. Use to "
        "validate a fix. Input: {command?} (default 'pytest -q'). Failures are "
        "deterministic feedback, not transient errors.",
        {"command": str},
    )
    async def exec_test(args: dict[str, Any]) -> dict[str, Any]:
        return await core_ops.op_exec_test(ctx, args)

    @tool(
        "exec_run",
        "Run a single shell program with args (no pipes/redirects) under a 60s timeout; "
        "returns {stdout, stderr, exit_code}. Use for one-off commands not covered by a "
        "dedicated tool. Input: {command}. NOT for tests (use exec_test) or regex search "
        "(use exec_grep).",
        {"command": str},
    )
    async def exec_run(args: dict[str, Any]) -> dict[str, Any]:
        return await core_ops.op_exec_run(ctx, args)

    @tool(
        "exec_format",
        "Auto-format code with ruff/black/prettier (whichever is installed). Use to fix "
        "style before committing. Input: {path?}. NOT for linting checks (use "
        "review_lint) or type checks (use exec_typecheck).",
        {"path": str},
    )
    async def exec_format(args: dict[str, Any]) -> dict[str, Any]:
        return await core_ops.op_exec_format(ctx, args)

    @tool(
        "exec_typecheck",
        "Run a static type checker (mypy/pyright) and return an error count. Use to "
        "verify types before a PR. Input: {path?}. NOT for style (use review_lint/"
        "exec_format) or running tests (use exec_test).",
        {"path": str},
    )
    async def exec_typecheck(args: dict[str, Any]) -> dict[str, Any]:
        return await core_ops.op_exec_typecheck(ctx, args)

    @tool(
        "exec_coverage",
        "Run pytest with coverage and return per-module coverage percentages. Use to "
        "find under-tested modules. Input: {} . NOT for a plain test pass/fail (use "
        "exec_test) or finding missing test files (use analysis_test_gaps).",
        {},
    )
    async def exec_coverage(args: dict[str, Any]) -> dict[str, Any]:
        return await core_ops.op_exec_coverage(ctx, args)

    @tool(
        "exec_build",
        "Build the project via make / npm run build / python -m build (auto-detected). "
        "Use to verify the project compiles/packages. Input: {} . NOT for running tests "
        "(use exec_test) or installing deps (use exec_install).",
        {},
    )
    async def exec_build(args: dict[str, Any]) -> dict[str, Any]:
        return await core_ops.op_exec_build(ctx, args)

    @tool(
        "exec_install",
        "Install a single dependency via pip or npm (auto-detected). Use to add a "
        "required package. Input: {package}. NOT for building (use exec_build) or "
        "running arbitrary commands (use exec_run).",
        {"package": str},
    )
    async def exec_install(args: dict[str, Any]) -> dict[str, Any]:
        return await core_ops.op_exec_install(ctx, args)

    @tool(
        "exec_grep",
        "Regex search across the repo (ripgrep --regexp), returning matching lines. Use "
        "when you need regex matching. Input: {pattern, max_results?}. NOT for plain "
        "substring search (use repo_search) or doc-only search (use doc_search).",
        {"pattern": str, "max_results": int},
    )
    async def exec_grep(args: dict[str, Any]) -> dict[str, Any]:
        return await core_ops.op_exec_grep(ctx, args)

    @tool(
        "state_update",
        "Update authoritative task state: set/replace the plan, mark a step done, "
        "and/or record a durable finding. Use to keep plan and conclusions current. "
        "Input: {plan?: [str], mark_done?: int, finding?: str}.",
        {"plan": list, "mark_done": int, "finding": str},
    )
    async def state_update(args: dict[str, Any]) -> dict[str, Any]:
        return await core_ops.op_state_update(ctx, args)

    @tool(
        "state_get",
        "Return a read-only JSON snapshot of the current TaskState (plan, files, "
        "findings, metrics). Use to inspect state without changing it. Input: {} . NOT "
        "for modifying state (use state_update) or recording metrics (use "
        "state_record_metric).",
        {},
    )
    async def state_get(args: dict[str, Any]) -> dict[str, Any]:
        return await core_ops.op_state_get(ctx, args)

    @tool(
        "state_record_metric",
        "Record a named numeric metric (e.g. coverage=82.5) into task findings. Use to "
        "track quantitative outcomes. Input: {key, value}. NOT for free-text notes (use "
        "state_update finding) or file artifacts (use state_add_artifact).",
        {"key": str, "value": float},
    )
    async def state_record_metric(args: dict[str, Any]) -> dict[str, Any]:
        return await core_ops.op_state_record_metric(ctx, args)

    @tool(
        "state_add_artifact",
        "Record a produced file path under a name as a task artifact. Use to register "
        "outputs (reports, logs). Input: {name, path}. NOT for numeric metrics (use "
        "state_record_metric) or editing files (use edit_apply).",
        {"name": str, "path": str},
    )
    async def state_add_artifact(args: dict[str, Any]) -> dict[str, Any]:
        return await core_ops.op_state_add_artifact(ctx, args)

    @tool(
        "state_annotate",
        "Attach a free-form note to a specific plan step by index. Use to annotate "
        "progress/decisions on a step. Input: {step, note}. NOT for marking a step done "
        "or replacing the plan (use state_update).",
        {"step": int, "note": str},
    )
    async def state_annotate(args: dict[str, Any]) -> dict[str, Any]:
        return await core_ops.op_state_annotate(ctx, args)

    @tool(
        "vcs_branch",
        "Create a new git branch in the workspace. Use before editing to keep changes "
        "isolated from the default branch. Input: {branch}. Not for committing "
        "(use vcs_commit) or opening a PR (use vcs_open_pr).",
        {"branch": str},
    )
    async def vcs_branch(args: dict[str, Any]) -> dict[str, Any]:
        return await vcs_ops.op_vcs_branch(ctx, args)

    @tool(
        "vcs_commit",
        "Stage all workspace changes and commit with a message. Use after editing to "
        "checkpoint work. Input: {message}. Fails if nothing to commit.",
        {"message": str},
    )
    async def vcs_commit(args: dict[str, Any]) -> dict[str, Any]:
        return await vcs_ops.op_vcs_commit(ctx, args)

    @tool(
        "vcs_open_pr",
        "Open a pull request for the current branch. Pushes to origin if a GitHub "
        "token is configured; returns a PRDraft either way. Input: {title, body, "
        "base?, blocking?}. Pass blocking=true to prevent PR open when a security "
        "report is blocking.",
        {"title": str, "body": str, "base": str, "blocking": bool},
    )
    async def vcs_open_pr(args: dict[str, Any]) -> dict[str, Any]:
        return await vcs_ops.op_vcs_open_pr(ctx, args)

    @tool(
        "review_lint",
        "Run ruff linting on the workspace (or a given path) and return a pass/fail "
        "result with lint output. Use before opening a PR. Input: {path?}.",
        {"path": str},
    )
    async def review_lint(args: dict[str, Any]) -> dict[str, Any]:
        return await vcs_ops.op_review_lint(ctx, args)

    @tool(
        "review_spawn_security",
        "Spawn the SecuritySubagent to review the workspace for vulnerabilities. "
        "Returns a typed SecurityReport with findings and a blocking flag. Use before "
        "vcs_open_pr. Input: {focus?}. Not for editing (use edit_apply) or linting "
        "(use review_lint).",
        {"focus": str},
    )
    async def review_spawn_security(args: dict[str, Any]) -> dict[str, Any]:
        return await vcs_ops.op_review_spawn_security(ctx, args)

    return [
        repo_read,
        repo_search,
        repo_list,
        repo_glob,
        repo_stat,
        repo_diff,
        repo_log,
        repo_blame,
        repo_outline,
        edit_apply,
        edit_create,
        edit_delete,
        edit_rename,
        edit_insert,
        exec_test,
        exec_run,
        exec_format,
        exec_typecheck,
        exec_coverage,
        exec_build,
        exec_install,
        exec_grep,
        state_update,
        state_get,
        state_record_metric,
        state_add_artifact,
        state_annotate,
        vcs_branch,
        vcs_commit,
        vcs_open_pr,
        review_lint,
        review_spawn_security,
    ]
