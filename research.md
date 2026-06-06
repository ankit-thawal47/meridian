# Where AI Applications Break — Failure Modes, Root Causes, and Advised Solutions

> Research compiled for **Meridian**. Structure per failure mode: **(a) what it is → (b) the underlying reason/root cause → (c) plausible solutions advised in the literature**, grouped by theme. The final section maps the highest-leverage failure modes onto Meridian's five properties.
>
> **Method & verification.** Findings were gathered by parallel theme-scoped research agents reading primary sources (arXiv papers + primary engineering write-ups), then **every load-bearing URL below was HTTP-verified (200 OK)** by the author. The OpenAI hallucination post returns 403 to automated fetches but is live; it is cited via its verified arXiv mirror. A handful of agent-surfaced, future-dated arXiv IDs that could not be independently read were **excluded** rather than cited. Secondary/practitioner figures are labeled as such.

---

## Executive summary — the five root causes underneath everything

Most production AI failures reduce to five structural facts about today's models:

1. **Attention is a finite, non-uniform budget.** Models do not use long context uniformly; quality degrades as input grows, well before the advertised window. → context-rot, lost-in-the-middle, tool-overload.
2. **Errors compound multiplicatively over steps.** Task success ≈ (per-step reliability)^steps, and worse when step errors are correlated. → long-horizon collapse.
3. **There is no instruction/data channel separation.** Instructions and untrusted data share one token stream. → prompt injection is structural, not a bug.
4. **Training and evaluation reward confident guessing over abstention.** → hallucination persists by incentive design.
5. **The system is non-deterministic and the failure surface is organizational, not just model-level.** → multi-agent coordination failures, eval gaps, reliability engineering.

Everything below is a specialization of these five.

---

## Part I — Context & Long-Horizon Execution Failures

### I.1 Lost in the Middle (positional / U-shaped attention)
- **What:** Retrieval accuracy depends on *where* the relevant info sits in the context. Performance is highest when it's at the **start or end**, and drops sharply in the **middle** — a U-shaped curve — even in long-context models.
- **Root cause:** Positional bias in how transformers attend over long inputs; models do not use their context uniformly, and degradation appears even when the needle is provably in-context.
- **Solutions:** Re-rank so the most relevant documents sit at the context **edges**; keep retrieved sets small and relevant rather than maximally long; test the real long-context behavior rather than trusting the advertised window.
- **Source:** Liu et al., *Lost in the Middle: How Language Models Use Long Contexts*, 2023 — https://arxiv.org/abs/2307.03172

### I.2 Context Rot (length-driven, non-uniform degradation)
- **What:** Across **18 frontier models** (Claude 4, GPT-4.1, Gemini 2.5, Qwen3), *every* model degrades as input length grows — even on simple tasks, and well before the limit (a 1M-token model already rots near ~50K).
- **Root cause:** Non-uniform token processing. Difficulty rises with (a) lower semantic similarity between needle and question, (b) presence of distractors, and (c) — counterintuitively — haystacks with coherent logical flow (shuffled haystacks scored *better*). GPT models hallucinated most under confusion; Claude abstained more.
- **Solutions:** Treat **context engineering** — *where and how* information is placed — as more important than mere presence; keep context tight and relevant, do not dump everything into a big window.
- **Source:** Hong, Troynikov, Huber (Chroma), *Context Rot*, 2025 — https://www.trychroma.com/research/context-rot

### I.3 The four context-degradation mechanisms (poisoning, distraction, confusion, clash)
- **What & root cause (each):**
  - **Poisoning** — a hallucination/error enters context and is repeatedly referenced; the model fixates on impossible goals (evidence: Gemini 2.5 "plays Pokémon" — goals/summaries became poisoned).
  - **Distraction** — as history grows, the model over-focuses on its own accumulated trace and neglects trained knowledge (Gemini 2.5 tipped past ~100K tokens; Llama 3.1 405B fell around ~32K).
  - **Confusion** — superfluous content, **especially too many tool definitions**, drags in irrelevant material and lowers output quality.
  - **Clash** — later context contradicts earlier content; models cling to premature early-turn assumptions (Microsoft/Salesforce sharded-prompt study: **avg −39%**; OpenAI o3 **98.1 → 64.1**).
- **Solutions:** **Context validation/quarantine**, **pruning**, **summarization/compaction**, **context offloading** to an external store, and **tool loadout** (load only relevant tools, e.g. RAG over tool definitions).
- **Source:** Drew Breunig, *How Long Contexts Fail* and *How to Fix Your Context*, 2025 — https://www.dbreunig.com/2025/06/22/how-contexts-fail-and-how-to-fix-them.html · https://www.dbreunig.com/2025/06/26/how-to-fix-your-context.html

### I.4 Compounding (cascading) errors over long trajectories
- **What:** Even with strong single-step accuracy, whole-task success decays geometrically with steps. 95%/step → ~59% at 10 steps, ~0.6% at 100; 90%/step → ~35% at 10.
- **Root cause:** Under independence, success = reliability^steps. Empirically failures are **positively correlated** (the same error mode recurs), making it *worse* than exponential.
- **Solutions:** Reduce the **effective horizon** via decomposition; add error detection/recovery and self-consistency; **reduce inter-step error correlation**; evaluate with reliability metrics (e.g. success "half-life") rather than single-shot pass rates.
- **Sources:** *Is there a half-life for the success rates of AI agents?*, 2025 — https://arxiv.org/abs/2505.05115 · METR, *Measuring AI Ability to Complete Long Tasks*, 2025 (agents' 50%-reliability task horizon is finite — ~2h for o3 — but doubling ~every 7 months) — https://metr.org/blog/2025-03-19-measuring-ai-ability-to-complete-long-tasks/

### I.5 Cross-cutting fix — context engineering as a discipline
- **What/why:** A finite "attention budget" depletes with every token; n² attention scaling and **context pollution** make naive context growth a primary cause of late-task failure.
- **Solutions (canonical playbook):** **compaction/summarization** (preserve architectural decisions, open bugs), **structured note-taking / external memory**, **sub-agent isolation** returning condensed summaries, **just-in-time retrieval** (load lightweight identifiers at runtime), **tool curation** (minimal, unambiguous). The four-strategy taxonomy: **Write / Select / Compress / Isolate**. And the root preventive principle: *prefer the simplest thing that works; only add agentic complexity when needed.*
- **Sources:** Anthropic, *Effective Context Engineering for AI Agents*, 2025 — https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents · Anthropic, *Building Effective Agents*, 2024 — https://www.anthropic.com/research/building-effective-agents · LangChain, *Context Engineering for Agents*, 2025 — https://www.langchain.com/blog/context-engineering-for-agents

---

## Part II — Multi-Agent / Orchestration Failures

### II.1 The MAST taxonomy (the empirical anchor)
- **What:** A study of 7 popular multi-agent frameworks found **failure rates of 41%–86.7%**, and built **MAST**: 14 failure modes in **3 categories**, validated at **Cohen's κ = 0.88** (human) across 1,642 annotated traces.
- **Category prevalence:** **System Design Issues 44.2%**, **Inter-Agent Misalignment 32.3%**, **Task Verification 23.5%**.
  - *System Design* — Disobey task spec (11.8%), Disobey role spec (1.5%), **Step repetition (15.7%)**, Loss of history (2.8%), **Unaware of termination (12.4%)**.
  - *Inter-Agent Misalignment* — Conversation reset (2.2%), Fail to ask for clarification (6.8%), Task derailment (7.4%), Information withholding (0.85%), Ignored other agent's input (1.9%), **Reasoning-action mismatch (13.2%)**.
  - *Task Verification* — Premature termination (6.2%), No/incomplete verification (8.2%), Incorrect verification (9.1%).
- **Root cause:** Failures "stem from **system design issues, not just LLM limitations**." A well-designed MAS beats a better model with bad structure. Protocol standardization (MCP/A2A) is *necessary but not sufficient*; FC2 needs deeper "social reasoning."
- **Solutions:** Better role/workflow specification (paper's intervention: **+9.4%** on ChatDev); **multi-level verification** — low-level *and* high-level objective checks (adding a task-objective verifier: **+15.6%**); treat MAS as an *organizational design* problem; combinatorial fixes, not single patches ("a verifier is not a silver bullet").
- **Source:** Cemri et al. (Berkeley), *Why Do Multi-Agent LLM Systems Fail?*, 2025 (NeurIPS D&B) — https://arxiv.org/abs/2503.13657

### II.2 When multi-agent helps — and its costs
- **What/root cause:** Multi-agent helps on **breadth-first, parallelizable, context-isolable** tasks (Anthropic's orchestrator-worker beat single-agent by **90.2%** on research) but hurts when agents must **share context** or have **many dependencies** (coding called out as suboptimal). **Token spend alone explains ~80% of performance variance**; multi-agent uses **~15× more tokens** than chat.
- **Solutions:** Detailed per-subagent delegation specs (objective, output format, tool guidance, boundaries); **effort-scaling rules** (1 agent/3–10 calls simple; 2–4 for comparisons; 10+ for complex); resume-from-failure over restart; full production tracing; small eval sets with an LLM-judge rubric + human testing.
- **Source:** Anthropic, *How we built our multi-agent research system*, 2025 — https://www.anthropic.com/engineering/multi-agent-research-system

### II.3 The case *against* multi-agent (context fragmentation)
- **What:** In naive parallel-subagent setups, subagents can't see each other's in-flight work and make **conflicting implicit decisions** that can't be reconciled (the "Flappy Bird" example: a Mario-style background + a mismatched bird).
- **Root cause:** Two principles — (1) "**Share context, and share full agent traces**, not just messages"; (2) "**Actions carry implicit decisions, and conflicting decisions carry bad results**." Parallelism disperses decision-making.
- **Solutions:** Default to a **single-threaded linear agent** with continuous context; for long tasks add a dedicated model to **compress history into key decisions** rather than splitting into parallel agents.
- **Source:** Walden Yan (Cognition), *Don't Build Multi-Agents*, 2025 — https://cognition.ai/blog/dont-build-multi-agents

> **Reconciliation (the decision rule):** Anthropic and Cognition agree on the danger (broken context-sharing) and differ on task topology. **Default single-threaded; escalate to orchestrator-worker only when the task is genuinely parallelizable, dependency-light, high-value, and context-isolable** — and when you do, MAST names the three surfaces (design, alignment, verification) you must engineer against.

---

## Part III — Tool-Calling at Scale (the 50+ tool problem)

### III.1 Too many tools in context → a performance cliff
- **What:** As candidate tool count grows, selection accuracy and task success degrade — smaller models first and hardest. Failure is a **cliff, not a slope** (often cited ~20 tools for capable models; a quantized Llama-3.1-8B failed with 46 tools but succeeded with 19). *Teams testing with 5–10 tools in dev won't see the 50-tool production failure.*
- **Root cause:** **Prompt/context bloat** — tool schemas saturate the window with distractors, diluting attention — plus **decision-space explosion** among near-equivalent options.
- **Solutions:** **Retrieval-over-tools (RAG-MCP):** retrieve only top-k relevant tools before invocation (reported tool-selection accuracy **13.62% → 43.13%**, **~50% prompt-token reduction**); **cap tool count** (practitioner consensus 5–15/server); **dynamic/deferred loading**.
- **Sources:** Gan & Sun, *RAG-MCP*, 2025 — https://arxiv.org/abs/2505.03275 · (tool-overload corroborated by Breunig I.3 and Anthropic below)

### III.2 Ambiguous / overlapping tool descriptions → tool confusion
- **What:** Similar names/descriptions (`get_status` vs `fetch_status` vs `query_status`) cause wrong-tool selection by surface similarity.
- **Root cause:** Models do fuzzy pattern-matching, not symbolic resolution. Anthropic's design test: "**If a human engineer can't definitively say which tool to use, an agent can't be expected to do better.**"
- **Solutions:** Write descriptions like onboarding a new colleague — spell out formats, edge cases, and **clear boundaries from other tools**; avoid ambiguous parameter names (`user_id` not `user`); **consolidate** to natural, non-overlapping task subdivisions (also shrinks tool count).
- **Source:** Anthropic, *Writing effective tools for AI agents*, 2025 — https://www.anthropic.com/engineering/writing-tools-for-agents

### III.3 Wrong-tool selection, schema/argument errors, hallucinated calls
- **What & root cause (from benchmark error taxonomies):** hallucinated function name (tool not in list), wrong tool from a valid list, missing required parameter, wrong call count, unparseable/invalid-JSON output. Driven by attention spread across similar tools, zero-shot invocation without grounding, and weak format adherence.
- **Solutions:** **constrained/structured decoding** (eliminates format errors), retrieval to shrink the candidate set, per-tool few-shot examples, **argument validation + retry loops**.
- **Sources:** Berkeley Function-Calling Leaderboard (Gorilla) — https://gorilla.cs.berkeley.edu/blogs/13_bfcl_v3_multi_turn.html · Kokane et al., *SpecTool*, 2024 — https://arxiv.org/abs/2411.13547 · Qin et al., *ToolLLM*, 2023 — https://arxiv.org/abs/2307.16789

### III.4 The reliability gap (can-do vs. does-reliably)
- **What:** **τ-bench** (Sierra): best agents score **<50%** average; the **pass^k** metric shows running the *same* task 8× succeeds **<25%** of the time — the headline "consistency collapse." Tasks needing **multiple DB writes** and strict **policy adherence** fail most.
- **Root cause:** Single-shot capability ≠ multi-turn reliability under policy; compounding errors (Part I.4) plus tool/argument fragility.
- **Solutions:** Evaluate with **pass^k / reliability** metrics, not pass@1; harden write-paths with validation + idempotency; constrain policy via verifiable checks.
- **Source:** Sierra, *τ-bench*, 2024 — https://sierra.ai/blog/benchmarking-ai-agents

### III.5 MCP-specific scaling (token bloat + collisions) — and "code mode"
- **What/root cause:** Loading many MCP servers pre-loads *all* schemas before the user types — well-documented practitioner figures cite **100K–200K tokens** of pure schema overhead in a 5–10 server stack, plus cross-server name collisions. (These specific token counts are from industry blogs, not peer-reviewed — directional.)
- **Solutions:** **Deferred/Tool-Search loading** (load schemas on demand — this very environment does it); **scoped servers** (5–15 tools each); and **Code Execution with MCP** — expose tools as a **code API** the agent programs against, loading only needed tools and filtering data *in a sandbox before it re-enters context* (reported 150K → 2K tokens on one example). Trade-off: requires secure sandboxing.
- **Source:** Anthropic, *Code execution with MCP*, 2025 — https://www.anthropic.com/engineering/code-execution-with-mcp

---

## Part IV — RAG / Retrieval Failures

### IV.1 The Seven Failure Points (canonical)
From an experience report across three production systems. Each point + its advised mitigation:
1. **Missing content** — answer isn't in the corpus, and the system answers anyway. → data cleaning; prompt the model to abstain ("say you can't answer if unsure").
2. **Missed top-ranked** — answer exists but ranks below the cutoff. → tune retrieval/K; make ranking a configurable, tested pipeline parameter; add metadata.
3. **Not in context (consolidation)** — retrieved but dropped before generation (token limits). → treat consolidation as an explicit, tunable stage; budget the window.
4. **Not extracted** — answer is in context but the LLM misses it ("too much noise or contradicting information"). → reduce noise; add metadata; cut competing passages.
5. **Wrong format** — ignores requested format (table/list). → output parsers; prompt engineering; test for jailbreaks.
6. **Incorrect specificity** — too vague or too specific for the user's need. → query rewriting/clarification; calibrate per domain.
7. **Incomplete** — misses parts of a multi-part answer that were present. → query decomposition into sub-queries.
- **Cross-cutting lesson:** robustness "evolves rather than being designed in" — failure points appear at **runtime**, so observability is mandatory.
- **Source:** Barnett et al., *Seven Failure Points When Engineering a RAG System*, 2024 — https://arxiv.org/abs/2401.05856

### IV.2 Chunking, retrieval-miss, embedding mismatch, reranking
- **What & root cause:** Overchunking fragments concepts; underchunking dilutes relevance; arbitrary splits **sever context** ("its 3.85M inhabitants…" with no city named). **Retrieval miss** stems from **query–document asymmetry** — dense embeddings encode semantics, not exact tokens, so identifiers (`Volvo XC90`, `ISO 27001`) get missed. Rerankers can push needed chunks below the cutoff if misaligned.
- **Solutions:** structure-aware / **semantic chunking**, overlapping chunks, **sentence-window / small-to-big** retrieval; **hybrid dense+sparse (BM25)** search; **HyDE** (embed a hypothetical answer to close the Q–A gap); domain-adapted embeddings; **two-stage retrieval** = bi-encoder recall (~50–75 candidates) → **cross-encoder reranker** tuned with hard negatives.
- **Sources:** Leung et al. (Layer 6 AI), *Classifying and Addressing the Diversity of Errors in RAG*, 2025 — https://arxiv.org/abs/2510.13975 · Pinecone, *Rerankers and Two-Stage Retrieval* — https://www.pinecone.io/learn/series/rag/rerankers/

### IV.3 Hallucinated citations / unfaithful grounding (retrieval can't fix this)
- **What:** The model answers from parametric memory, then scans retrieved docs for **post-hoc supporting tokens**; citation presence has **near-zero correlation** with factual accuracy ("illusion of groundedness"). (The "57% unfaithful" figure is from a practitioner write-up — directional.)
- **Root cause:** generate-then-cite pipelines attach citations *after* generation, disconnected from the evidence actually used.
- **Solutions:** inline attribution **during** generation; evaluate grounding at the **atomic-claim level** (NLI faithfulness checks); chain-of-verification; conformal **abstention**.
- **Highest-leverage retrieval fix (measured):** Anthropic **Contextual Retrieval** — prepend a 50–100 token Claude-generated context to each chunk before embedding + BM25; top-20 retrieval failure **5.7% → 3.7%** (contextual embeddings), **→ 2.9%** (+ contextual BM25), **→ 1.9%** (+ reranking).
- **Sources:** Leung et al. (above) · Anthropic, *Contextual Retrieval*, 2024 — https://www.anthropic.com/news/contextual-retrieval

---

## Part V — Hallucination & Faithfulness

### V.0 The foundational distinction
**Factuality** (matches the world) vs **Faithfulness/groundedness** (matches the *provided* context) are **orthogonal** — a claim can be true-but-ungrounded or grounded-but-false. Robust systems evaluate both. (Ji et al. 2022.)

### V.1 Intrinsic vs extrinsic hallucination
- **What:** *Intrinsic* — output contradicts the source. *Extrinsic* — output is unverifiable by the source.
- **Root cause:** erroneous decoding / imperfect representation; **source–reference divergence** in training data (e.g., 62% of WIKIBIO first sentences carry info absent from the infobox — the data *teaches* divergence); **parametric-knowledge override** and **exposure bias**.
- **Solutions:** faithful dataset construction/cleaning; retrieval grounding; planning/sketch-then-generate; post-hoc correction.
- **Source:** Ji et al., *Survey of Hallucination in NLG*, 2022 — https://arxiv.org/abs/2202.03629

### V.2 Snowballing (self-contradiction) and fact-conflict
- **What:** Model contradicts its own earlier output ("hallucination snowballing"); or contradicts established world knowledge.
- **Root cause:** autoregression **over-commits to early mistakes**; knowledge deficiency/staleness, overconfidence, **RLHF sycophancy**.
- **Solutions:** **chain-of-verification**, **self-consistency**, multi-agent debate; reward functions that let the model challenge the premise / express uncertainty / admit incapability; retrieval.
- **Source:** Zhang et al., *Siren's Song in the AI Ocean*, 2023 — https://arxiv.org/abs/2309.01219

### V.3 The meta-cause — confident guessing is rewarded ⭐
- **What:** Models emit plausible-but-false statements instead of abstaining — "like students guessing on a hard exam."
- **Root cause (two-stage):** (1) *Statistical* — when valid/invalid statements aren't cleanly separable in data, generative error is lower-bounded by the binary mis-classification rate (some hallucination is unavoidable from training). (2) *Persistence* — **benchmark scoring rewards guessing**: binary 0/1 accuracy gives zero credit for "I don't know," so a confident guess dominates abstention. Leaderboards **select for overconfidence**.
- **Solution:** a *socio-technical* fix — **rework mainstream benchmark scoring** to penalize confident errors more than uncertainty and give partial credit for calibrated abstention. Calibration is statistically *cheaper* than accuracy.
- **Source:** Kalai, Nachum, Vempala, Zhang (OpenAI), *Why Language Models Hallucinate*, 2025 — https://arxiv.org/abs/2509.04664 (blog, bot-blocked but live: https://openai.com/index/why-language-models-hallucinate/)

---

## Part VI — Security: Prompt Injection & Agent Risk

### VI.1 Prompt injection (OWASP LLM01)
- **What:** User/external input alters model behavior in unintended ways. **Direct** (user input), **indirect** (hidden instructions in retrieved content), **multimodal** (instructions in images). Inputs need not be human-visible — only parsed by the model.
- **Root cause:** **No separation between instruction and data channels** — both arrive as one concatenated token stream (the SQL-injection analogy). RAG and fine-tuning **do not fully mitigate** it.
- **Solutions (risk-reducing, *not* foolproof):** constrain behavior via system prompts; validate output formats; input/output filtering; **least-privilege** access + API-token separation; **human-in-the-loop for high-risk actions**; segregate/denote untrusted content; adversarial testing.
- **Sources:** OWASP LLM01:2025 — https://genai.owasp.org/llmrisk/llm01-prompt-injection/ · Simon Willison, *Prompt injection attacks against GPT-3*, 2022 — https://simonwillison.net/2022/Sep/12/prompt-injection/

### VI.2 The Lethal Trifecta
- **What:** The dangerous combination — **(1) access to private data + (2) exposure to untrusted content + (3) ability to externally communicate/exfiltrate.** With all three, one piece of poisoned content can steal data (read → be instructed → send). Confirmed in real Slack AI / Notion AI exfiltration cases.
- **Root cause:** the same unsolved channel-separation flaw, turned into a complete attack chain.
- **Solution:** **break the chain — never let one agent hold all three legs.** Detection-based guardrails are insufficient ("we still don't know how to 100% reliably prevent this"); the durable fix is application-level architecture.
- **Source:** Simon Willison, *The lethal trifecta for AI agents*, 2025 — https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/

### VI.3 Indirect injection + Excessive Agency (the amplifier)
- **What:** Attackers plant instructions in data the agent will retrieve (webpages, files, emails) — demonstrated against deployed systems. Damage becomes real when paired with **Excessive Agency**: too much functionality, permission, or autonomy.
- **Root cause:** tool-using agents feed untrusted retrieved data into the same context as instructions, with no provenance tracking; over-broad tool permissions convert an injection into consequential actions.
- **Solutions:** minimize extensions; **least-privilege** permissions; execute in the user's security context; **require human approval for significant actions**; complete mediation/authorization downstream; zero-trust output handling. Architecturally, the **Dual-LLM / CaMeL** pattern — a privileged planner that never sees untrusted content + a quarantined extractor with no tool access, plus **provenance tracking + capability-based policies** (blocked ~67% of attacks in AgentDojo; "the first credible mitigation").
- **Sources:** Greshake et al., *Not what you've signed up for (Indirect Prompt Injection)*, 2023 — https://arxiv.org/abs/2302.12173 · OWASP LLM Top 10 (2025) — https://genai.owasp.org/llm-top-10/ · Simon Willison, *CaMeL*, 2025 — https://simonwillison.net/2025/Apr/11/camel/

---

## Part VII — Evaluation Gaps & LLM-as-Judge Pitfalls

### VII.1 Shipping without evals
- **What:** Teams validate on cherry-picked "vibe checks" and ship; quality degrades silently as prompts/RAG/models change.
- **Root cause:** evals feel like a tax; worse, *developer intuition of "good/bad" is itself miscalibrated and shifts as they see more data* — so spot-checks optimize a moving target.
- **Solutions:** **assertion-based unit tests** from real prod samples (≥3 criteria each) that fire on any pipeline change; review input/output samples **daily**; reference-free evals that double as guardrails; track dev↔prod skew.
- **Source:** Yan, Bischof, Frye, Husain, Liu, Shankar, *What We've Learned From a Year of Building with LLMs*, 2024 — https://applied-llms.org/

### VII.2 Benchmark contamination & overfitting
- **What:** Benchmark data leaks into training (scores reflect memorization); or iterating against a static test set leaks the signal into design (Goodhart).
- **Root cause:** web-scale corpora ingest public benchmarks; closed models don't disclose composition. Even minor contamination causes overfitting under scaling laws.
- **Solutions:** held-out / **post-cutoff** evaluation data; rotate/refresh benchmarks; prefer task-specific evals from your own production distribution over leaderboard chasing.
- **Source:** Xu et al., *Benchmark Data Contamination of LLMs: A Survey*, 2024 — https://arxiv.org/abs/2406.04244 · Bordt et al., *How Much Can We Forget about Data Contamination?*, ICML 2025 — https://arxiv.org/abs/2410.03249

### VII.3 LLM-as-judge biases (quantified)
From the canonical judge paper (Zheng et al. 2023):
- **Position bias** — verdict depends on answer order. GPT-4 only **65%** consistent on swap; Claude-v1 **23.8%** (favoring first **75%** of the time). → **call twice with swapped order; tie unless consistent** (few-shot raised GPT-4 to 77.5%).
- **Verbosity bias** — prefers longer answers. A no-new-info "repetitive list attack" fooled weaker judges **91.3%** of the time. → pairwise over Likert; instruct to ignore length; length-controlled scoring.
- **Self-preference** — judges favor their own family (GPT-4 ~+10%, Claude-v1 ~+25% vs humans). → use a **different-family** judge; anonymize; panel/ensemble.
- **Weak math/reasoning grading** — default prompt failed **70%** of math grading; **reference-guided** judging cut it to **15%**. → CoT / reference-guided judging, or deterministic checkers for verifiable tasks.
- **Agreement is task-specific** — GPT-4 ~85% on non-tie votes (> human-human 81%) but biases erode this elsewhere. → **validate judge↔human agreement on your own task**; use the judge as a filter, not an oracle.
- **Source:** Zheng et al., *Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena*, 2023 — https://arxiv.org/abs/2306.05685 · broader 12-bias taxonomy: Ye et al., *Justice or Prejudice?*, 2024 — https://arxiv.org/abs/2410.02736

---

## Part VIII — Production Reliability Engineering

### VIII.1 Retries: naive retries → retry storms
- **What/root cause:** Treating transient failures (429/500/503/timeout) as fatal, or retrying immediately, causes synchronized "thundering herd" load (quadratic in competing clients).
- **Solution:** **Exponential backoff + jitter.** Plain backoff still clusters; jitter spreads retries to ~constant rate. **Full Jitter** (`sleep = random(0, min(cap, base·2^attempt))`) is best overall.
- **Source:** Marc Brooker (AWS), *Exponential Backoff and Jitter*, 2015 — https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/

### VIII.2 Rate limiting, idempotency, timeouts, typed errors
- **What/root cause:** bursty traffic hits quotas (429); timeout-triggered retries cause **duplicate side effects**; absent timeouts hang resources; generic catch-all retries non-retryable errors and crashes on empty/malformed output (LLMs "return output even when they shouldn't").
- **Solutions:** honor the **Retry-After** header; classify retryable (429/5xx/529) vs terminal (quota/billing/auth → fail fast); **idempotency keys** on side-effecting calls; explicit per-call **timeouts** with bounded retries; inspect error **bodies** not just status; validate/parse structured outputs and regenerate on failure; **circuit breakers** with **per-provider+model keys** + fallbacks. *(Patterns from the Applied-LLMs essay + practitioner production guides — verify against each provider's API ref.)*
- **Source:** Applied LLMs (above) — https://applied-llms.org/

### VIII.3 Observability / tracing
- **What/root cause:** multi-step agent runs are deeply nested and non-deterministic; standard APM can't model "which step failed, what it cost, why latency spiked."
- **Solutions:** **OpenTelemetry GenAI semantic conventions** (standard span schema: `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.operation.name`, prompt/completion as span events) — adopted by Datadog/MLflow/cloud vendors; **LangSmith** / **Langfuse** for step-level prompt/tool/token/cost/latency traces + online judge evals on sampled traces. Enables daily data review, drift detection, and root-causing.

### VIII.4 Cost/latency runaway, infinite tool loops, non-determinism
- **What/root cause:** oversized models, no caching, bloated context, unbounded agent steps; low-temperature agents hit "deterministic loop failure" (too rigid to pivot); even at temp=0 + fixed seed, API-side batching/quantization/load-balancing introduce variance.
- **Solutions:** pick the **smallest model that works** (a workflow of small models can beat one big model); cache aggressively; trim context; **bound max steps/iterations** + cost/latency budgets with alerts; prefer **deterministic, traced workflows** over open-ended agents; design evals for **semantic equivalence**, not byte-exact; pin model/version per call; treat reproducibility as *bounded*.
- **Source:** Applied LLMs (above); reliability framing consistent with Parts I.4 & III.4.

---

## Part IX — Mapping to Meridian's Five Properties

For each property: the failure modes that threaten it, and the literature-advised mitigations Meridian should hold to (with what Phase 0 already does).

### Property 1 — Model-driven tool selection at 50+ tools
- **Threats:** tool-overload performance **cliff** (III.1), **context confusion** from too many tool defs (I.3), ambiguous-description **tool confusion** (III.2), hallucinated/wrong-tool/schema errors (III.3), MCP token bloat (III.5).
- **Advised mitigations → Meridian:**
  - **Retrieval-over-tools / deferred loading** once the registry passes ~20 tools — do *not* put 50 schemas in context at once (RAG-MCP III.1; Anthropic code-mode III.5). *Phase 0 has 5 tools in-context; a `tools/retrieval.py` selector is required before scaling the registry.*
  - **Unambiguous, boundary-stating descriptions + namespacing** so "a human could say which tool to use" (III.2). *Phase 0 already namespaces `repo_/edit_/exec_/state_` and writes when-to/when-not descriptions; the planned Phase-3 **LLM-judge ambiguity audit** directly operationalizes this.*
  - **Constrained/structured decoding + argument validation + retry** for schema errors (III.3). *Maps to Meridian's typed `ToolOutcome` + retry classifier.*

### Property 2 — Genuine subagent isolation
- **Threats:** **context fragmentation / conflicting implicit decisions** (II.3); MAST **Inter-Agent Misalignment** 32.3% (II.1); the **lethal trifecta** when a subagent has data+untrusted-content+exfil (VI.2); excessive agency (VI.3).
- **Advised mitigations → Meridian:**
  - Subagents must **return condensed, typed summaries**, not dump raw context to the parent (I.5, II.2). *Meridian's `SecurityReport` typed return + isolated worktree is exactly this.*
  - **Least-privilege scoped tools** + **break the lethal trifecta**: the read-only `SecuritySubagent` (no write/exec, no external comms) is a textbook trifecta break (VI.2, VI.3). *Already the Phase-1 design.*
  - Heed Cognition's warning: **isolate only genuinely parallelizable, dependency-light, context-isolable** work; default single-threaded otherwise (II.3 reconciliation).

### Property 3 — Long-horizon coherence / context management (≥20 tool calls)
- **Threats:** **context rot** (I.2), **lost-in-the-middle** (I.1), **poisoning/distraction/clash** (I.3), **compounding errors** (I.4), MAST **step-repetition (15.7%)** and **unaware-of-termination (12.4%)** (II.1).
- **Advised mitigations → Meridian:**
  - **Compaction + structured external memory + just-in-time retrieval** (I.5). *Meridian's authoritative compact `TaskState` (raw output summarized & discarded, budgeted `render_context`) is the in-code expression of this — the property the assignment demands be "in the code itself."*
  - **Reduce effective horizon** via plan decomposition + step verification; **reduce inter-step error correlation** (I.4). *Maps to `state_update` plan tracking + the planned evaluator step.*
  - Explicit **termination conditions** + budget ceilings to avoid step-repetition/non-termination (II.1). *Meridian uses SDK `max_turns`/`max_budget_usd`.*
  - Keep relevant info at context **edges**; keep the active window **below the distraction ceiling** (I.1, I.3).

### Property 4 — Production scaffolding
- **Threats:** retry storms (VIII.1), duplicate side-effects / 429s / hangs (VIII.2), invisible multi-step failures (VIII.3), cost/latency runaway + infinite loops + non-determinism (VIII.4), **shipping without evals** + **judge bias** (VII).
- **Advised mitigations → Meridian:**
  - **Exponential backoff + jitter (Full Jitter)**, Retry-After, **typed retryable-vs-terminal** classification, **idempotency keys**, timeouts, **circuit breakers per provider+model** (VIII.1–2). *Meridian has the deterministic-vs-transient flag; backoff+jitter, rate-limit handling, and breakers are the Phase-2 build-out.*
  - **OTel GenAI tracing + step-level cost/latency** (VIII.3). *Meridian persists trace spans; adopt OTel GenAI attribute names.*
  - **Eval harness from real traces; reference-guided / swapped-order / different-family judges; validate judge↔human agreement; held-out post-cutoff data** (VII.1–3). *Directly shapes Meridian's `evals/` harness — and warns against trusting a same-family LLM judge.*
  - **Bound max steps + budgets**, prefer deterministic/traced flow, design evals for **semantic equivalence** (VIII.4).

### Property 5 — Composable tool chains
- **Threats:** unparseable/format errors breaking chains (III.3); **intermediate-result duplication** through the model inflating context (III.5); **unfaithful hand-offs** where a downstream tool trusts an upstream free-text blob (IV.3).
- **Advised mitigations → Meridian:**
  - **Typed, schema-validated I/O** so one tool's output is another's typed input, with **structured decoding** to kill format errors (III.3). *This is precisely Meridian's `tools/schemas.py` + `ToolOutcome` contract and the planned Phase-3 contract tests.*
  - **Filter/condense data before it re-enters context** (code-mode / store-by-reference) to avoid duplication bloat (III.5, I.5). *Meridian stores large raw output by `blob:` reference and folds only conclusions into `TaskState`.*
  - For any tool that consumes another's *content* (e.g. PR-writer consuming `SecurityReport`/`TestResult`), validate at the **claim level** rather than trusting free text (IV.3).

---

## Sources (all HTTP-verified 200 OK unless noted)

**Context & long-horizon**
- Liu et al., *Lost in the Middle*, 2023 — https://arxiv.org/abs/2307.03172
- Chroma, *Context Rot*, 2025 — https://www.trychroma.com/research/context-rot
- Breunig, *How Long Contexts Fail* — https://www.dbreunig.com/2025/06/22/how-contexts-fail-and-how-to-fix-them.html · *How to Fix Your Context* — https://www.dbreunig.com/2025/06/26/how-to-fix-your-context.html
- *Half-life of agent success rates*, 2025 — https://arxiv.org/abs/2505.05115
- METR, *Measuring AI Ability to Complete Long Tasks*, 2025 — https://metr.org/blog/2025-03-19-measuring-ai-ability-to-complete-long-tasks/
- Anthropic, *Effective Context Engineering* — https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents · *Building Effective Agents* — https://www.anthropic.com/research/building-effective-agents
- LangChain, *Context Engineering for Agents* — https://www.langchain.com/blog/context-engineering-for-agents

**Multi-agent**
- Cemri et al., *Why Do Multi-Agent LLM Systems Fail?* (MAST), 2025 — https://arxiv.org/abs/2503.13657
- Anthropic, *Multi-agent research system* — https://www.anthropic.com/engineering/multi-agent-research-system
- Cognition, *Don't Build Multi-Agents* — https://cognition.ai/blog/dont-build-multi-agents

**Tool-calling**
- Gan & Sun, *RAG-MCP*, 2025 — https://arxiv.org/abs/2505.03275
- Anthropic, *Writing effective tools for AI agents* — https://www.anthropic.com/engineering/writing-tools-for-agents · *Code execution with MCP* — https://www.anthropic.com/engineering/code-execution-with-mcp
- Kokane et al., *SpecTool*, 2024 — https://arxiv.org/abs/2411.13547 · Qin et al., *ToolLLM*, 2023 — https://arxiv.org/abs/2307.16789
- Berkeley Function-Calling Leaderboard — https://gorilla.cs.berkeley.edu/blogs/13_bfcl_v3_multi_turn.html · Sierra, *τ-bench* — https://sierra.ai/blog/benchmarking-ai-agents

**RAG**
- Barnett et al., *Seven Failure Points of RAG*, 2024 — https://arxiv.org/abs/2401.05856
- Leung et al., *Diversity of Errors in RAG*, 2025 — https://arxiv.org/abs/2510.13975
- Anthropic, *Contextual Retrieval*, 2024 — https://www.anthropic.com/news/contextual-retrieval · Pinecone, *Rerankers* — https://www.pinecone.io/learn/series/rag/rerankers/

**Hallucination**
- Kalai et al. (OpenAI), *Why Language Models Hallucinate*, 2025 — https://arxiv.org/abs/2509.04664 (blog 403-to-bots but live: https://openai.com/index/why-language-models-hallucinate/)
- Ji et al., *Survey of Hallucination in NLG*, 2022 — https://arxiv.org/abs/2202.03629 · Zhang et al., *Siren's Song*, 2023 — https://arxiv.org/abs/2309.01219

**Security**
- OWASP Top 10 for LLM Apps (2025) — https://genai.owasp.org/llm-top-10/ · LLM01 Prompt Injection — https://genai.owasp.org/llmrisk/llm01-prompt-injection/
- Simon Willison: *Prompt injection* (2022) — https://simonwillison.net/2022/Sep/12/prompt-injection/ · *Lethal trifecta* (2025) — https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/ · *CaMeL* (2025) — https://simonwillison.net/2025/Apr/11/camel/
- Greshake et al., *Indirect Prompt Injection*, 2023 — https://arxiv.org/abs/2302.12173

**Evaluation & reliability**
- Zheng et al., *Judging LLM-as-a-Judge*, 2023 — https://arxiv.org/abs/2306.05685 · Ye et al., *Justice or Prejudice?*, 2024 — https://arxiv.org/abs/2410.02736
- Xu et al., *Benchmark Data Contamination Survey*, 2024 — https://arxiv.org/abs/2406.04244 · Bordt et al., *How Much Can We Forget about Data Contamination?*, 2025 — https://arxiv.org/abs/2410.03249
- Yan et al., *What We've Learned From a Year of Building with LLMs*, 2024 — https://applied-llms.org/
- Brooker (AWS), *Exponential Backoff and Jitter*, 2015 — https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/

### Caveats / not load-bearing
- **Future-dated arXiv IDs** surfaced by agents but not independently readable (e.g. `2603.29231`, `2603.11495`, `2604.23178`, `2601.19927`) were **excluded**; claims they would have supported are instead carried by verified sources above.
- **Specific token-count figures** for MCP bloat (III.5) and the **"57% unfaithful citations"** stat (IV.3) come from practitioner blogs, not peer-reviewed work — treated as **directional**. The Anthropic *Contextual Retrieval* and *Code execution with MCP* numbers are from Anthropic's own primary posts.
- **Microsoft/Salesforce sharded-prompt** figures (I.3) are cited via Breunig's write-up, not the primary paper.
