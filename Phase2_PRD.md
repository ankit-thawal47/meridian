# Meridian — Phase 2 PRD: Unimplemented Features

> **Status:** Draft v1.0 · **Owner:** Ankit · **Date:** 2026-06-06
> **Source:** Gap analysis against Phase 0–1 implementation
> **Prerequisite:** Phase 1 complete (isolation, retry, hooks, typed schemas, contract tests)

---

## 0. Purpose

This document captures every feature required by the main PRD that is **not yet implemented** after Phase 0–1. Each item includes: what the PRD requires, what currently exists (if anything), what is missing, and a concrete implementation description.

Items are organized by the five PRD properties. Severity labels:

- **❌ Missing** — nothing exists; must be built from scratch
- **⚠️ Dead code** — module is written but never called in the run path; must be wired
- **⚠️ Partial** — feature partially implemented; specific gaps must be filled

---

## 1. Property 1 — Model-Driven Tool Selection

### 1.1 Tool retrieval for large registries (FR1.1 at scale)

**Severity:** ⚠️ Dead code

**PRD requirement (FR1.1 / §6.4):**
The registry must stay coherent and unambiguous as it grows toward 50+ tools. When the registry exceeds the threshold, the top-k most relevant tools should be selected per turn rather than flooding the context with all 50+.

**What exists:**
`src/meridian/tools/retrieval.py` contains a complete `select_tools(all_tools, query, k=TOP_K)` function implementing keyword-overlap scoring. `RETRIEVAL_THRESHOLD = 20`, `TOP_K = 12` are defined.

**What is missing:**
`src/meridian/tools/registry.py:build_registry()` calls only `count_guard(tools)`, which emits a warning log when the count exceeds the threshold. It never calls `select_tools()`. When the registry grows past 20 tools, all tools are still eagerly loaded — selection will degrade silently.

**Implementation required:**

1. Modify `build_registry()` to accept an optional `query: str` parameter representing the current task goal or turn prompt.
2. After `build_core_tools(ctx)`, if `len(tools) > RETRIEVAL_THRESHOLD`, call `select_tools(tools, query)` to filter down to `TOP_K`.
3. The orchestrator must pass the current task goal as the `query` when calling `build_registry(ctx, query=ctx.state.goal)`.
4. Update `ToolRegistry.tool_names` to reflect the filtered set so `allowed_tools` in `ClaudeAgentOptions` stays in sync.
5. Add a test: registry with 25 mock tools + a query returns exactly `TOP_K` tools, and the tool names match the highest-scoring ones.

---

### 1.2 LLM-judge ambiguity audit (FR1.5)

**Severity:** ❌ Missing

**PRD requirement (FR1.5 / §5 Property 1 verification):**
An LLM-judge eval must confirm each tool's description uniquely disambiguates it from all others. Target: 0 ambiguous pairs. This is one of the two "how we know Property 1 holds" checks.

**What exists:**
`evals/run_evals.py:eval_p1_no_hardwired_graph()` only checks that the orchestrator source does not contain a handful of forbidden strings (`switch(`, `if issue_type`, etc.). This is a necessary but not sufficient check.

**What is missing:**
No eval exists that measures tool description quality or pairwise ambiguity. The wrong-tool rate and novel-task pass-rate metrics (also required by FR1.5) have no implementation.

**Implementation required:**

1. Add `eval_p1_ambiguity_audit()` to `evals/run_evals.py`:
   - Load all tool descriptions from the registry.
   - For each pair of tools, prompt a judge model (e.g. `claude-haiku-4-5`) with: *"Given these two tool descriptions, could a model reasonably confuse which one to call for the same task? Answer yes/no with a one-sentence reason."*
   - Collect all "yes" pairs. The eval passes if the count is 0.
2. Add `eval_p1_wrong_tool_rate()`:
   - Use the fixtures in `evals/fixtures/` (extend with more issue→expected-tool-sequence fixtures).
   - Run each fixture through a stub orchestrator that records tool selections.
   - Assert wrong-tool rate below a defined threshold (e.g. < 5%).
3. Add `eval_p1_novel_task()`:
   - Include at least 3 fixture issues that don't match any "common pattern".
   - Assert task completes (status = succeeded or a PR draft is produced).
4. Wire all three into `run_all()` and gate CI on them.

---

## 2. Property 2 — Genuine Subagent Isolation

### 2.1 SDK-native agent invocation path (FR2 / §6.1)

**Severity:** ⚠️ Dead code

**PRD requirement:**
The Claude Agent SDK's native subagent primitive should be used. Subagents registered in `ClaudeAgentOptions.agents` can be invoked by the orchestrating model itself (the model decides when to spawn a security review, which is the model-driven principle of Property 1 applied to subagents).

**What exists:**
`sdk_session.py:78` registers `agents={"security_reviewer": build_security_subagent_definition()}` in `ClaudeAgentOptions`. The `AgentDefinition` is correctly built with read-only tools and a capped turn budget.

**What is missing:**
`op_review_spawn_security()` in `tools/vcs_ops.py` spawns the subagent via a direct `sdk_query(prompt=focus, options=sub_options)` call — bypassing the SDK-native `agents=` registry entirely. There are two parallel spawn paths, only one is used. The SDK-native path, which enables the orchestrating model to autonomously invoke the subagent, is never triggered.

**Implementation required:**

1. Decide on a single canonical spawn path. The recommended approach: keep both but clarify their roles.
   - **SDK-native path** (via `agents=`): used when the orchestrating model itself decides to invoke the security reviewer mid-task. The model calls a tool that triggers the registered agent. This is the model-driven approach.
   - **Explicit path** (via `op_review_spawn_security`): used as a forced gate before `vcs_open_pr`, regardless of model decision.
2. If keeping the explicit path as the gate, update the tool description for `review_spawn_security` to clarify it calls the subagent programmatically.
3. If the SDK-native path is the preferred approach: wire `review_spawn_security` as an agent-delegation tool that triggers the `security_reviewer` agent from the `agents=` dict via the SDK's agent invocation API, not a direct `sdk_query`.
4. Add a test asserting the chosen path actually results in a separate SDK context (separate `max_turns` budget consumed, parent context unchanged).

### 2.2 Subagent filesystem boundary (FR2.3)

**Severity:** ⚠️ Partial

**PRD requirement (FR2.3):**
*"Subagents execute in an isolated git worktree; writes outside the worktree are impossible by construction."*

**What exists:**
The parent task gets an isolated git worktree via `workspace.py:prepare_workspace()`. The SecuritySubagent options set `cwd=str(ctx.workspace)` — the same directory as the parent.

**What is missing:**
The isolation guarantee for the subagent is entirely behavioral (the `_DISALLOWED_TOOLS` list), not structural (a separate filesystem boundary). The PRD says "by construction" — meaning even a compromised subagent prompt should not be able to write, because the filesystem prevents it, not just the tool list. A subagent that somehow gained access to a write tool could still write to the shared parent workspace.

**Implementation required:**

1. In `build_security_subagent_options(ctx)`, create a read-only bind-mount or a separate temp directory that contains only the files the subagent needs to inspect.
   - Simple approach: copy the workspace diff (only modified files) to a new temp directory and set `cwd` to that directory. The subagent has no path to the parent worktree.
   - Stronger approach: use a read-only filesystem view (on Linux: `unshare`/`overlayfs`; on macOS: use a separate `git worktree` at a detached read-only path).
2. Update `ToolContext.safe_path()` logic in the subagent's `_repo_read`/`_repo_search` closures to confine reads to the new read-only directory.
3. Add a test: subagent attempting `open(path, 'w')` on the parent workspace path raises an error (filesystem-level, not tool-level).

---

## 3. Property 3 — Long-Horizon Coherence

### 3.1 Per-turn budget enforcement in orchestrator (FR3.2)

**Severity:** ❌ Missing

**PRD requirement (FR3.2):**
*"Token budget is allocated per region (repo map / TaskState / recent outputs / system) and enforced before each turn."* The budget invariant test requires: assert total context ≤ budget at every turn.

**What exists:**
`context/budget.py` defines `REGION_CEILINGS` for four regions (`system`, `repo_map`, `task_state`, `recent_outputs`) and implements `RegionBudget.allocate()`. Only the `task_state` region is ever used — inside `TaskState.render_context()`. The other three regions are defined but never tracked. There is no per-turn budget check anywhere in the orchestrator.

**What is missing:**
- The orchestrator does not instantiate a `RegionBudget` or check `within_budget()` before each turn.
- The `system`, `repo_map`, and `recent_outputs` regions are never allocated — their ceilings exist but have zero effect.
- Tool outputs (which map to `recent_outputs`) are returned directly to the SDK and are not budgeted through `RegionBudget`.

**Implementation required:**

1. Extend `ToolContext` to hold a `RegionBudget` instance that persists across the task's lifetime.
2. In `_handle_message()` (or in each `op_*` function), after a tool call completes, call `budget.allocate("recent_outputs", tool_output_text)` to track the region consumption. If the region is exhausted, truncate the output before it's returned.
3. Add a `check_budget(state, budget)` function called at the top of `_handle_message()` that asserts `budget.within_budget()`. If it fails, emit a warning span and trigger the eviction policy (see §3.2 below).
4. Track `system` region separately: the system prompt byte count should be estimated once at session start and recorded in the budget.
5. Track `repo_map` region: `op_repo_search()` and `op_repo_read()` outputs should be allocated against `repo_map` via `budget.allocate("repo_map", content)`.
6. Add the budget invariant as a runtime assertion (not just a test): if `not budget.within_budget()` at turn start, log an error and trigger graceful degradation.
7. Add the eval: `eval_p3_budget_invariant()` should instantiate a real `RegionBudget`, simulate 150 turns with large tool outputs, and assert the invariant holds throughout.

---

### 3.2 Budget-pressure eviction policy (FR3.6)

**Severity:** ❌ Missing

**PRD requirement (FR3.6):**
*"On budget pressure, oldest/lowest-value regions are evicted by an explicit policy (not random truncation)."*

**What exists:**
`TaskState.render_context()` caps findings at `max_findings=25` (hardcoded) and truncates the rendered text at the `task_state` ceiling via `RegionBudget.allocate()`. This is truncation, not eviction.

**What is missing:**
There is no eviction policy. When the context fills, the current behavior is: the TaskState text is truncated mid-sentence if it exceeds the ceiling. Older findings are not preferentially dropped. The `recent_outputs` region has no eviction logic at all.

**Implementation required:**

1. Define an `EvictionPolicy` class in `context/budget.py`:
   ```
   Eviction order (lowest value → evicted first):
     1. recent_outputs older than N turns
     2. findings beyond the last M (dynamic, budget-driven, not hardcoded 25)
     3. completed plan steps (done=True)
     4. files_touched entries older than the current editing focus
   ```
2. In `TaskState`, replace the hardcoded `max_findings=25` with a budget-driven cap: `max_findings = budget.remaining("task_state") // AVG_FINDING_TOKENS`.
3. Add an `evict(budget: RegionBudget)` method to `TaskState` that drops old findings, completed steps, and stale file references until `within_budget()` returns True.
4. Call `state.evict(budget)` in the orchestrator when `check_budget()` detects pressure (before constructing the next turn's prompt).
5. Add a test: a state with 200 findings + 100 plan steps evicts correctly under pressure and the remaining content is within budget.
6. Ensure eviction is logged as a span (`kind="eviction"`) so it is observable.

---

## 4. Property 4 — Production Scaffolding

### 4.1 VCS tool idempotency (FR4.2)

**Severity:** ⚠️ Partial

**PRD requirement (FR4.2):**
*"Side-effecting tools (vcs, exec) are guarded against duplication."*

**What exists:**
`op_edit_apply()` and `op_exec_test()` use `ctx.get_cached(key)` / `ctx.set_cached(key, result)` with a SHA-256 digest of `(tool, args)` as the cache key. This prevents duplicate file edits and redundant test runs.

**What is missing:**
`op_vcs_branch()`, `op_vcs_commit()`, and `op_vcs_open_pr()` have no idempotency cache. Running `vcs_commit` twice with the same message creates two commits. Running `vcs_branch` twice with the same name returns a git error (which is handled) — but the error is `deterministic=True`, meaning the model gets a confusing "branch already exists" message instead of a clean cache hit.

**Implementation required:**

1. Add idempotency caching to `op_vcs_branch()`:
   - Key: `_call_key("vcs_branch", {"branch": branch})`.
   - On cache hit, return the cached result directly (the branch was already created).
2. Add idempotency caching to `op_vcs_commit()`:
   - Key: `_call_key("vcs_commit", {"message": message})`.
   - On cache hit, return the cached result (commit was already made).
   - Note: this is content-based idempotency, not git-level — if file contents changed between calls with the same message, the cache key will differ.
3. Add idempotency caching to `op_vcs_open_pr()`:
   - Key: `_call_key("vcs_open_pr", {"title": title, "base": base})`.
   - On cache hit, return the cached `PRDraft` — don't push or create a duplicate PR.
4. Add tests for all three: call twice, assert git/API operations invoked only once.

---

### 4.2 Span latency and token count measurement (FR4.4)

**Severity:** ⚠️ Partial

**PRD requirement (FR4.4):**
*"Every model turn and tool call emits a trace span with inputs (redacted), outputs, latency, cost, outcome."* NFR-Observability: 100% of tool calls and model turns are traced with cost, latency, and outcome.

**What exists:**
`SpanRecord` has fields `duration_ms: float = 0.0`, `input_tokens: int = 0`, `output_tokens: int = 0`. These are defined but never populated. `DbTraceSink.record()` persists `kind`, `name`, `summary`, `cost_usd`, `outcome`, `ts` — but `duration_ms`, `input_tokens`, `output_tokens`, and `attributes` are not in the `TraceSpan` ORM model and are silently dropped on every write.

**What is missing:**
- Latency measurement around tool calls and model turns.
- Token count extraction from SDK message metadata.
- `TraceSpan` ORM model and DB table missing the columns for `duration_ms`, `input_tokens`, `output_tokens`, `attributes`.

**Implementation required:**

1. **Measure latency:** In `_handle_message()`, record `start = time.monotonic()` before processing each message block and compute `duration_ms = (time.monotonic() - start) * 1000` before calling `sink.record()`.
2. **Extract token counts from SDK messages:** When processing `AssistantMessage` blocks, check for usage metadata. The SDK's `ResultMessage` typically carries `input_tokens` and `output_tokens`. Extract these and populate `SpanRecord.input_tokens` / `SpanRecord.output_tokens`.
3. **Add columns to `TraceSpan` ORM model** (`persistence/models.py`):
   ```python
   duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
   input_tokens: Mapped[int] = mapped_column(Integer, default=0)
   output_tokens: Mapped[int] = mapped_column(Integer, default=0)
   attributes: Mapped[dict] = mapped_column(JSON, default=dict)
   ```
4. **Update `DbTraceSink.record()`** to persist all four new fields.
5. **Generate a DB migration** (Alembic or equivalent) to add the four columns to the `trace_spans` table.
6. **Update `SpanView`** API response model (`api/routes_tasks.py`) to expose `duration_ms` and token counts so operators can inspect them.
7. Add a test: after a task run with a mock sink, assert at least one span has `duration_ms > 0`.

---

### 4.3 Model routing applied at runtime (FR4.6)

**Severity:** ⚠️ Dead code

**PRD requirement (FR4.6):**
*"Cheap models for mechanical subtasks, frontier models for reasoning, behind one provider-neutral interface; routing decisions are traced."*

**What exists:**
`agent/routing.py` defines `MECHANICAL_TOOLS = {"repo_read", "repo_search", "review_lint"}` and `route_model(tool_name, settings) -> str`. In `_handle_message()`, `route_model()` is called and its result is written to `span.attributes["gen_ai.request.model"]`. The attribute is recorded in the span but has zero effect — the SDK session was started with a single `model=s.model` and that does not change per-tool.

**What is missing:**
The SDK does not support per-tool-call model overrides within a single session. The routing value exists only in span metadata, not in actual model dispatch.

**Implementation required:**

Two options — pick one:

**Option A: Per-request routing via separate sub-queries (recommended)**
1. Mechanical tools (`repo_read`, `repo_search`, `review_lint`) do not need the full orchestrating model. Instead of routing through the orchestrator, these tools can execute as direct SDK queries with `model=s.model_fast`:
   - In `op_repo_read()` and `op_repo_search()`, if the operation is too large for the fast model's context, fall back to `s.model`.
   - The `op_review_lint()` function already runs `ruff` deterministically — no model needed at all, routing is irrelevant here.
2. For tools that do require a model (e.g. a future `repo_summarize`), spawn them via `sdk_query(options=ClaudeAgentOptions(model=s.model_fast, ...))`.

**Option B: Dual-session architecture**
1. Maintain two SDK sessions per task: a `fast_session` (`model_fast`) and a `smart_session` (`model`).
2. The orchestrator decides which session to use based on `route_model(tool_name, settings)`.
3. Tool calls are dispatched to the appropriate session.
4. Both sessions share the same `TaskState` (passed by reference in `ToolContext`).

**Either way:**
- Routing decisions must be reflected in span `attributes["gen_ai.request.model"]` — this is already done; the value must also be accurate.
- Add a test: a task that calls `repo_read` uses `model_fast`, a task that calls `state_update` uses the frontier model.

---

### 4.4 Circuit breaker integration (FR4 / §8)

**Severity:** ⚠️ Dead code

**PRD requirement (FR4 / §8 Failure Modes):**
Circuit breakers are listed in the degradation strategy for model-tier failures. The circuit breaker is supposed to fail fast when a model endpoint is consistently unavailable, falling back to `fallback_model` or raising a `CircuitOpenError`.

**What exists:**
`reliability/circuit.py` implements a complete three-state (`closed → open → half_open`) circuit breaker with configurable `failure_threshold` and `reset_timeout_s`. `get_breaker(model)` returns a per-model singleton. `CircuitBreaker.call(fn, fallback_model=...)` handles fallback or raises `CircuitOpenError`.

**What is missing:**
Nothing in the run path calls `get_breaker()`. The circuit breaker is fully implemented and completely unwired.

**Implementation required:**

1. In `_run_with_retry()` (`worker/orchestrator.py`), wrap the SDK runner call with the circuit breaker:
   ```python
   breaker = get_breaker(settings.model)
   result = await breaker.call(
       runner, prompt=prompt, options=options,
       fallback_model=settings.fallback_model,
   )
   ```
2. The circuit breaker's `call()` method handles the async generator returned by `runner`. Verify that `_call()` in `circuit.py` correctly handles async generators (it checks `hasattr(result, "__aiter__")` — confirm this works with the SDK's streaming runner).
3. When `CircuitOpenError` is raised and there is no fallback, catch it in `run_task()` and set `state.status = TaskStatus.failed` with a descriptive finding.
4. Import `get_breaker` and `CircuitOpenError` in `orchestrator.py`.
5. Add tests:
   - 5 consecutive failures → circuit opens.
   - Open circuit with `fallback_model` → call proceeds on fallback.
   - After `reset_timeout_s`, circuit moves to `half_open` and probes.

---

### 4.5 Degradation ladder on budget exceeded (FR4.3 / §8)

**Severity:** ❌ Missing

**PRD requirement (FR4.3 / §8):**
*"Degradation ladder: full task → reduced model tier for mechanical steps → narrowed scope (smaller fix) → produce draft PR + diagnosis → clean terminal failure with reproducible trace. Never silent failure, never runaway spend."*

**What exists:**
`_finalize()` in `orchestrator.py` checks `"budget" in subtype or "max_turns" in subtype` and sets `state.status = TaskStatus.budget_exceeded`. Execution stops. No partial output is surfaced.

**What is missing:**
The entire degradation ladder. When a task exceeds its budget, it terminates silently with a status string. The operator and maintainer get no partial PR, no diagnosis, and no indication of what was completed before budget ran out.

**Implementation required:**

1. **Level 1 — Reduced model tier:** When `budget.total_used() > 0.7 * TOTAL_BUDGET` (70% consumed), switch subsequent tool calls to `model_fast` by updating `ClaudeAgentOptions` for the remaining turns. This requires passing the budget state into the orchestrator's turn loop.
2. **Level 2 — Narrowed scope:** At 85% budget, inject a `state_update` that rewrites the plan to target only the minimal fix (the first unresolved step).
3. **Level 3 — Draft PR on budget exceeded:** When `TaskStatus.budget_exceeded` is detected in `_finalize()`, attempt to open a draft PR with whatever state exists:
   ```python
   if result.status == TaskStatus.budget_exceeded and state.files_touched:
       draft = PRDraft(
           title=f"[DRAFT] {state.goal[:60]}",
           body=f"Budget exceeded after {result.turns} turns.\n\nPartial progress:\n{state.render_context()}",
           branch=current_branch,
       )
       # persist draft to DB, emit as span
   ```
4. **Level 4 — Clean terminal failure:** If no files were touched, emit a `SpanRecord(kind="degradation", outcome="budget_exceeded")` with the full `TaskState` snapshot as the summary. Surface this via the `/tasks/{id}/trace` API endpoint.
5. Add a test: a task runner that always exceeds budget produces a `PRDraft` with `[DRAFT]` in the title and a non-empty body when files have been touched.

---

## 5. Property 5 — Composable Tool Chains

### 5.1 `FileEdit` schema — wire or remove (FR5.2)

**Severity:** ⚠️ Dead code

**PRD requirement (FR5.2):**
*"Common types (`FileEdit`, ...) are shared, versioned schemas."* `FileEdit` is listed explicitly in the PRD's data shapes.

**What exists:**
`tools/schemas.py:51` defines `FileEdit(path: str, old_string: str, new_string: str)`. No tool uses it. `op_edit_apply()` accepts a plain `dict` (`args["path"]`, `args["old_string"]`, `args["new_string"]`) and returns `EditResult` — not `FileEdit`.

**What is missing:**
`FileEdit` is intended as the **input** schema for `edit_apply` — typed input for the composable chain (PR5.3: *"output of one tool becomes the typed input of the next"*). Currently the input is untyped dict.

**Implementation required:**

1. In `op_edit_apply()`, parse `args` into a `FileEdit` instance at the top of the function:
   ```python
   try:
       edit = FileEdit.model_validate(args)
   except ValidationError as e:
       return err(f"invalid edit args: {e}", deterministic=True)
   ```
2. Use `edit.path`, `edit.old_string`, `edit.new_string` throughout the function instead of direct `args["..."]` access.
3. Document in the `edit_apply` tool description that its input must conform to the `FileEdit` schema.
4. Add a contract test: calling `op_edit_apply()` with an invalid `FileEdit` (e.g. missing `path`) returns a typed `ToolOutcome(status=error)`, not an uncaught `KeyError`.

---

### 5.2 Structured tool chain piping (FR5.3)

**Severity:** ⚠️ Partial

**PRD requirement (FR5.3):**
*"Output schemas are designed to be directly consumable as inputs to downstream tools (composability is a design constraint, not luck)."* And: *"Does NOT pass raw, unstructured stdout/chat between steps as the integration contract. Does NOT require the model to re-parse free text to chain steps."*

**What exists:**
The `SecurityReport.blocking` flag → `vcs_open_pr.blocking` parameter is the main composition chain. It works — but only because the model reads the JSON payload, extracts `blocking`, and constructs a new `vcs_open_pr` call. The scaffolding does not enforce the chain structurally.

**What is missing:**
The orchestrator has no mechanism to pipe a typed output directly as typed input. The chain is entirely model-mediated: the model reads the JSON text of one tool result and manually constructs the args for the next. A confused or adversarially prompted model could break the chain.

**Implementation required:**

1. Add a `ToolChain` abstraction that can express: *"if `review_spawn_security` returns `SecurityReport(blocking=True)`, automatically invoke `vcs_open_pr(blocking=True)` as a guard"* — without relying on the model to make that connection:
   ```python
   @dataclass
   class ToolChain:
       trigger_tool: str
       trigger_condition: Callable[[dict], bool]
       downstream_tool: str
       arg_mapper: Callable[[dict], dict]
   ```
2. Implement a `CHAINS` list with the security → PR gate as the first entry:
   ```python
   CHAINS = [
       ToolChain(
           trigger_tool="review_spawn_security",
           trigger_condition=lambda payload: payload.get("blocking", False),
           downstream_tool="vcs_open_pr",
           arg_mapper=lambda _: {"blocking": True},
       )
   ]
   ```
3. In the orchestrator's `_handle_message()` or tool call handler, after each tool result, check all chains and inject a forced downstream call if a condition is met.
4. This is the "composability is a design constraint" clause — the chain is enforced by the scaffolding, not hoped for from the model.
5. Add a test: a `SecurityReport(blocking=True)` returned by the subagent automatically forces the `vcs_open_pr` gate, even if the model does not pass `blocking=True`.

---

## 6. Additional Missing Infrastructure

### 6.1 `repo_map` tool (§6.4)

**Severity:** ❌ Missing

**PRD requirement (§6.4):**
The `repo.*` namespace should include a map tool: *"never load the tree"*. The budget explicitly reserves 8,000 tokens for `repo_map`. Currently the budget region exists but nothing writes to it.

**What is missing:**
A `repo_map` tool that generates a compact, hierarchical view of the repository structure (directories, file counts, key entry points) sized to the `repo_map` budget region.

**Implementation required:**

1. Add `op_repo_map(ctx, args) → dict` in `core_ops.py`:
   - Walk `ctx.workspace` to build a directory tree, skipping `.git`, `.meridian`, `__pycache__`.
   - Format as indented text: `src/ (12 files)`, `  meridian/agent/ (4 files)`, etc.
   - Call `RegionBudget().allocate("repo_map", tree_text)` to size the output to the budget ceiling.
   - Return the budgeted tree as a `RepoSlice(files=all_paths, token_cost=estimated_tokens)`.
2. Register `repo_map` as a tool in `core_tools.py` with description: *"Get a compact map of the repo directory structure. Use at task start to understand layout. Input: none. Not for reading files (use repo_read) or searching (use repo_search)."*
3. Update `CORE_TOOL_NAMES` to include `"repo_map"`.
4. Track output against the `repo_map` budget region.

---

### 6.2 Alembic migrations (production scaffolding)

**Severity:** ❌ Missing

**PRD requirement (§4 NFR-Reproducibility):**
The persistence layer must be production-ready. Schema changes (e.g. adding `duration_ms`, `input_tokens` columns from §4.2) require versioned migrations.

**What is missing:**
There is no Alembic setup in the repository. `persistence/db.py` likely calls `Base.metadata.create_all()` (acceptable for Phase 0 development), but this approach drops and recreates the schema on each change, losing all task history.

**Implementation required:**

1. Initialize Alembic: `alembic init alembic` at the repo root.
2. Configure `alembic.ini` to use `MERIDIAN_DATABASE_URL` from settings.
3. Configure `env.py` to import `Base` from `persistence/models.py`.
4. Generate the initial migration from the current models.
5. Add `alembic upgrade head` to the Docker startup sequence in `docker-compose.yml`.
6. Document the migration workflow in `README.md`.

---

### 6.3 More eval fixtures (FR1.5 / §9)

**Severity:** ❌ Missing

**PRD requirement (§9):**
*"Held-out task set (issue→PR fixtures) runs on every change; release gated on pass-rate ≥ NFR-Correctness."*

**What exists:**
`evals/fixtures/` contains exactly one fixture: `issue_add_bug.json`. `load_fixtures()` in `run_evals.py` loads them, but the fixture-driven property evals (`eval_p1_wrong_tool_rate`, `eval_p1_novel_task`) don't exist yet (see §1.2).

**What is missing:**
A diverse fixture set covering: bug fixes, refactors, feature additions, security issues, and tasks with no obvious pattern (novel tasks). Minimum: 10 fixtures, at least 3 "novel" ones.

**Implementation required:**

1. Add fixtures for:
   - A bug fix that requires multi-file changes.
   - A refactor with no new functionality.
   - A security vulnerability report (tests FR2 isolation gate).
   - A novel task outside any common pattern (tests FR1.5 novel-task metric).
   - A task that should be blocked by the security subagent (tests the blocking gate).
2. Fixture format: `{"repo": "...", "issue_ref": "#N", "goal": "...", "expected_tools": [...], "expected_outcome": "succeeded|blocked"}`.
3. Update `eval_p1_wrong_tool_rate()` and `eval_p1_novel_task()` to consume the fixture set.

---

## 7. Implementation Priority

| # | Item | Property | Severity | Effort |
|---|---|---|---|---|
| 1 | Per-turn budget enforcement (§3.1) | P3 | ❌ Missing | M |
| 2 | Budget-pressure eviction policy (§3.2) | P3 | ❌ Missing | M |
| 3 | VCS idempotency (§4.1) | P4 | ⚠️ Partial | S |
| 4 | Span latency + token counts (§4.2) | P4 | ⚠️ Partial | M |
| 5 | Circuit breaker integration (§4.4) | P4 | ⚠️ Dead code | S |
| 6 | Model routing applied at runtime (§4.3) | P4 | ⚠️ Dead code | L |
| 7 | Degradation ladder (§4.5) | P4 | ❌ Missing | L |
| 8 | Tool retrieval wired into registry (§1.1) | P1 | ⚠️ Dead code | S |
| 9 | `FileEdit` input schema wired (§5.1) | P5 | ⚠️ Dead code | S |
| 10 | `ToolChain` structured piping (§5.2) | P5 | ⚠️ Partial | L |
| 11 | `repo_map` tool (§6.1) | P1/P3 | ❌ Missing | M |
| 12 | LLM-judge ambiguity audit (§1.2) | P1 | ❌ Missing | L |
| 13 | More eval fixtures (§6.3) | All | ❌ Missing | M |
| 14 | SDK-native agent path (§2.1) | P2 | ⚠️ Dead code | M |
| 15 | Subagent filesystem boundary (§2.2) | P2 | ⚠️ Partial | L |
| 16 | Alembic migrations (§6.2) | Infra | ❌ Missing | S |

**Effort:** S = < 1 day · M = 1–3 days · L = 3–5 days

---

*All items trace back to the main PRD's functional requirements. Each item in this document should be removed when its implementation is verified by the corresponding test passing in CI.*
