# Meridian

Autonomous, long-horizon software-engineering agent: it takes a GitHub issue to a
production-ready pull request with no human in the inner loop. Built on the
**Claude Agent SDK** (sole agent runtime; Anthropic models by default, layer not
vendor-locked).

Meridian is a *system with five properties*, not a feature list — see
[`PRD.md`](PRD.md). Build plan: [`Plans/`](Plans/).

| Property | Where it lives |
|---|---|
| 1. Model-driven tool selection | `tools/registry.py`, `worker/orchestrator.py` |
| 2. Genuine subagent isolation | `repo/workspace.py`, `tools/context.py` (Phase 1: `subagents/`) |
| 3. Long-horizon coherence | `agent/task_state.py` |
| 4. Production scaffolding | `observability/tracing.py`, SDK budget ceilings in `agent/sdk_session.py` |
| 5. Composable tool chains | `tools/schemas.py`, `tools/core_ops.py` |

## Architecture (Phase 0)

```
POST /tasks ──> intake ──> arq queue (Redis) ──> worker
                  │                                  │
              Postgres (Task, TraceSpan)        prepare workspace
                                                     │
                                          orchestrator wraps SDK loop
                                          (registry of typed tools, TaskState,
                                           budget ceiling, trace spans)
```

The FastAPI control plane only ingests/queries; the agent loop runs out-of-band
in an arq worker because tasks run for minutes across 20–40+ tool calls.

## Quickstart (local)

```bash
# 1. install
make install              # uv venv + editable install with dev deps

# 2. infra
make up                   # postgres + redis via docker compose

# 3. run control plane + a worker (separate shells)
export ANTHROPIC_API_KEY=sk-ant-...
make api                  # http://localhost:8000  (docs at /docs)
make worker

# 4. submit a task against a LOCAL repo path (Phase 0)
curl -s localhost:8000/tasks -H 'content-type: application/json' -d '{
  "repo": "/abs/path/to/toy-repo",
  "issue_ref": "#1",
  "goal": "The add() function returns a-b instead of a+b. Fix it and make tests pass."
}'

# 5. inspect
curl -s localhost:8000/tasks/<task_id>
curl -s localhost:8000/tasks/<task_id>/trace
```

## Tests

```bash
make test     # full suite (SDK-gated tests run when claude-agent-sdk is installed)
make lint
make typecheck
```

Unit tests run without the SDK installed (the agent loop is injected as a fake
stream); SDK-gated tests auto-skip when `claude-agent-sdk` is absent.

## Status

Phase 0 (walking skeleton) — control plane, arq worker, SDK agent loop with five
typed namespaced tools, authoritative `TaskState`, trace persistence. Phases 1–5
(isolation, scaffolding, composability, scale, hardening) are in `Plans/`.

> Scale targets in `PRD.md` §4/§12 carry `[A]` placeholders pending the
> assignment's concrete numbers.
