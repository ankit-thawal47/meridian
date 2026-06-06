# Meridian — Implementation Plan

> Companion to `PRD.md` (the *what/why*). This file is the *how*: a phased build plan for a FastAPI + Python implementation on the **Claude Agent SDK (Python)**.

## Context

We are building **Meridian** — an autonomous, long-horizon software-engineering agent that takes a GitHub issue to a production-ready PR with no human in the inner loop. The PRD frames Meridian as a *system with five properties* (model-driven tool selection, genuine subagent isolation, long-horizon coherence, production scaffolding, composable tool chains), not a feature list. This plan turns those properties into a concrete Python codebase.

The repo is **greenfield** (only `PRD.md` exists). Decisions locked with the user: **FastAPI/Python backend**, **Claude Agent SDK (Python) as the sole agent runtime** (Anthropic default, model layer not vendor-locked), **arq + Redis** for async agent workers, **Postgres + Redis** for state/traces/queue/cache, **GitHub App + webhooks** for intake, and a **full-system plan sequenced into phased milestones (Phase 0→5)**.

Why this shape: agent tasks run for minutes across 20–40+ tool calls, so they cannot run inside an HTTP request — the FastAPI control plane only ingests/enqueues/queries, while arq workers run the SDK agent loop asynchronously. State must be durable and replayable, hence Postgres; the queue and repo-map cache live in Redis.

## Goals

- Implement the §6 architecture from `PRD.md` so all five properties demonstrably hold.
- FastAPI control plane (intake, status, replay) + arq agent workers (the `while not done` loop).
- Build incrementally; each phase exits only when its property's "how we know it holds" checks are green.
- Keep the model layer swappable behind one interface; standardize on the Claude Agent SDK runtime.

## Tech Stack & Key Decisions

| Concern | Choice |
|---|---|
| Web framework | **FastAPI** (async), `uvicorn`/`gunicorn` |
| Agent runtime | **`claude-agent-sdk` (Python)** — agent loop, custom tools, subagents, permissions, hooks, compaction |
| Async workers | **arq** (asyncio-native, Redis broker) — one task per worker job |
| Durable store | **Postgres** (TaskState, traces, replay records, PR drafts) via SQLAlchemy 2.0 async + Alembic |
| Cache/queue | **Redis** (arq queue, repo-map cache, rate-limit/idempotency keys) |
| GitHub | **GitHub App** + webhooks; `PyGithub`/`githubkit` + git CLI for worktrees |
| Validation/schemas | **Pydantic v2** for all typed tool I/O and reports (Property 5) |
| Observability | **OpenTelemetry** SDK → OTLP; structured logging (`structlog`) |
| Config | `pydantic-settings`; secrets via env / secret manager |
| Packaging/deps | **uv** + `pyproject.toml` |
| Tests/evals | `pytest` + `pytest-asyncio`; eval harness runs issue→PR fixtures in CI |
| Containerization | Docker; `docker-compose` for local (api + worker + postgres + redis) |

> **SDK API note:** confirm exact `claude-agent-sdk` surface against current docs before coding — `ClaudeAgentOptions`, custom tools (`@tool` / `create_sdk_mcp_server`), subagents (`AgentDefinition`), `can_use_tool` permission callback, `permission_mode`, and `PreToolUse`/`PostToolUse` hooks. The design below depends only on these primitives existing; names may need adjusting.

## Proposed Project Structure

```
meridian/
  pyproject.toml                # uv-managed deps
  docker-compose.yml            # api + worker + postgres + redis
  alembic/                      # migrations
  src/meridian/
    main.py                     # FastAPI app factory
    config.py                   # pydantic-settings
    api/
      routes_tasks.py           # POST /tasks (manual trigger), GET /tasks/{id}, GET /tasks/{id}/trace, POST /tasks/{id}/replay
      routes_webhooks.py        # GitHub App webhook → enqueue
      deps.py                   # DB/redis sessions
    control_plane/
      intake.py                 # validate issue, create Task row, enqueue arq job
      scheduler.py              # arq settings, concurrency limits, backpressure
    worker/
      runner.py                 # arq job: builds SDK agent, runs loop to terminal status
      orchestrator.py           # the while-not-done loop wiring (Property 1)
    agent/
      sdk_session.py            # ClaudeAgentOptions, model routing, hooks wiring
      task_state.py             # TaskState (Pydantic) — authoritative, compact (Property 3)
      context_budget.py         # per-region token budgeting + eviction policy (Property 3)
      retry.py                  # transient-vs-deterministic classifier (Property 4)
      model_router.py           # Haiku/Sonnet/Opus selection behind one interface (Property 4)
      hooks.py                  # PreToolUse/PostToolUse: path protection, secret scrub (Property 4/10)
    tools/                      # the 50+ registry, namespaced, typed (Property 1 & 5)
      registry.py               # registration + ambiguity audit hook
      repo.py  edit.py  exec.py  vcs.py  review.py  state.py
      schemas.py                # FileEdit, TestResult, SecurityReport, RepoSlice, PRDraft (Pydantic)
    subagents/
      base.py                   # spawn-in-worktree, scoped tools, typed report (Property 2)
      security.py               # SecuritySubagent (read-only) → SecurityReport
    repo/
      worktree.py               # git worktree per task; confinement
      repo_map.py               # map/retrieval slice sized to budget; Redis cache per commit
    persistence/
      models.py                 # SQLAlchemy: Task, TraceSpan, ReplayRecord, PRDraft
      repository.py             # data access
    observability/
      tracing.py                # OTel spans per model turn + tool call
      replay.py                 # record model+tool I/O; deterministic replay
    evals/
      fixtures/                 # issue→PR task fixtures
      run_evals.py              # CI-gated pass-rate; property-specific suites
  tests/
```

## Component Design (mapped to the five properties)

- **Property 1 — Model-Driven Tool Selection** → `worker/orchestrator.py` runs a pure `while not done` loop: pass `TaskState` + full registry to the SDK, the model picks tool(s), structured outputs come back, state updates, repeat. **No router/keyword/graph.** `tools/registry.py` enforces namespacing (`repo.* edit.* exec.* vcs.* review.* state.*`) and runs an LLM-judge **ambiguity audit** over tool descriptions.
- **Property 2 — Genuine Subagent Isolation** → `subagents/base.py` spawns a subagent via the SDK with its **own context window**, a **scoped tool set** (least privilege), inside a **dedicated git worktree** (`repo/worktree.py`), returning a **typed Pydantic report**. `subagents/security.py` is read-only (no `edit.*`/`vcs.write`) and emits `SecurityReport`. Negative tests prove writes/non-granted tools are denied and parent context is untouched.
- **Property 3 — Long-Horizon Coherence** → `agent/task_state.py` is the single authoritative, compact state; `agent/context_budget.py` allocates tokens per region (repo map / state / recent outputs / system) and evicts by explicit policy. Raw tool outputs are summarized into `TaskState` and dropped; SDK auto-compaction is the backstop.
- **Property 4 — Production Scaffolding** → `agent/retry.py` (transient backoff vs deterministic feedback), `agent/model_router.py`, `agent/hooks.py` (policy/secret scrub/path protection), cost+budget ceiling in the loop, `observability/tracing.py` (100% span coverage), `observability/replay.py` (deterministic replay).
- **Property 5 — Composable Tool Chains** → `tools/schemas.py` defines shared, versioned Pydantic types so each tool output is the typed input of the next (e.g. `SecurityReport` → `vcs.open_pr`; `TestResult` → next model decision). Contract tests in CI; raw stdout stored by reference, never as the integration contract.

## Data Model (Postgres, illustrative)

- `tasks` — id, repo, issue_ref, status, budget, plan (jsonb TaskState snapshot), created/updated.
- `trace_spans` — id, task_id, kind (model_turn|tool_call), name, inputs_redacted, outputs, latency_ms, cost, outcome, ts.
- `replay_records` — task_id, ordered model+tool I/O + config/seed for deterministic replay.
- `pr_drafts` — task_id, title, body, branch, diff_stat, status.
- Queue + repo-map cache + idempotency keys live in **Redis** (not Postgres).

## Execution Flow

1. GitHub webhook → `routes_webhooks.py` verifies signature → `intake.py` creates `Task` → enqueues arq job (idempotency key on issue+commit).
2. arq worker `runner.py` loads `Task`, builds SDK session (`sdk_session.py`) with registry + hooks + model router + budget.
3. `orchestrator.py` runs the loop: model selects tool(s) → typed outputs → `TaskState` update → budget/cost check → repeat. Spawns `SecuritySubagent` when the model decides to.
4. On a non-blocking `SecurityReport`, model finalizes → `vcs.open_pr` produces `PRDraft` → opens PR.
5. Terminal status + full trace persisted; replay available via API.

## Phased Milestones (each gated on its property's PRD verification)

- **Phase 0 — Walking skeleton:** uv project, FastAPI app, Postgres+Redis via compose, arq worker, SDK loop with 5–8 core tools (`repo.read/search`, `edit.apply`, `exec.test`, `state.update`), `TaskState`. One task end-to-end on a toy repo via `POST /tasks`. *(Proves P1 & P3 minimally.)*
- **Phase 1 — Isolation:** `subagents/base.py` + `security.py` in worktree, scoped read-only tools, `SecurityReport`. *(Proves P2 — incl. isolation/permission negative tests.)*
- **Phase 2 — Scaffolding:** retry classifier, cost/budget ceiling, OTel tracing, replay recorder, model router, hooks. *(Proves P4 — retry/budget/replay tests.)*
- **Phase 3 — Composability + registry to 50+:** full `tools/schemas.py`, contract tests, namespacing, ambiguity audit. *(Proves P5; hardens P1.)*
- **Phase 4 — Scale + intake:** GitHub App webhooks, scheduler concurrency limits + backpressure, autoscaling workers, evals-as-CI gating. *(Hits the §4 scale envelope once assignment numbers are filled in.)*
- **Phase 5 — Hardening:** degradation ladder, write-conflict handling at PR open, cost dashboards, runbooks.

## Reuse / Don't Reinvent

- Use the **Claude Agent SDK** agentic loop, subagents, permission callback, hooks, and compaction — do **not** hand-roll an agent loop.
- Use **arq** retry/scheduling for the *job* layer; the *agent-step* retry classifier is Meridian-specific (different concern).
- Use **Pydantic v2** everywhere for typed tool I/O (Property 5) — one schema source, validated in CI.
- Use **git worktrees** (native) for subagent confinement — no custom sandbox.

## Verification (how we test end-to-end)

- **Local:** `docker-compose up` (api + worker + postgres + redis); `POST /tasks {repo, issue}` against a seeded toy repo; assert a PR draft is produced and `GET /tasks/{id}/trace` shows the full tool/model span sequence.
- **Property tests (CI):** P1 registry ambiguity audit (0 ambiguous pairs) + wrong-tool rate; P2 negative isolation/permission tests + parent-context-unchanged assertion; P3 150-tool-call horizon stress test + context-budget invariant; P4 retry-classification + budget-ceiling + deterministic-replay tests; P5 contract tests for every tool schema.
- **Evals-as-CI:** `evals/run_evals.py` runs issue→PR fixtures, gates release on pass-rate ≥ target (from assignment).
- **Reproducibility:** replay a recorded task and assert identical decision sequence.

## Open Items / Dependencies

1. **Assignment scale numbers** still pending — needed to set arq concurrency, autoscaling targets, latency SLOs, cost ceiling, and eval pass-rate (the `[A]` placeholders in `PRD.md` §4/§12).
2. ~~Confirm exact `claude-agent-sdk` (Python) API surface.~~ **RESOLVED (2026-06-06):** verified against code.claude.com docs. Imports: `query, ClaudeSDKClient, ClaudeAgentOptions, tool, create_sdk_mcp_server, AgentDefinition, PermissionResultAllow, PermissionResultDeny`. Tools via `@tool(name, desc, schema)` + `create_sdk_mcp_server` (referenced as `mcp__<server>__<tool>`). Subagents via `agents={name: AgentDefinition(tools=, disallowedTools=, permissionMode=, maxTurns=, model=)}`. Permissions via `can_use_tool(tool_name, input, ctx)->PermissionResult` + `permission_mode`. **The SDK owns the agent loop** — Meridian's orchestrator wraps the message stream (does NOT hand-roll the loop). Native `max_budget_usd` + `max_turns` provide the Property-4 cost/turn ceiling. `sandbox: SandboxSettings` available for isolation.
3. Model-routing policy specifics (which subtasks → which tier).
4. Repo-map strategy (static index vs on-demand retrieval) + cache invalidation per commit.
5. Eviction policy under context pressure (LRU-by-region vs value-scored).
```
