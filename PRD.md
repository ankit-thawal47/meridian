# Meridian — Product Requirements Document

> **Status:** Draft v1.0 · **Owner:** Ankit · **Date:** 2026-06-06
> **Type:** Technical PRD (product requirements + PRD-level architecture)
> **Runtime constraint:** Built on the **Claude Agent SDK** (sole agent runtime). Anthropic models are the default; the model layer is **not** vendor-locked.

---

## 0. How to read this document

Meridian is **not a product with a feature list. It is a system with properties.** Accordingly, this PRD is organized around the **five properties** the system must hold. Every functional requirement, architectural decision, and evaluation criterion derives from exactly one property:

1. **Model-Driven Tool Selection** — the model chooses the steps; the harness never hard-wires a workflow graph.
2. **Genuine Subagent Isolation** — specialized work runs in a real boundary (own context, scoped tools, independent failure).
3. **Long-Horizon Coherence** — the agent stays on-plan across a 20–40+ tool-call arc without context collapse.
4. **Production Scaffolding** — typed I/O, budgeted context, retry semantics, observability, reproducibility.
5. **Composable Tool Chains** — tool outputs are structured so the output of one becomes the typed input of the next.

For each property: **what the system does**, **what it explicitly does NOT do**, the **functional requirements**, and **how we know the property holds** (verification + metrics).

> **Guiding principle:** *The model makes every interesting decision. The scaffolding makes every interesting decision safe.* Neither half works without the other.

---

## 1. Overview

### 1.1 Problem
Most "agents" are pipelines pretending to be agents: a fixed sequence (read issue → search code → write fix → run tests → open PR) wired with conditional logic, where the model only fills in values. They break on novel tasks because the model does not choose the steps, lose coherence as the context window fills with raw tool output, and offer only cosmetic "specialization" (a function call dressed up as a sub-agent).

### 1.2 What Meridian is
Meridian is an **autonomous, long-horizon software-engineering agent** that owns the full loop from a GitHub issue to a production-ready pull request — with no human in the inner loop. It reads the issue, reasons over the codebase, implements a multi-file fix, validates it through execution and an **isolated** security review, and opens a PR with a complete description. The pipeline is an *emergent property of the model's reasoning over a coherent tool registry*, not a hand-wired graph.

### 1.3 One-sentence definition
> Meridian receives a goal — *fix this issue* — and is responsible for every decision between that goal and a merged pull request.

### 1.4 Why now (June 2026 AI-native best practices baked in)
- **Context engineering as a first-class discipline** — explicit token budgets, structured state, summarize-and-discard.
- **Claude Agent SDK** — production agent loop, native subagents, permission gating, hooks, automatic compaction, MCP tool integration, session resumption.
- **Model routing** — cheap/fast models for mechanical subtasks, frontier models for reasoning, behind a provider-neutral interface.
- **Evals-as-CI + LLM-as-judge with guardrails** — behavior is regression-tested, not vibe-checked.
- **Typed, composable tool I/O + deterministic replay** — agents become debuggable systems, not black boxes.
- **OpenTelemetry-style agent tracing** — every decision is observable and reproducible.

---

## 2. Goals & Non-Goals

### 2.1 Goals
- G1. Deliver a model-driven engine that completes real, novel issue→PR tasks across a 20–40+ tool-call horizon.
- G2. Hold all five properties under the full scale envelope (§4), demonstrably (not aspirationally).
- G3. Make specialization real via isolated subagents with scoped permissions and typed reports.
- G4. Keep context within an explicit budget so coherence does not degrade with task length.
- G5. Ship production scaffolding: retries, idempotency, observability, reproducibility, cost control.
- G6. Stay model-portable: Anthropic default, swappable provider behind one interface; **Claude Agent SDK is the only agent runtime.**

### 2.2 Non-Goals (explicitly out of scope)
- N1. Not a code-completion / autocomplete tool.
- N2. Not a post-hoc PR-review bot that runs after a human writes the code.
- N3. Not a pair-programming chatbot with a human in the inner loop.
- N4. Not a hand-wired workflow engine with a fixed step graph.
- N5. Not a multi-vendor agent framework — we standardize on **one** runtime (Claude Agent SDK) and route models beneath it.
- N6. Not a general DevOps/CD platform; Meridian's output is a PR, not a deploy.

---

## 3. Personas & Primary Flow

| Persona | Need from Meridian |
|---|---|
| **Maintainer** | Hand off well-scoped issues; receive a reviewable, correct PR with a clear description and passing checks. |
| **Platform/Infra owner** | Run many Meridian tasks concurrently within cost/latency/safety budgets; full observability. |
| **Security reviewer** | Trust that every change passed an isolated, permission-scoped security review with a typed report. |
| **Meridian operator (on-call)** | Diagnose a failed task from traces; reproduce deterministically; know whether failure was transient or deterministic. |

**Primary flow (happy path):** Issue ingested → TaskState initialized → model plans → reads/searches code → edits across files → runs tests/build → spawns SecuritySubagent (isolated) → consumes typed `SecurityReport` → finalizes → opens PR with description → reports terminal status.

---

## 4. Scale Envelope & Non-Functional Requirements

> ⚠️ **CONFIRM AGAINST ASSIGNMENT.** The literal numbers from the assignment did not reach this author. Values below are **labeled assumptions** chosen to be defensible defaults for this system class. **Replace each `[A]` with the assignment's figure before sign-off.** The architecture is parameterized so these are configuration, not redesign.

### 4.1 Scale dimensions (the axes that actually stress this system)
| # | Dimension | Default assumption `[A]` | Why it matters |
|---|---|---|---|
| S1 | **Concurrent tasks** (agents running in parallel) | `[A]` 100s–1,000s simultaneous | Drives the subagent runtime, isolation, and resource scheduling. |
| S2 | **Task horizon** (tool calls per task) | `[A]` 20–40 typical, 150 p99 | The core coherence challenge; context budget must survive the tail. |
| S3 | **Repo size** (files / LOC navigated) | `[A]` up to 10⁵ files / 10⁷ LOC | Repo map + retrieval must fit a token budget, not the whole tree. |
| S4 | **Tool registry size** | 50+ tools | Selection must stay unambiguous as the registry grows. |
| S5 | **Context window budget** | Fixed per model; allocated explicitly | Coherence fails when raw output is allowed to accumulate. |
| S6 | **Throughput** (issues/day) | `[A]` e.g. 10³–10⁴/day | Drives queueing, autoscaling, cost ceiling. |
| S7 | **Concurrency per repo/tenant** | `[A]` N tasks/repo | Worktree isolation + write-conflict handling. |
| S8 | **Subagent fan-out per task** | `[A]` 1–5 isolated subagents | Each consumes its own context window + tool budget. |

### 4.2 Non-functional requirements
- **NFR-Latency:** Time-to-PR p50 `[A]`, p95 `[A]`; first-tool-call latency p95 `[A]`.
- **NFR-Availability:** Control plane `[A]` (target 99.9%); a single task failure never cascades (NFR-Isolation).
- **NFR-Throughput:** Sustain S6 with autoscaling; graceful backpressure beyond ceiling (no silent drops).
- **NFR-Cost:** Per-task token/$ budget enforced; hard ceiling triggers degradation, not overrun (§9).
- **NFR-Correctness:** Eval suite pass-rate ≥ `[A]`% on the held-out task set before any release (§10).
- **NFR-Reproducibility:** Any completed/failed task is replayable from its trace + recorded model I/O.
- **NFR-Security:** Subagents cannot exceed granted permissions; no subagent can write outside its worktree.
- **NFR-Observability:** 100% of tool calls and model turns are traced with cost, latency, and outcome.

---

## 5. The Five Properties (core of the PRD)

### Property 1 — Model-Driven Tool Selection

**What the system does.** The orchestration loop is a `while not done` cycle: the model receives current `TaskState`, selects one or more tools, receives **structured** outputs, updates its plan, and continues. There is **no router, no keyword matcher, no hardcoded workflow graph.** The registry of 50+ tools is engineered so selection stays coherent and unambiguous: typed schemas, explicit operational semantics in every tool description, and namespace organization that eliminates overlap.

**What it explicitly does NOT do.**
- Does **not** classify the issue to pick a branch in a predefined flow.
- Does **not** fall back to a fixed sequence when uncertain.
- Does **not** let two tools have overlapping/ambiguous purpose.

**Functional requirements.**
- FR1.1 The loop exposes the full tool registry to the model every turn; the model alone decides the next call(s).
- FR1.2 Every tool has a typed input/output schema and a description stating *what it does, when to use it, when not to, and its side effects.*
- FR1.3 Tools are namespaced (e.g. `repo.*`, `edit.*`, `exec.*`, `vcs.*`, `review.*`) so no two overlap in purpose.
- FR1.4 The model may select **multiple independent tools in one turn** (parallel calls) when there are no data dependencies.
- FR1.5 Selection quality is measured, not assumed (see verification).

**How we know the property holds.**
- Registry **ambiguity audit**: an LLM-judge eval confirms each tool's description uniquely disambiguates it from all others (target: 0 ambiguous pairs).
- **Wrong-tool rate** on the eval set below threshold `[A]`.
- **Novel-task pass-rate**: tasks deliberately outside any "common pattern" still complete (proving steps weren't hard-wired).
- Code audit: grep-able proof there is no `switch(issueType)` / workflow-graph construct in the orchestrator.

---

### Property 2 — Genuine Subagent Isolation

**What the system does.** When Meridian needs a security review, it does not call a security *function* — it spawns a `SecuritySubagent` (via the Claude Agent SDK subagent primitive) in an **isolated git worktree**, with a **scoped, read-only** tool set, running a full analysis in **its own context window**, and returning a typed `SecurityReport` to the parent. The parent consumes that report as a structured input to the next tool. The subagent **cannot contaminate** the parent context, **cannot exceed** its permissions, and **can fail independently** without cascading.

**What it explicitly does NOT do.**
- Subagents do **not** share the parent's context window.
- Subagents do **not** inherit the parent's full tool permissions.
- A subagent failure does **not** crash or corrupt the parent task.
- Subagent work is **not** a same-process function call dressed up as an "agent."

**Functional requirements.**
- FR2.1 Each subagent runs with its own context window and its own model turn budget.
- FR2.2 Each subagent is granted a **scoped tool set** (least privilege); SecuritySubagent is read-only (no `edit.*`, no `vcs.write`).
- FR2.3 Subagents execute in an **isolated git worktree**; writes outside the worktree are impossible by construction.
- FR2.4 Subagents return a **typed report** (e.g. `SecurityReport { findings[], severity, blocking }`) — never raw chat text.
- FR2.5 Subagent failure returns a typed error the parent can handle; parent decides continue/abort.
- FR2.6 Subagent permissions and tool grants are declared, not implicit, and are enforced by the SDK permission layer + hooks.

**How we know the property holds.**
- **Isolation test:** a subagent attempting a write outside its worktree / a non-granted tool is **denied** (negative test must pass).
- **Context-contamination test:** parent context token count is unchanged by subagent execution except for the returned typed report.
- **Independent-failure test:** force a subagent crash; parent task survives and records a typed error.
- **Permission audit:** every subagent's effective tool set ⊆ its declared scope (automated).

---

### Property 3 — Long-Horizon Coherence

**What the system does.** Meridian treats the **context window as infrastructure**, not a side effect. It maintains a structured **`TaskState`** — current plan, files touched, tests run, findings — that is *always current, always compact, always authoritative*. Raw tool outputs are **summarized and discarded**; only structured conclusions persist. The window is **budgeted explicitly** (repo map = X tokens, TaskState = Y, recent tool outputs = Z), expressed in code, not left implicit.

**What it explicitly does NOT do.**
- Does **not** append raw tool output to the context indefinitely.
- Does **not** rely on the model to "remember" what happened from chat history.
- Does **not** let context growth be an emergent accident.

**Functional requirements.**
- FR3.1 A canonical `TaskState` object is the single source of truth for what has happened; updated after every tool call.
- FR3.2 Token budget is allocated per region (repo map / TaskState / recent outputs / system) and enforced before each turn.
- FR3.3 Raw tool outputs are **compacted to structured conclusions** and the raw form dropped from context once consumed.
- FR3.4 Repo context is a **map/retrieval slice**, never the whole tree; sized to its budget.
- FR3.5 SDK automatic compaction is configured and complemented by Meridian's explicit TaskState (defense in depth).
- FR3.6 On budget pressure, oldest/lowest-value regions are evicted by an explicit policy (not random truncation).

**How we know the property holds.**
- **Horizon stress test:** tasks at S2-p99 (150 tool calls) complete without coherence loss; plan-adherence score ≥ `[A]`.
- **Budget invariant:** assert total context ≤ budget at every turn (runtime invariant + test).
- **State-authority test:** reconstruct the full task purely from `TaskState` (no chat history) and confirm sufficiency.
- **Coherence metric:** measured drift between stated plan and executed actions stays below threshold across the arc.

---

### Property 4 — Production Scaffolding

**What the system does.** The scaffolding ensures tool outputs are typed and composable, context stays within budget, retries distinguish transient from deterministic failures, subagents run in isolation, cost is bounded, and **every decision is observable and reproducible.**

**What it explicitly does NOT do.**
- Does **not** retry deterministic failures blindly (no infinite loops on a real bug).
- Does **not** allow unbounded cost/token spend.
- Does **not** lose the trace of why a decision was made.

**Functional requirements.**
- FR4.1 **Retry semantics:** transient failures (timeout, rate-limit, 5xx) retried with backoff + jitter; deterministic failures (compile error, assertion) are **not** retried — they feed back into the model's reasoning.
- FR4.2 **Idempotency:** re-running a tool with the same inputs is safe; side-effecting tools (vcs, exec) are guarded against duplication.
- FR4.3 **Cost/budget control:** per-task token + $ ceiling; on breach, enter graceful degradation (§9), never silent overrun.
- FR4.4 **Observability:** every model turn and tool call emits a trace span with inputs (redacted), outputs, latency, cost, outcome.
- FR4.5 **Reproducibility:** model I/O + tool I/O + seed/config recorded so any task is deterministically replayable.
- FR4.6 **Model routing:** cheap models for mechanical subtasks, frontier models for reasoning, behind one provider-neutral interface; routing decisions are traced.
- FR4.7 **Hooks/guardrails:** PreToolUse/PostToolUse hooks enforce policy (e.g. block writes to protected paths, scrub secrets).

**How we know the property holds.**
- **Retry classification test:** injected transient vs. deterministic failures route correctly (100% on the fixture set).
- **Cost-ceiling test:** a runaway task is halted at the budget with a typed `BudgetExceeded` outcome.
- **Replay test:** a recorded task replays to an identical decision sequence.
- **Trace completeness:** 100% of tool calls/model turns appear in the trace (automated check).

---

### Property 5 — Composable Tool Chains

**What the system does.** Tool outputs are **structured** so the output of one tool becomes the **typed input** of the next. A `SecurityReport` from a subagent is consumed structurally by the finalize/PR tool; a `TestResult` feeds the model's next decision as typed data, not as a wall of stdout.

**What it explicitly does NOT do.**
- Does **not** pass raw, unstructured stdout/chat between steps as the integration contract.
- Does **not** require the model to re-parse free text to chain steps.
- Does **not** let tool contracts drift untyped/untested.

**Functional requirements.**
- FR5.1 Every tool returns a **typed, schema-validated** object; free-text is a field, never the contract.
- FR5.2 Common types (`FileEdit`, `TestResult`, `SecurityReport`, `RepoSlice`, `PRDraft`) are shared, versioned schemas.
- FR5.3 Output schemas are designed to be **directly consumable** as inputs to downstream tools (composability is a design constraint, not luck).
- FR5.4 Schema validation failures surface as typed errors, not silent malformed data.
- FR5.5 Tool I/O contracts are covered by contract tests in CI.

**How we know the property holds.**
- **Contract tests:** every tool's I/O validates against its schema in CI (must be green to ship).
- **Composition test:** representative chains (e.g. `exec.test → model decision → edit.apply`) pass end-to-end on typed data only.
- **No-free-text-contract audit:** no tool integration depends on parsing another tool's unstructured text.

---

## 6. System Architecture (PRD-level, lighter by design)

> Depth chosen: **PRD-level + high-level architecture.** Deep component design deferred to a follow-up Technical Design Doc (§13).

### 6.1 Runtime foundation
**Claude Agent SDK is the sole agent runtime.** Meridian uses, rather than reinvents: the SDK's agentic loop, custom-tool + MCP tool integration, **subagents**, **permission modes / `canUseTool` gating**, **hooks** (PreToolUse/PostToolUse), **automatic context compaction**, **session persistence/resumption**, and streaming. Meridian's own code adds: the `TaskState` discipline, explicit token budgeting, the typed tool/report schemas, retry classification, model routing, and observability/replay.

### 6.2 Components (logical)
```
┌────────────────────────────────────────────────────────────────────┐
│  Control Plane                                                       │
│  ┌──────────────┐   ┌──────────────┐   ┌───────────────────────┐    │
│  │ Issue Intake │──▶│  Task Queue  │──▶│  Scheduler / Autoscaler│   │
│  └──────────────┘   └──────────────┘   └───────────┬───────────┘    │
└────────────────────────────────────────────────────┼───────────────┘
                                                      │ leases a task
┌─────────────────────────────────────────────────────▼──────────────┐
│  Task Worker  (one per concurrent task — Claude Agent SDK)          │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Orchestration Loop  (while not done)                         │  │
│  │   model ↔ TaskState ↔ Tool Registry (50+, namespaced, typed)  │  │
│  │   ├─ Context Budgeter (repo map / state / recent outputs)     │  │
│  │   ├─ Retry Classifier (transient vs deterministic)            │  │
│  │   ├─ Model Router (Haiku/Sonnet/Opus, provider-neutral)       │  │
│  │   └─ Hooks/Guardrails (policy, secret scrub, path protection) │  │
│  └───────────────┬──────────────────────────────────────────────┘  │
│                  │ spawns (isolated worktree, scoped tools)         │
│        ┌─────────▼──────────┐   ┌──────────────────────┐            │
│        │ SecuritySubagent   │   │ (other subagents…)   │            │
│        │ read-only · own ctx│   │ scoped · own ctx     │            │
│        │ → SecurityReport   │   │ → typed report       │            │
│        └────────────────────┘   └──────────────────────┘            │
└─────────────────────────────────────────────────────────────────────┘
        │ traces/cost/outcome              │ git worktree per task
┌───────▼───────────────┐        ┌─────────▼──────────────────────────┐
│ Observability + Replay │        │ Repo / VCS layer (worktrees, PRs)  │
│ (OTel spans, recorder) │        │ (GitHub: issue read, branch, PR)   │
└────────────────────────┘        └────────────────────────────────────┘
```

### 6.3 Key data shapes (illustrative, versioned)
- `TaskState { goal, plan[], filesTouched[], testsRun[], findings[], budget, status }`
- `RepoSlice { files[], symbols[], tokenCost }` (retrieval/map, never whole tree)
- `TestResult { passed, failures[], stdoutRef }` (raw stdout stored by ref, not inlined)
- `SecurityReport { findings[], maxSeverity, blocking }`
- `PRDraft { title, body, branch, diffStat }`

### 6.4 Tool registry organization (50+)
Namespaced to eliminate overlap: `repo.*` (map, read, search), `edit.*` (apply, revert), `exec.*` (test, build, run), `vcs.*` (branch, commit, openPR), `review.*` (spawnSecurity, lint), `state.*` (update plan, record finding). Each tool description states purpose / when-to-use / when-not / side effects. (Property 1.)

---

## 7. Scaling Strategy (per dimension from §4.1)
- **S1 Concurrent tasks** — one stateless Task Worker per task, horizontally scaled; control-plane scheduler with leasing; autoscale on queue depth.
- **S2 Task horizon** — Property 3 (TaskState + budgeting) is the scaling mechanism; horizon scales with *budget discipline*, not bigger windows.
- **S3 Repo size** — repo **map + retrieval slice** sized to budget; never load the tree. Cache repo maps per commit.
- **S4 Tool registry** — coherence preserved via typed schemas + namespacing + ambiguity audit; registry can grow without retraining flow logic.
- **S5 Context budget** — explicit per-region allocation + eviction policy; SDK compaction as backstop.
- **S6 Throughput** — queue + autoscaler; backpressure (NFR) instead of silent drops; cost ceiling per task bounds spend.
- **S7 Per-repo concurrency** — git **worktree per task** isolates concurrent work on the same repo; write-conflict detection at PR open.
- **S8 Subagent fan-out** — each subagent is a budgeted unit; scheduler accounts for subagent context/tool cost when admitting tasks.

---

## 8. Failure Modes & Degradation
| Failure | Detection | Response |
|---|---|---|
| Transient (timeout/rate-limit/5xx) | Retry classifier | Backoff+jitter retry (FR4.1) |
| Deterministic (compile/test error) | Retry classifier | **Feed back to model**, do not retry blindly |
| Budget exceeded | Context budgeter / cost meter | Graceful degradation → typed `BudgetExceeded`, summarize-and-stop, surface partial PR/draft |
| Subagent crash | Typed subagent error | Parent survives; decide continue/abort (FR2.5) |
| Coherence drift | Plan-adherence monitor | Re-anchor from `TaskState`; if unrecoverable, terminate with diagnosis |
| Write conflict at PR | VCS layer | Rebase/abort with typed outcome; never force-push |
| Tool schema violation | Schema validation | Typed error, no malformed propagation (FR5.4) |

**Degradation ladder:** full task → reduced model tier for mechanical steps → narrowed scope (smaller fix) → produce **draft PR + diagnosis** → clean terminal failure with reproducible trace. Never silent failure, never runaway spend.

---

## 9. Observability, Evals & Cost
- **Tracing:** OTel-style span per model turn + tool call (inputs redacted, outputs, latency, cost, outcome). 100% coverage (FR4.4).
- **Replay:** recorded model+tool I/O enables deterministic replay of any task (FR4.5).
- **Evals-as-CI:** held-out task set (issue→PR fixtures) runs on every change; release gated on pass-rate ≥ NFR-Correctness. Property-specific evals: registry ambiguity audit (P1), isolation/permission negative tests (P2), horizon stress test (P3), retry/budget/replay tests (P4), contract tests (P5).
- **LLM-as-judge with guardrails:** PR quality + plan-adherence scored by judge models with rubric; judges themselves validated against human labels.
- **Cost dashboards:** per-task and aggregate token/$ with budget-breach alerts.

---

## 10. Security & Permissions
- **Least privilege:** every (sub)agent gets the minimal tool set; SecuritySubagent is read-only.
- **Worktree confinement:** writes impossible outside the task's worktree (FR2.3).
- **Hooks enforce policy:** block writes to protected paths, scrub secrets from traces, deny disallowed tools at `canUseTool`.
- **Isolated security review** is a required gate before PR open; a `blocking` `SecurityReport` halts finalization.
- **Auditability:** every permission grant + denial is traced.

---

## 11. Rollout Plan (phased)
- **Phase 0 — Walking skeleton:** SDK loop + 5–8 core tools, `TaskState`, single task end-to-end on a toy repo. Proves Properties 1 & 3 minimally.
- **Phase 1 — Isolation:** SecuritySubagent in worktree with scoped tools + typed report. Proves Property 2.
- **Phase 2 — Scaffolding:** retry classifier, budget ceiling, tracing, replay, model routing. Proves Property 4.
- **Phase 3 — Composability + registry to 50+:** typed schemas, contract tests, ambiguity audit. Proves Property 5 + hardens Property 1.
- **Phase 4 — Scale:** control plane (queue/scheduler/autoscaler), concurrency to S1, evals-as-CI gating. Hits the §4 envelope.
- **Phase 5 — Hardening:** degradation ladder, write-conflict handling, cost dashboards, on-call runbooks.

Each phase exits only when its property's **"how we know it holds"** checks are green.

---

## 12. Success Metrics
- **Task success rate** (issue→merged-able PR) ≥ `[A]` on held-out set.
- **Novel-task success rate** ≥ `[A]` (guards against hidden pipelines).
- **Coherence at S2-p99** (150 tool calls) — plan-adherence ≥ `[A]`.
- **Isolation guarantees** — 100% of isolation/permission negative tests pass.
- **Reproducibility** — 100% of tasks replay deterministically.
- **Cost adherence** — 0 tasks exceed budget ceiling; p95 cost/task ≤ `[A]`.
- **Trace completeness** — 100%.
- **Throughput @ scale** — sustain S6 at NFR latencies.

---

## 13. Open Questions & Assumptions to Confirm
**Must confirm against the assignment (Pasted text #3):**
1. The literal **scale numbers** for S1–S8 and all `[A]` placeholders (§4, §12).
2. Required **latency SLOs** and **availability target**.
3. **Throughput** (issues/day) and any **cost ceiling**.
4. Target **repos/tenancy** model (single org vs multi-tenant).
5. Required **eval pass-rate** for release.

**Design questions to resolve in the Technical Design Doc:**
6. Eviction policy specifics under context pressure (LRU by region vs value-scored).
7. Model-routing policy (which subtasks → which tier) and the provider-neutral interface shape.
8. Repo-map strategy (static index vs on-demand retrieval) and cache invalidation per commit.
9. Worktree lifecycle / cleanup and per-repo concurrency limits.
10. Which additional subagents beyond Security are first-class (e.g. test-author, refactor).

---

*Appendix A — derivation check: every FR above traces to exactly one of the five properties; every property has explicit "does NOT do" anti-requirements and binary "how we know it holds" verification. This is intentional and should be preserved on edits.*
