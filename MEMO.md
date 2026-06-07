# Meridian — Build Memo

**Domain:** Autonomous software-engineering agent — GitHub issue → production pull request, no human in the inner loop.

---

## What was built

Meridian receives a goal (*fix this issue*) and owns every decision between that goal and a merged pull request. The pipeline is an emergent property of the model's reasoning over a coherent tool registry, not a hand-wired graph.

**Core loop.** An arq worker dequeues a task, prepares an isolated git worktree, and hands control to the Claude Agent SDK. The SDK drives a `while not done` loop; Meridian's orchestrator streams messages, emits an OTel-style `SpanRecord` per model turn and tool call, and writes terminal state to Postgres. The HTTP layer (FastAPI) never touches the agent; it only enqueues tasks and exposes status/trace endpoints.

**50 tools across 9 namespaces** — `repo_*` (9), `edit_*` (5), `exec_*` (8), `state_*` (5), `vcs_*` (3), `review_*` (2), `analysis_*` (8), `doc_*` (5), `issue_*` (5). Above a threshold of 20 tools the registry activates keyword-overlap retrieval (`select_tools`), loading only the top-12 most relevant schemas into the MCP server for the task. The model selects freely within that set; the harness never dispatches by issue type.

**Genuine subagent isolation.** `review_spawn_security` calls `sdk_query()` with its own `ClaudeAgentOptions`: a separate MCP server (`meridian_sec`) exposing only `repo_read` + `repo_search`, an explicit `disallowed_tools` list covering every write surface, `max_turns=15`, and its own context window SDK-guaranteed separate from the parent. It returns a pydantic-validated `SecurityReport`; the parent reads `report.blocking` and gates `vcs_open_pr` on it. A function call with a different name does not satisfy this — the isolation is enforced by the SDK session boundary.

**Long-horizon coherence.** `TaskState` is the single authoritative source. `render_context()` injects a compact snapshot every turn, bounded by `RegionBudget` (system 2 K, repo\_map 8 K, task\_state 6 K, recent\_outputs 10 K, total 30 K). Raw stdout from `exec_test` and `exec_run` is stored by `blob:` reference and never inlined. The budget enforcement is in the code — `RegionBudget.allocate()` truncates at the ceiling before the text ever reaches the SDK. End-to-end verified at 21 turns with plan coherence intact.

**Production scaffolding.** Full Jitter exponential backoff (`reliability/retry.py`) with deterministic vs. transient failure classification. `RateLimitedClient` caps concurrent GitHub API calls at 3 and parses `Retry-After` headers rather than guessing a sleep duration. Idempotency cache on `edit_apply` and `exec_test` (SHA-256 key over args). CaMeL-style prompt injection quarantine wraps issue text in hard delimiters before it enters the SDK prompt. SDK hooks (`PreToolUseHook`, `PostToolUseHook`) enforce the allowed-tools list at the hook layer as a second guard. OTel-style spans persisted to Postgres. 121 tests across unit and integration paths; property eval harness (`evals/run_evals.py`) with five property-specific checks that run in CI.

**Composable tool chains.** Every tool returns `ToolOutcome` wrapping a typed pydantic payload. `SecurityReport.blocking` → `vcs_open_pr(blocking=True)` is the canonical chain: the parent reads a typed field from one tool's output and passes it as a typed argument to the next. No free-text blobs as integration contracts.

---

## What was cut

**Circuit breaker unwired.** `reliability/circuit.py` implements `CircuitBreaker` with half-open probing and per-model keying. `get_breaker(model)` is never called in the run path. The module was built before the SDK's own budget/error handling made it partially redundant; wiring it to the Anthropic client calls is a one-session task.

**OTel token and latency fields are zero.** `SpanRecord` has `input_tokens`, `output_tokens`, and `duration_ms` fields. The SDK's `ResultMessage` exposes `total_cost_usd` and `num_turns` but not per-turn token counts at the streaming layer; the fields are emitted as zero rather than fabricated. Real per-span token accounting requires either the Anthropic Bedrock streaming headers or a wrapper around the SDK's internal HTTP client.

**Model routing is logged, not applied.** `agent/routing.py` maps tool names to model tiers (fast/standard/frontier) and writes the recommended model into span attributes. The orchestrator records it but does not change which model executes. Wiring it requires per-tool `ClaudeAgentOptions` overrides on tool-use responses, which the SDK supports but which was not reached.

**LLM-judge ambiguity audit is missing.** `evals/run_evals.py` checks that the orchestrator source contains no hardwired dispatch strings (`if issue_type`, `workflow_graph`), but does not use a judge model to verify that each tool description uniquely disambiguates it from all others. This is the strongest evidence for Property 1 at scale; it requires a small fixture set and a haiku-class judge call per description pair.

**Nested worktree failure is unhandled.** When the target repo is itself a git worktree (`.git` is a file pointer, not a directory), `git worktree add --detach` fails silently and the task stays `pending`. The fix is a one-line check — detect the file vs. directory distinction and fall back to `shutil.copytree` — but it was deferred after confirming it was an environment-specific edge case.

**`state_update` call discipline.** The agent completes analysis tasks but does not reliably call `state_update` before finishing, leaving the DB findings list empty even when the result text is substantive. This is a system prompt enforcement gap, not a tool failure.

---

## What additional time would have addressed

**Per-turn budget assertion in the orchestrator.** `RegionBudget` enforces ceilings when `render_context()` is called, but the orchestrator does not assert `budget.within_budget()` after each turn and raise if the invariant breaks. Adding this as a hard check in `_handle_message` would make context overruns visible rather than silent.

**A real long-horizon eval with a live model.** The 60-call test in `test_orchestrator_logic.py` uses a fake async generator. The proof that coherence holds at 20+ turns is the live E2E run (21 turns, $0.78, coherent conclusion), not an automated test. A parameterized fixture set with known multi-step issues and an automated coherence scorer (checking that each plan step is marked done before moving to the next) would make this a repeatable CI gate rather than a one-off demonstration.

**Session resumption on worker crash.** The SDK supports resuming a session from a prior message list. If the arq worker crashes mid-task, the task stays `running` and is never retried. Implementing resume requires persisting the SDK message stream incrementally to Postgres and passing it back to `sdk_query()` on restart.

**GitHub webhook end-to-end.** `control_plane/intake.py` parses `issues.opened` webhooks and enqueues tasks. The handler is complete but was tested only with a manually crafted `curl`; a Smee.io or ngrok tunnel pointing at the running API was not demonstrated.

---

## One design decision I would defend

**`TaskState` as the sole context authority, not conversational history.**

The alternative a reasonable engineer would reach for is passing the full message history back to the SDK each turn — letting the model's own context window accumulate the record of what happened. Most agent frameworks do this by default.

The problem is that full-history accumulation is exactly what the research identifies as the primary failure mode for long-horizon tasks: context rot, lost-in-the-middle degradation, distraction from accumulated tool output, and poisoning when an early error gets repeated by the model citing its own prior turn. The Chroma context-rot study shows every frontier model degrades well before its advertised window, and the degradation is non-linear.

`render_context()` inverts this. Every turn starts from a compact, structured snapshot: the current plan (with done flags), the last N findings, files touched, and cost. Raw stdout is stored by `blob:` reference and never re-injected. The snapshot is token-budgeted at the ceiling before it reaches the SDK. The model cannot hallucinate a finding that wasn't recorded via `state_update` because the finding does not exist in the context if it wasn't written.

The cost is that the model must call `state_update` to persist conclusions — it cannot rely on the conversational record. In practice this creates the enforcement gap noted above. But the alternative — unbounded history — guarantees coherence collapse on long tasks regardless of prompt quality. A structured write discipline is fixable; context rot at turn 30 is not.
