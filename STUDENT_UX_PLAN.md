# Student Experience Plan — CEGE 3102 AITA

All student-facing behavior lives in **aita-core** (`~/gitsrcs/aitacore`,
`UMN-Choi-Lab/aita-core`), not this repo. `main.py` here is just `run(CONFIG)`.
So each feature below is an aita-core change, released as a new wheel (bump to
`0.7.0`), then vendored here (`aita_core-0.7.0-py3-none-any.whl`) and redeployed.

Priority = impact ÷ effort. Effort: **S** ≈ <½ day, **M** ≈ 1 day, **L** ≈ 2–3 days.

---

## P0 — Launch robustness (do before a 100-user day-1 burst)  (effort: S · impact: High under load)

Two small aita-core hardening changes that only matter under concurrency — exactly the
day-1 scenario. See `DEPLOY.md` → "Capacity for ~100 users".

**A. SQLite WAL + busy_timeout** (`db.py`, `get_conn`). Default SQLite serializes writers
and can raise `database is locked` when several sessions log turns at once. In `get_conn()`,
right after `sqlite3.connect(...)`:
```python
conn.execute("PRAGMA journal_mode=WAL")     # concurrent readers + one writer
conn.execute("PRAGMA busy_timeout=5000")    # wait up to 5s instead of erroring
conn.execute("PRAGMA synchronous=NORMAL")   # safe with WAL, much faster writes
```
WAL persists on the volume; one-time set is enough but harmless per-connection.

**B. Graceful rate-limit handling** (`providers.py`, `_gemini_chat`). On a paid-tier 429
the current code returns the generic "couldn't generate" fallback. Instead, detect the
quota error and (i) retry once or twice with short backoff, then (ii) return a clear
"We're seeing high demand right now — please resend in a few seconds." So a brief spike
degrades gracefully rather than looking broken. (The empty-candidate retry loop is already
there; extend it to catch `google.genai.errors.ClientError` / status 429.)

> These don't change behavior at low load, so they're safe to ship independently of P1–P6.

---

## P1 — Streaming responses  (effort: M · impact: High)

**Problem.** `rag.chat()` returns the full string and `app.py` shows a static
`st.spinner("Thinking…")`. With flash-lite + 2048 output tokens, students stare at a
spinner for several seconds per turn. Perceived latency dominates the experience.

**Change.**
- `providers.py`: add `chat_complete_stream(cfg, messages)` — a generator.
  - Gemini: `client.models.generate_content_stream(model=…, contents=…, config=…)`,
    `yield chunk.text` for each chunk.
  - OpenAI: `client.chat.completions.create(..., stream=True)`, yield deltas.
  - Keep the existing non-stream `chat_complete` for ingestion/eval reuse.
- `rag.py`: add `chat_stream(user_query, history, current_week)` that runs the same
  retrieval/injection, computes `sources`, then returns `(text_generator, sources)`.
- `app.py` (`chat_page`): replace the spinner block with
  ```python
  with st.chat_message("assistant"):
      gen, sources = chat_stream(user_input, history_for_rag,
                                 current_week=st.session_state.current_week)
      response = st.write_stream(gen)          # renders tokens live, returns full text
      if not response.strip():
          response = "I'm sorry — I couldn't generate a response. Could you rephrase?"
  ```
  Then `log_interaction(...)` with the accumulated `response` exactly as today.

**Watch-outs.**
- The current empty-candidate retry (temperature nudging) can't run mid-stream —
  fall back to the message above when the stream yields nothing.
- `st.write_stream` renders incrementally with Markdown; confirm `$…$` still renders
  once the stream completes (it re-renders the final string).

---

## P2 — Student-visible past conversations  (effort: M · impact: High)

**Problem.** Every turn is already logged to `interactions`, but students can't see
their own history. Close the tab (or a Fly restart) and the conversation is gone —
`chat_history` is only in `st.session_state`.

**Change.** Group turns into conversations and surface them.
- `db.py`: add a `conversation_id TEXT` column to `interactions` (add an idempotent
  `ALTER TABLE` migration next to the existing `reason` one). Add:
  - `get_conversations(student_id, limit=25)` → distinct `conversation_id` with first
    question (title) + latest timestamp + turn count.
  - `get_conversation(conversation_id)` → ordered turns to rehydrate.
  - Thread `conversation_id` through `log_interaction(...)`.
- `app.py`:
  - `st.session_state.conversation_id` = a UUID; **New Conversation** mints a fresh one.
  - Sidebar **"My conversations"** expander lists past ones (title + date); clicking
    loads that conversation's turns into `chat_history` (resumable — same id — so new
    turns append to it).

This is the foundation P3 builds on.

---

## P3 — Persist the active chat across reloads / Fly restarts  (effort: S on top of P2 · impact: High on Fly)

**Problem.** A browser refresh or a `fly deploy` (which restarts the machine) wipes the
in-progress conversation even though the student is still "signed in" via cookie.

**Change (given P2's `conversation_id` + DB on the volume):**
- Store the active `conversation_id` in a lightweight cookie (reuse the existing
  `_set_auth_cookie` / `st.context.cookies` pattern in `app.py`).
- On startup, if that cookie is present, rehydrate `chat_history` via
  `get_conversation(id)`. The DB lives on the Fly volume, so it survives restarts.

**Watch-out.** Cap rehydration to the last N turns to match the 20-message window
`build_messages` already uses for the LLM.

---

## P4 — Confirm LaTeX renders (esp. inline `$…$`)  (effort: S · impact: Med-High)

**Problem.** The system prompt mandates `$…$` / `$$…$$`. Streamlit renders LaTeX via
KaTeX, but **inline single-`$`** support depends on the Streamlit version. If it breaks,
students see raw `$P(A\mid B)$` all over a probability course — very bad.

**Change.**
- Check the Streamlit version aita-core pins; ensure it's new enough for inline `$…$`
  in `st.markdown` (Streamlit ≥ 1.29). Pin it if not.
- Manual check after P1: ask *"Write Bayes' theorem"* and confirm both inline and
  display math render. Optional small CSS bump for KaTeX font size on mobile.

---

## P5 — Warm machine + optional per-student daily cap  (effort: S · impact: Med)

- **Warm machine** is already handled in `fly.toml` (`min_machines_running = 1`,
  `auto_stop_machines = false`) — no cold-start wait. ✅ done in this pass.
- **Cost guard (optional):** on a public URL, add a `max_messages_per_student_per_day`
  config field; in `chat_page`, count today's `interactions` for the student and show a
  friendly "you've reached today's limit" message past the cap. Cheap insurance against
  a runaway loop inflating Gemini usage.

---

## P6 — "Copy" and "Regenerate" affordances  (effort: S · impact: Low-Med)

- **Copy answer:** small button under each assistant message (JS `navigator.clipboard`
  snippet, or render into an `st.code` block which has a native copy button).
- **Regenerate:** button under the latest assistant turn that pops it and re-runs
  `chat_stream` with the same last user query (store `last_user_query` in session).

---

## Suggested sequencing

1. **P4** (verify LaTeX) — do during the model-id check; may need only a version pin.
2. **P1** (streaming) — biggest felt improvement, self-contained.
3. **P2 → P3** (history + persistence) — one DB migration, two related UI additions.
4. **P5 cap / P6** — polish, as time allows.

Ship P1–P3 as aita-core `0.7.0`, vendor the new wheel here, `fly deploy`.

> I can implement any of these directly in `~/gitsrcs/aitacore` as PRs — say which
> (P1 alone is a good first, low-risk win) and I'll build + test it.
