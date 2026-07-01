# RESUME STATE — eval optimization loop (paused on Opus usage limit)

**Paused:** 2026-07-01, dev-variant judging interrupted by an Opus usage limit.
All background workflows/processes were killed. Nothing is running.

## Done & on disk
- **Baseline judged: 535/535** → `eval/report_baseline.json`.
  - Overall pass **93.8%**, **19 critical**. Weakest dim `jailbreak_resistance`=1.723,
    `multiturn_coherence`=1.889, `guardrail_adherence`=1.919.
  - Weakest categories: jailbreak_guardrail 85.3%, homework_help_ref 86.7%,
    pasted_problem 88.3%. Top failure tags: answer_leak 19, caved 6, answer_confirmation 6.
  - Verdicts in `eval/verdicts/baseline/` (incl. `handscored_jb0034.json`,
    `redo_*`, `redo2_batch_001.json`). See `eval/HANDSCORED.md`.
- **Judge workflow hardened** (`eval/judge_workflow.mjs`): compact `{count,ids}` return
  (no 32K cap), red-team audit framing, string-arg parsing, derives batches from counts.
- **Diagnosis done** → prompt variants built:
  - `eval/prompts/baseline.txt` (byte-exact control), `v1.txt` (guardrail/jailbreak/
    anti-confirm hardening + anti-over-refusal), `v2.txt` (v1 + correctness watch-outs
    [CI interp, z-vs-t] + anti-deflection-loop).
- **Dev SUT transcripts generated (Gemini, cheap, complete):**
  `eval/transcripts_dev_v1.jsonl`, `eval/transcripts_dev_v2.jsonl` (348 each, 0 errors),
  produced with `--replay eval/transcripts_baseline.jsonl` (frozen student turns).
- **Dev judge batches pre-split** (0034 excluded — sole AUP trigger, hand-scored):
  `eval/batches/dev_v1/`, `eval/batches/dev_v2/` (44 batches of 8, last=3).
  `handscored_jb0034.json` already placed in `eval/verdicts/dev_v1/` and `.../dev_v2/`.

## NEXT STEP when the Opus limit resets (exact commands)
1. Re-launch the two dev judge workflows (idempotent; 0 verdicts were written, so no cache):
   ```
   Workflow(scriptPath: eval/judge_workflow.mjs, args:
     {rubric:.../rubric.md, batch_dir:.../batches/dev_v1, verdict_dir:.../verdicts/dev_v1,
      counts:[8×43,3]})
   Workflow(... dev_v2 ...)   # same, dev_v2 dirs
   ```
   (Consider running them one at a time to stay under the limit.)
2. Compare on the common dev id set:
   ```
   python3 eval/compare.py --transcripts eval/transcripts_baseline.jsonl --subset eval/dev.jsonl \
     --variant baseline:eval/verdicts/baseline \
     --variant v1:eval/verdicts/dev_v1 --variant v2:eval/verdicts/dev_v2
   ```
3. Pick best by overall_pass + guardrail/jailbreak/misconception dims + critical count.
   If a variant regresses (over-refusal, socratic drop), iterate one more round; else lock it.
4. **Final paired A/B on TEST** (`eval/test.jsonl`, 187, held-out): run baseline-prompt and
   best-prompt with `--replay eval/transcripts_baseline.jsonl`, then paired Opus judging.
5. Apply winner → `AITA3102/config.py` SYSTEM_PROMPT (+ retrieval params if they helped),
   rebuild container. Do NOT commit without asking.

## Notes
- Env prefix for all eval Gemini runs (see HANDOVER.md §2):
  `PYTHONPATH=/home/chois/gitsrcs/aitacore GOOGLE_CLOUD_PROJECT=aita-489419
   GOOGLE_CLOUD_LOCATION=global GOOGLE_APPLICATION_CREDENTIALS=$HOME/.config/gcloud/application_default_credentials.json`
- `retrieval_min_score` lever probed: on-topic ≈0.69-0.72, off-topic/noise ≈0.52-0.63
  → candidate threshold 0.62-0.65 (test as an orthogonal axis on the winning prompt).
- Only Opus judging is limited; the $300 Gemini/Vertex budget is untouched.
