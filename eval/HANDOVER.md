# HANDOVER — CEGE 3102 AI-TA: Gemini migration + prompt/system optimization

**Audience:** a fresh Claude Code window with no prior conversation. This doc is
self-contained. Read it top to bottom before doing anything.

**Last updated:** 2026-06-30, by the previous session.

---

## 0. TL;DR — where we are and the next action

Two pieces of work happened in this repo:

1. **DONE & verified — Gemini/Vertex migration.** The 3102 AI-TA now runs on
   Google Gemini (`gemini-3.1-flash-lite`) via Vertex AI using ADC, instead of
   OpenAI. Container is live on port **30005**. Week-gating was also disabled
   (`week_aware=False`) and the schedule corrected to Fall 2026.

2. **IN PROGRESS — eval + autoresearch prompt/system optimization.** We built an
   evaluation harness (535 test scenarios mined from real 3201 logs), produced a
   clean **baseline run (535/535 transcripts, 0 errors)**, validated an Opus-judge
   rubric on a pilot, and **reviewed/fixed the pipeline**. We are **paused at a
   checkpoint** waiting for the user's go-ahead to launch the "ultracode" part:
   the full Opus-judge workflow + the optimization loop.

**THE IMMEDIATE NEXT STEP** (once the user confirms — they said "review the
pipeline before start using ultracode", and the review is done):
re-split the clean baseline → run the judge workflow → `aggregate.py` →
diagnose → optimize on dev → final paired A/B on test. See §7.

> ⚠️ Before judging, RE-SPLIT: `eval/batches/baseline/` currently holds the OLD
> 499-row split from a discarded biased run. Re-run `split_transcripts.py` on the
> current clean `transcripts_baseline.jsonl` (535 rows) first. See §7 step 1.

---

## 1. The goal (what the user asked for)

- Migrate the base model to **Gemini** (UMN policy) using **ADC** (not API keys).
  Done. User has $300 GCP credit (Gemini/Vertex only).
- Build **≥500 test scenarios** — both single-interaction and multi-interaction
  (multi-turn sessions) — grounded in real student logs.
- **Evaluate Gemini's performance**, with **Opus (you) as the supervising judge**,
  via a **multi-agent workflow**.
- **Optimize the prompt and system** — primarily the system prompt, but also
  retrieval and few-shot — **"treat it as autoresearch"** (iterate until plateau).
- Pedagogical contract being tested: **never give/confirm direct answers**, **catch
  misconceptions**, **resist jailbreaks**, **cite sources**, **help with any week's
  topic** (week-gating is OFF), stay coherent across turns.

---

## 2. Environment & credentials (CRITICAL)

- **GCP project:** `aita-489419` (from the ADC quota project).
- **Vertex location:** `global` — REQUIRED. `gemini-3.1-flash-lite` 404s on
  `us-central1`. Embeddings (`gemini-embedding-001`) work at both, but use `global`.
- **Only reachable models on this project:** `gemini-3.1-flash-lite` (chat) and
  `gemini-embedding-001` (embeddings). `gemini-3-flash` / `gemini-3.1-pro` are
  **404** here (not allowlisted), so we could NOT use a stronger model for the
  student-simulator → documented monoculture limitation.
- **ADC file (host):** `~/.config/gcloud/application_default_credentials.json`
  (created via `gcloud auth application-default login`; gcloud is at
  `~/google-cloud-sdk/bin/gcloud`, not on PATH).
- **aita-core source** lives at `/home/chois/gitsrcs/aitacore` (NOT on PyPI).

### The env prefix used for EVERY Python run in eval/
```bash
PYTHONPATH=/home/chois/gitsrcs/aitacore \
GOOGLE_CLOUD_PROJECT=aita-489419 GOOGLE_CLOUD_LOCATION=global \
GOOGLE_APPLICATION_CREDENTIALS=$HOME/.config/gcloud/application_default_credentials.json \
python3 eval/<script>.py ...
```
- `PYTHONPATH` points at the aita-core **source** (has the latest edits incl.
  `providers.py`). Do NOT rely on an installed aita-core for eval runs.
- `GOOGLE_APPLICATION_CREDENTIALS` must point at the HOST ADC path for local runs.
  Note: `.env` sets it to `/app/adc.json` (the container path) — that's why local
  runs must OVERRIDE it on the command line (the override above does this; Python's
  `load_dotenv` does not override pre-set env vars).

---

## 3. Repo state & what changed (all UNCOMMITTED — user reviews before commit)

### `/home/chois/gitsrcs/aitacore` → bumped to **v0.6.0** (uncommitted)
Pre-existing unrelated WIP was already there (inline-feedback feature, `break_weeks`).
Our additions on top:
- `aita_core/providers.py` (NEW): provider abstraction. `chat_complete(cfg, msgs)`
  and `embed_texts(cfg, texts)` branch on `cfg.llm_provider` ("openai"|"gemini").
  Gemini path uses `google-genai` `Client(vertexai=True, project, location)`,
  `generate_content` (system→`system_instruction`, `assistant`→`model`), and
  `embed_content(output_dimensionality=...)`.
- `aita_core/config.py`: new fields — `week_aware: bool=True`, `llm_provider="openai"`,
  `gcp_project=""`, `gcp_location="us-central1"`, `llm_max_output_tokens=0`,
  `retrieval_min_score=0.0`. All added to `EDITABLE_FIELDS`. **Defaults preserve
  old behavior**, so AITA3201/template are unaffected.
- `aita_core/rag.py`: routed chat + embeddings through `providers`; split the
  week-gate prompt so the "future-topic refusal" block is gated by `week_aware`
  while the homework policy always applies; added `retrieval_min_score` filter;
  added a generic no-context warning when `week_aware=False`.
- `aita_core/ingest.py`: `get_embeddings(texts, config)` now delegates to providers.
- `pyproject.toml`: version 0.6.0, added `google-genai>=1.0.0` dependency.
- Wheel built: `dist/aita_core-0.6.0-py3-none-any.whl` (also vendored into 3102).

### `/home/chois/gitsrcs/AITA3102` (uncommitted)
- `config.py`: `week_aware=False`; `semester_start="2026-09-07"`; `week_topics` +
  `exam_scope` corrected to the Fall-2026 syllabus (MT1 wks 1-6, MT2 wks 7-11);
  Gemini block (`llm_provider="gemini"`, `llm_model="gemini-3.1-flash-lite"`,
  `gcp_project`/`gcp_location` from env, `llm_max_output_tokens=2048`,
  `embedding_model="gemini-embedding-001"`, `embedding_dimensions=3072`).
- `requirements.txt`: `aita-core>=0.6.0`.
- `Dockerfile`: now installs the vendored `aita_core-*.whl` before requirements.
- `docker-compose.yml`: published port **30005** (30001 taken by AgentHQ commander,
  30003 by hcm_ai); `environment: GOOGLE_CLOUD_LOCATION=global` (overrides .env);
  mounts host ADC → `/app/adc.json:ro`.
- `aita_core-0.6.0-py3-none-any.whl` (vendored, untracked).
- `eval/` (the harness, this directory — untracked).
- **`CLAUDE.md` is gitignored in 3102** (`.gitignore` lists it) — local edits to it
  won't show in `git status`. It WAS updated (week-gating disabled note + Fall-2026
  schedule table).
- `faiss_db/` is gitignored and was **re-ingested with Gemini embeddings**
  (531 vectors, `gemini-embedding-001`, 3072-dim). HW *solutions* are excluded by
  `ingest.collect_homework` (skips files with "solution").

### `.env` (hook-protected — you CANNOT write `.env*`; ask the user to edit)
Has: `GOOGLE_CLOUD_PROJECT=aita-489419`, `GOOGLE_CLOUD_LOCATION=us-central1` (overridden
to `global` by compose), `GOOGLE_APPLICATION_CREDENTIALS=/app/adc.json`, plus the old
`OPENAI_API_KEY` (now unused), `GOOGLE_REDIRECT_URI` (currently
`http://cege-u-tol-gpu-02.cege.umn.edu:30005/`), `GOOGLE_COOKIE_KEY`, `ADMIN_PASSWORD`,
`AITA_DATA_DIR`.

---

## 4. The eval harness (`eval/`)

| File | Purpose |
|---|---|
| `generate_scenarios.py` | Generates scenarios via Gemini → `scenarios.jsonl`. Categories + weights are inline (`CATEGORIES`). |
| `scenarios.jsonl` | **535 scenarios** (300 single / 235 multi / 300 guardrail-critical). |
| `run_sut.py` | Runs scenarios through the live 3102 Gemini RAG. Multi-turn via a Gemini student-simulator. Has retry/backoff, `--replay`, `--prompt-file`, `--retrieval-k`, `--retrieval-min-score`, `--limit`, `--workers`. |
| `transcripts_baseline.jsonl` | **Clean baseline: 535/535, 0 errors.** Current SUT output. |
| `rubric.md` | The judge rubric (8 dimensions 0-2/NA + overall_pass + severity + tags). |
| `judge_workflow.mjs` | Workflow script: one Opus judge per batch, writes verdict JSON files. |
| `split_transcripts.py` | Splits a transcripts file into batch files; prints a JSON manifest (used as Workflow `args`). |
| `aggregate.py` | Reads verdict files + transcripts → metrics report (`report_<tag>.json`). |
| `split_dev_test.py` | Stratified **dev (348) / test (187)** split (seed=42) → `dev.jsonl`, `test.jsonl`. |
| `pilot.jsonl`, `pilot_transcripts.jsonl` | 8-scenario pilot used to validate the loop + rubric. |
| `batches/`, `verdicts/` | Per-tag batch files and judge verdict outputs. **`batches/baseline/` is STALE (old 499 split) — re-split before judging.** |

### Scenario record shape (`scenarios.jsonl`)
```json
{"id":"pasted_problem__0007","category":"pasted_problem","guardrail_critical":true,
 "week":5,"topic":"Special discrete distributions","turn_type":"single|multi",
 "turn1_text":"...","followup_intents":["...","..."],   // [] for single
 "expected_behavior":"...","embedded_error":"..."}        // embedded_error only for misconception_bait
```
### Transcript record shape (`transcripts_baseline.jsonl`)
```json
{"id":...,"category":...,"guardrail_critical":...,"week":...,"current_week":...,
 "topic":...,"turn_type":...,"expected_behavior":...,"embedded_error":...,
 "transcript":[{"role":"user","content":...},{"role":"assistant","content":...,"sources":[...]}, ...]}
```
### Verdict record shape (written by judges into `verdicts/<tag>/batch_NNN.json`)
JSON array of: `{id, guardrail_adherence, correctness, misconception_catch,
socratic_quality, citation, jailbreak_resistance, relevance, multiturn_coherence,
overall_pass, severity, failure_reason, tags}` (dims are 0-2 or "NA").

---

## 5. Key decisions & rationale (don't relitigate)

- **Gemini via native `google-genai` + Vertex/ADC** (not OpenAI-compat shim): ADC's
  short-lived tokens auto-refresh only cleanly in the native SDK.
- **Provider abstraction with `openai` default**: keeps sibling courses unchanged.
- **`week_aware=False` for 3102**: instructor (Prof. Levin) wants no calendar-based
  refusals; HW *solutions* aren't ingested so future-problem "leakage" is moot.
- **Judge = Opus via Workflow** (user's explicit choice). SUT = Gemini. Independent
  models → no self-judging bias.
- **Optimization = autoresearch** (user's words): iterate prompt (primary) +
  retrieval + few-shot until plateau.
- **dev/test split + `--replay`**: avoid overfitting and control the multi-turn A/B
  confound (freeze student turns; only the TA's replies change between variants).

---

## 6. Pipeline review — findings & status (user asked for this before ultracode)

| # | Sev | Finding | Status |
|---|---|---|---|
| A | HIGH | 429 rate-limit caused 36 **biased** dropouts (future_topic/jailbreak/exam_prep). | FIXED: backoff+retry, workers=5. Clean 535/535 re-run done. |
| B | HIGH | Multi-turn A/B confound (student turns regenerated per run). | FIXED: `--replay` freezes student turns. |
| C | MED | Overfitting on one set. | FIXED: dev/test split. |
| D | MED | Judge variance can swamp small deltas. | PLANNED: paired judging for final A/B + adversarial double-check on criticals. |
| E | MED | Model monoculture (gen+SUT+sim all flash-lite). | UNAVOIDABLE here (other models 404). Documented. |
| F | LOW | Judge trusts Gemini-written `expected_behavior`. | Mitigated by rubric leaning on judge expertise; do a spot-check. |
| G | LOW | future_topic test weak under `week_aware=False`. | Keep as "doesn't spontaneously refuse"; low weight. |

**Pilot result (sanity):** baseline flash-lite + current prompt was already strong —
held firm over 4 escalating jailbreak turns, caught misconceptions, helped with
future topics. Expect optimization gains to be marginal but real, concentrated in
guardrail-critical edge cases + the **retrieval-source-noise** issue (irrelevant HW
files shown as "sources" on refusal/off-topic turns → lever: `retrieval_min_score`).

---

## 7. EXACT next steps to resume (the gated ultracode plan)

All commands assume `cd /home/chois/gitsrcs/AITA3102` and the env prefix from §2.

**1. Re-split the clean baseline (REQUIRED — current batches are stale):**
```bash
PYTHONPATH=/home/chois/gitsrcs/aitacore python3 eval/split_transcripts.py \
  --in eval/transcripts_baseline.jsonl --tag baseline --size 15
```
This prints a JSON manifest (rubric, batch_dir, verdict_dir, batches[]). Capture it.

**2. Run the Opus-judge workflow** (Workflow tool). Pass the manifest as `args`:
```
Workflow({ scriptPath: "/home/chois/gitsrcs/AITA3102/eval/judge_workflow.mjs",
           args: <the manifest object from step 1> })
```
Each Opus judge reads `rubric.md` + its batch file and writes
`verdicts/baseline/batch_NNN.json`. ~36 batches. (Pilot judge used ~305K Opus tokens
for 8 transcripts, so a full pass is ~15-20M Opus tokens — fine under ultracode; the
$300 is Gemini-only and untouched by judging.)
- Optional rigor (finding D): after judging, spawn 3 adversarial Opus verifiers on
  every `severity:"critical"` verdict; keep the majority vote.

**3. Aggregate the baseline report:**
```bash
python3 eval/aggregate.py --tag baseline --transcripts eval/transcripts_baseline.jsonl
```
Gives overall pass rate, per-category pass rate, per-dimension means, failure tags.

**4. Diagnose (you, the supervisor):** read `report_baseline.json` + sample failing
transcripts (esp. guardrail_critical fails) → list the top fixable failure modes.

**5. Autoresearch optimization loop on DEV (replayed for controlled A/B):**
For each round, propose candidate variants and evaluate each:
```bash
# example variant run on dev, reusing baseline student turns:
PYTHONPATH=... <env> python3 eval/run_sut.py \
  --in eval/dev.jsonl --out eval/transcripts_dev_v1.jsonl \
  --replay eval/transcripts_baseline.jsonl \
  --prompt-file eval/prompts/v1.txt --retrieval-min-score 0.35 --workers 5
# then split --tag dev_v1, run judge_workflow, aggregate --tag dev_v1
```
Levers: `SYSTEM_PROMPT` (edit a copy in `eval/prompts/*.txt`, pass via
`--prompt-file`), `--retrieval-min-score`, `--retrieval-k`, and few-shot exemplars
(add to the prompt text). Keep the best by overall_pass + guardrail/jailbreak/
misconception dimensions + critical-failure count. **Stop after 2 rounds with no gain.**
Consider a judge-panel/tournament workflow to score variants in parallel.

**6. Final paired A/B on TEST (held-out):** run baseline-prompt and best-prompt on
`test.jsonl` with `--replay eval/transcripts_baseline.jsonl`, then judge BOTH
responses per scenario in a single paired Opus judgment (controls judge variance).
Report before/after: overall, per-category, and critical-failure reduction.

**7. Apply the winner:** write the optimized prompt into `AITA3102/config.py`
`SYSTEM_PROMPT`, set `retrieval_min_score`/`retrieval_k` if they helped (re-ingest
only needed if `chunk_size` changed — it won't unless you choose to). Rebuild aita-core
wheel if you changed retrieval defaults in the library. Rebuild container.

---

## 8. Gotchas

- **`.env` is hook-protected** — you cannot Write `.env*`. Hand the user the lines to
  add/change.
- **Local runs must override `GOOGLE_APPLICATION_CREDENTIALS`** to the host ADC path
  (see §2) — `.env` points it at the container path `/app/adc.json`.
- **Vertex rate limits**: keep `--workers` ≤ 5; backoff is built in. Higher → 429s.
- **Only flash-lite + embedding-001 are reachable** on this project.
- **Ports**: 30001 = AgentHQ commander, 30003 = hcm_ai, 30005 = this app. Don't bind taken ports.
- **`batches/baseline` is stale** (old 499 split) — re-split first (§7.1).
- **CLAUDE.md gitignored in 3102** — edits are invisible to `git status`.
- **Opus token cost ≠ $300 budget.** The $300 is Gemini/Vertex only; Opus judging
  runs on the agent harness.
- **Nothing is committed.** aita-core has unrelated WIP mixed in; the user reviews
  before any commit. Do not commit without asking.

---

## 9. Quick verification commands
```bash
# baseline complete & unbiased?
wc -l eval/transcripts_baseline.jsonl   # 535
# container live?
docker ps --filter name=aita3102 --format '{{.Names}} {{.Status}} {{.Ports}}'
# Gemini reachable from container (in-container smoke):
docker exec aita3102-aita-1 python -c "from config import CONFIG; from aita_core.config import set_config; from aita_core.rag import chat; set_config(CONFIG); print(chat('what is a pmf?',[],15)[0][:120])"
# config sanity:
PYTHONPATH=/home/chois/gitsrcs/aitacore GOOGLE_CLOUD_PROJECT=aita-489419 python3 -c "import sys,types; sys.modules['faiss']=types.ModuleType('faiss'); import aita_core; from config import CONFIG; print(CONFIG.llm_provider, CONFIG.llm_model, CONFIG.gcp_location, CONFIG.week_aware)"
```

---

## 10. Open items / pending user decisions
- **Checkpoint:** user said "review the pipeline before start using ultracode." Review
  is DONE (§6). Awaiting explicit go-ahead to launch §7 (judge workflow + optimization).
- **Commits:** not done yet. Two repos to commit (aitacore 0.6.0 has unrelated WIP to
  separate; AITA3102). Ask before committing.
- **OAuth on :30005**: redirect is `http://...:30005/` (http on a real host) — Google
  may require https; student-ID fallback works meanwhile. Production likely behind the
  existing nginx + Let's Encrypt (see `/data2/aita_3102/letsencrypt`).
- **Optimization params to confirm** (if user wants): rounds, variants/round, stop
  condition.
