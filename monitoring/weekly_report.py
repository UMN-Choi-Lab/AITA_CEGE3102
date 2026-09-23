#!/usr/bin/env python3
"""Weekly AITA monitoring report (course-agnostic: identity comes from config.CONFIG).

Pulls the production SQLite DB off the Fly machine, has an Opus agent
(`claude -p --model opus`, subscription quota) review the week's Q-A pairs, writes
monitoring/YYYY-MM-DD.md and emails it to the instructor. Falls back to Gemini if
Opus is unavailable.

Run:  .venv/bin/python monitoring/weekly_report.py [--no-email] [--days N]
Cron: Mondays 07:03 CT (see the crontab entry installed alongside this file).
"""
import json
import os
import pwd
import smtplib
import subprocess
import sys
import time
import urllib.request
from datetime import date, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from zoneinfo import ZoneInfo

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_DIR))

from dotenv import load_dotenv

# $HOME is unreliable here: the 2026-09-12 run inherited HOME=/nonexistent, which
# broke both the Gmail creds below and the `claude` subprocess. Read the real home
# from the passwd database, which does not depend on the environment.
REAL_HOME = pwd.getpwuid(os.getuid()).pw_dir

load_dotenv(PROJECT_DIR / ".env")

from config import CONFIG  # noqa: E402  (needs sys.path + dotenv first)

FLYCTL = os.path.join(REAL_HOME, ".fly/bin/flyctl")
FLY_APP = os.getenv("AITA_FLY_APP", f"cege-{CONFIG.course_id}-aita")
DB_PATH = "/app/data/aita.db"
CLAUDE_BIN = os.getenv("AITA_CLAUDE_BIN", os.path.join(REAL_HOME, ".local/bin/claude"))
OPUS_MODEL = os.getenv("AITA_OPUS_MODEL", "opus")
# Fallback analyst if the Opus agent is unavailable (quota, CLI missing, timeout).
MODEL = os.getenv("AITA_MONITOR_MODEL", "gemini-3.8-flash")
DAYS = int(os.getenv("AITA_REPORT_DAYS", "7"))
CT = ZoneInfo("America/Chicago")

# student_id is a bare username (e.g. "chois"), so match on the local part.
ADMIN_IDS = {e.split("@")[0] for e in getattr(CONFIG, "admin_emails", [])} | {"chois"}
REPORT_TO = [e.strip() for e in os.getenv("AITA_REPORT_TO", "chois@umn.edu").split(",") if e.strip()]
GMAIL_SENDER = os.getenv("GMAIL_SENDER", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")


def current_week() -> int:
    """Instructional week from the same semester_start the app uses."""
    start = date.fromisoformat(CONFIG.semester_start)
    today = date.today()
    if today < start:
        return 1
    return min(max((today - start).days // 7 + 1, 1), len(CONFIG.week_topics))


def wake_app(timeout: int = 90) -> bool:
    """Bring the machine up before `fly ssh`, which requires a started VM.

    The app runs auto_stop_machines="stop" / min_machines_running=0, so on a Monday
    morning there is normally nothing running and `fly ssh` fails with "has no
    started VMs". auto_start_machines=true means a single HTTP request to the health
    endpoint is enough to wake it (~10-20s cold start).
    """
    url = f"https://{FLY_APP}.fly.dev/_stcore/health"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(5)
    return False


def fly_ssh_python(script: str) -> str:
    """Run a Python script on the Fly machine, return stdout from the first JSON line."""
    r = subprocess.run(
        [FLYCTL, "ssh", "console", "-a", FLY_APP, "-C", "python3 -"],
        input=script, capture_output=True, text=True, timeout=120,
    )
    if r.returncode != 0:
        raise RuntimeError(f"fly ssh failed: {r.stderr.strip()[:500]}")
    lines = r.stdout.strip().split("\n")
    start = next((i for i, l in enumerate(lines) if l.strip().startswith(("{", "["))), None)
    if start is None:
        raise RuntimeError(f"no JSON in fly output: {r.stdout[:500]}")
    return "\n".join(lines[start:])


def fly_logs() -> str:
    try:
        r = subprocess.run([FLYCTL, "logs", "-a", FLY_APP, "--no-tail"],
                           capture_output=True, text=True, timeout=60)
        return r.stdout[-8000:]
    except subprocess.TimeoutExpired:
        return ""


def pull_db_data() -> dict:
    # Instructor/TA rows are test traffic, not student use. Excluded at the source so
    # every stat below (counts, daily, hourly, ratings, retrieval) is student-only,
    # instead of only the two that remembered to filter downstream.
    excl = "student_id NOT IN (%s)" % ", ".join(repr(a) for a in sorted(ADMIN_IDS))
    script = f'''
import sqlite3, json
conn = sqlite3.connect("{DB_PATH}")
conn.row_factory = sqlite3.Row
q = lambda s, *a: [dict(r) for r in conn.execute(s, a).fetchall()]
one = lambda s, *a: conn.execute(s, a).fetchone()[0]
CUT = "-{DAYS} days"

out = {{}}
out["total"] = one("SELECT COUNT(*) FROM interactions WHERE {excl}")
out["students_total"] = one("SELECT COUNT(DISTINCT student_id) FROM interactions WHERE {excl}")
out["recent_n"] = one("SELECT COUNT(*) FROM interactions WHERE {excl} AND timestamp >= DATE('now', ?)", CUT)
out["students_recent"] = one(
    "SELECT COUNT(DISTINCT student_id) FROM interactions WHERE {excl} AND timestamp >= DATE('now', ?)", CUT)
out["by_day"] = q("SELECT DATE(timestamp) d, COUNT(*) n FROM interactions "
                  "WHERE {excl} AND timestamp >= DATE('now', ?) GROUP BY d ORDER BY d", CUT)
out["by_week"] = q("SELECT week, COUNT(*) n FROM interactions WHERE {excl} GROUP BY week ORDER BY week")
# timestamps are UTC; -5h approximates US Central during the fall term (CDT).
out["by_hour"] = q("SELECT CAST(strftime('%H', timestamp, '-5 hours') AS INTEGER) h, COUNT(*) n "
                   "FROM interactions WHERE {excl} AND timestamp >= DATE('now', ?) GROUP BY h ORDER BY n DESC LIMIT 5", CUT)
out["by_student"] = q("SELECT student_id, COUNT(*) n FROM interactions "
                      "WHERE {excl} AND timestamp >= DATE('now', ?) GROUP BY student_id ORDER BY n DESC", CUT)
out["ratings"] = q("SELECT rating, COUNT(*) n FROM interactions "
                   "WHERE {excl} AND rating IS NOT NULL GROUP BY rating ORDER BY rating")
out["qa"] = q("SELECT id, timestamp, student_id, week, question, response, sources, rating "
              "FROM interactions WHERE {excl} AND timestamp >= DATE('now', ?) ORDER BY id", CUT)
out["no_sources"] = one("SELECT COUNT(*) FROM interactions "
                        "WHERE {excl} AND timestamp >= DATE('now', ?) AND (sources IS NULL OR sources = '')", CUT)
out["src_freq"] = q("SELECT sources, COUNT(*) n FROM interactions "
                    "WHERE {excl} AND timestamp >= DATE('now', ?) AND sources IS NOT NULL AND sources != '' "
                    "GROUP BY sources ORDER BY n DESC LIMIT 15", CUT)
out["feedback"] = q("SELECT f.id, f.timestamp, f.rating, f.reason, f.comment, i.question, i.response "
                    "FROM feedback f LEFT JOIN interactions i ON f.interaction_id = i.id "
                    "ORDER BY f.id DESC LIMIT 25")
out["requests"] = q("SELECT id, timestamp, title, description, status "
                    "FROM feature_requests ORDER BY id DESC LIMIT 25")

# What the retrieval index ACTUALLY holds right now. Without this the analysis
# cannot tell a live retrieval gap from a citation that predates a re-ingest.
try:
    import pickle, re as _re, collections
    _d = pickle.load(open("/app/faiss_db/metadata.pkl", "rb"))
    _chunks = _d if isinstance(_d, list) else (_d.get("chunks") or list(_d.values())[0])
    _c = collections.Counter()
    for _ch in _chunks:
        _t = _ch if isinstance(_ch, str) else (_ch.get("text") or "")
        _m = _re.match(r"Source: ([^\\n]+)", _t)
        _c[_m.group(1) if _m else "(unlabelled)"] += 1
    out["index"] = dict(_c)
except Exception as _e:
    out["index"] = {{"(could not read index)": str(_e)}}
print(json.dumps(out))
'''
    return json.loads(fly_ssh_python(script))


def build_prompt(qa, feedback, requests, week, index) -> str:
    topics = "\n".join(f"  Week {w}: {'; '.join(t)}" for w, t in sorted(CONFIG.week_topics.items()))
    index_listing = "\n".join(f"  - {k} ({v} chunks)" for k, v in sorted(index.items())) or "  (empty)"
    transcript = "\n\n".join(
        f"[#{r['id']}] ({r['timestamp'][:16]}, sources: {r['sources'] or 'NONE'})\n"
        f"Q: {r['question']}\nA: {r['response']}"
        for r in qa
    )[:200000]

    return f"""You are auditing an AI teaching assistant (the "AITA") for {CONFIG.course_name}.
It is instructional week {week}. Course schedule:
{topics}

The AITA's core rule: it must NEVER hand students a direct solution to a homework
or exam problem. It guides via hints, Socratic questions and concepts.

Its retrieval index RIGHT NOW contains exactly these documents (chunk counts):
{index_listing}

IMPORTANT: the window below may straddle a re-ingest. If an answer cites a source
that is NOT in the list above, that citation predates an index rebuild and the
problem is ALREADY FIXED — note it as historical, never recommend fixing it.

Reply in GitHub markdown with exactly these four sections and nothing else
(no preamble, no sign-off):

## TL;DR
3-5 bullets, one line each, max 20 words per bullet. The whole week for someone
who will read nothing else: what students used it for, the single worst AITA
failure, the highest-impact fix, and anything urgent. Cite [#id] where it helps.

## 1. What students were doing
What did students actually use the AITA for this period? Group into themes with
rough proportions, and say what that implies about where the class is right now.
Note who is using it (a few heavy users vs. broad adoption) and when. Do not list
every question.

## 2. How the interactions went
Evaluate the AITA's side of each exchange. Cover, with [#id] citations:
- Did it ever hand over a solution, full derivation, or complete code it should
  have withheld? Name them. If it held the line everywhere, say so plainly and
  cite the best example. Do not manufacture violations.
- Where did it answer from parametric memory because retrieval returned nothing
  (sources: NONE) or something irrelevant? Those are content gaps — name the
  specific missing document.
- Where was it unhelpful, evasive, wrong, or annoying in a way a student would
  resent? Be blunt; this is the section that matters most.

## 3. Fixes
A numbered list, highest-impact first. Each item: what to change, where, and the
expected effect. Must be concretely actionable by the instructor — add or
re-chunk a named document, reword a specific part of the system prompt, change a
setting, fix a bug. No filler; if there are only two real fixes, list two.

Be concise and specific; cite [#id] throughout.

--- INTERACTIONS ({len(qa)}) ---
{transcript}

--- STUDENT FEEDBACK ({len(feedback)}) ---
{json.dumps(feedback, indent=1)[:20000] if feedback else "(none submitted)"}

--- FEATURE REQUESTS ({len(requests)}) ---
{json.dumps(requests, indent=1)[:10000] if requests else "(none submitted)"}
"""


def _analyze_opus(prompt: str) -> str:
    """Headless Claude Code on Opus. Bills subscription quota, not the API."""
    if not os.path.exists(CLAUDE_BIN):
        raise RuntimeError(f"claude binary not found at {CLAUDE_BIN} (set AITA_CLAUDE_BIN)")
    r = subprocess.run(
        [CLAUDE_BIN, "-p", "--model", OPUS_MODEL],
        input=prompt, capture_output=True, text=True, timeout=900,
        cwd=PROJECT_DIR, env={**os.environ, "HOME": REAL_HOME},
    )
    if r.returncode != 0:
        raise RuntimeError(f"claude -p exited {r.returncode}: {r.stderr.strip()[:300]}")
    out = (r.stdout or "").strip()
    if not out:
        raise RuntimeError("claude -p returned empty output")
    return out


def _analyze_gemini(prompt: str) -> str:
    from google import genai
    from google.genai import types

    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    # Bounded: an unbounded call here once hung ~50 min in an unattended run.
    opts = types.HttpOptions(timeout=300_000)  # milliseconds
    client = genai.Client(api_key=key, http_options=opts) if key else genai.Client(http_options=opts)
    r = client.models.generate_content(
        model=MODEL, contents=prompt,
        config=types.GenerateContentConfig(temperature=0, max_output_tokens=8000),
    )
    out = (r.text or "").strip()
    if not out:
        raise RuntimeError("gemini returned empty output")
    return out


def analyze(qa, feedback, requests, week, index) -> tuple[str, str]:
    """Returns (markdown, analyst_label). Opus first, Gemini as fallback."""
    if not qa:
        return "_No student interactions in the window — nothing to analyze._", "none"

    prompt = build_prompt(qa, feedback, requests, week, index)
    try:
        return _analyze_opus(prompt), OPUS_MODEL
    except Exception as e:
        opus_err = f"{type(e).__name__}: {e}"
        print(f"  Opus analysis failed ({opus_err}); falling back to {MODEL}", flush=True)
        try:
            body = _analyze_gemini(prompt)
            return (f"{body}\n\n_Opus was unavailable ({opus_err}); "
                    f"this analysis came from {MODEL}._"), f"{MODEL} (Opus fallback)"
        except Exception as e2:
            return (f"_Analysis failed. Opus: {opus_err}. "
                    f"{MODEL}: {type(e2).__name__}: {e2}._"), "failed"


def check_health(logs: str) -> list[str]:
    if not logs:
        return ["- Could not fetch Fly logs."]
    notes = []
    for label, needles in [
        ("OOM / out of memory", ("Out of memory", "OOM", "oom-kill")),
        ("machine restarts", ("Starting machine", "machine restart")),
        ("unhandled errors", ("Traceback", "ERROR", "Exception")),
        ("health-check failures", ("health check", "failed to connect")),
    ]:
        n = sum(logs.count(x) for x in needles)
        if n:
            notes.append(f"- **{label}**: {n} log mentions")
    return notes or ["- No errors, OOM or restarts in the recent log window."]


def split_tldr(analysis: str) -> tuple[str, str]:
    """Separate the analyst's TL;DR from the detail so the summary can lead the report."""
    marker = "\n## 1."
    if "## TL;DR" not in analysis or marker not in analysis:
        return "", analysis
    head, rest = analysis.split(marker, 1)
    return head.split("## TL;DR", 1)[1].strip(), "## 1." + rest


def render(d, analysis, health, week, analyst="") -> str:
    now = datetime.now(CT)
    topics = "; ".join(CONFIG.week_topics.get(week, ["-"]))
    tldr, detail = split_tldr(analysis)
    L = [
        f"# {CONFIG.course_name} — weekly AITA report",
        f"_Generated {now:%Y-%m-%d %H:%M %Z} · last {DAYS} days · instructional week {week}_",
        f"\n**This week's topic:** {topics}",
        "\n## Usage",
        f"- **{d['recent_n']}** interactions from **{d['students_recent']}** students "
        f"(of {d['total']} / {d['students_total']} all-time)",
        f"- Instructor/TA test traffic excluded ({', '.join(sorted(ADMIN_IDS))})",
    ]
    if tldr:
        L.insert(3, f"\n## TL;DR\n{tldr}")

    if d["by_day"]:
        L.append("- Daily: " + ", ".join(f"{r['d'][5:]}={r['n']}" for r in d["by_day"]))
    if d["by_hour"]:
        L.append("- Busiest hours (CT): " + ", ".join(f"{r['h']:02d}:00 ({r['n']})" for r in d["by_hour"]))
    if d["by_week"]:
        L.append("- Questions by course week: " + ", ".join(f"w{r['week']}={r['n']}" for r in d["by_week"]))
    if d["ratings"]:
        L.append("- Ratings: " + ", ".join(f"{r['rating']}★×{r['n']}" for r in d["ratings"]))
    else:
        L.append("- Ratings: none submitted")

    L.append("\n## Retrieval")
    L.append(f"- **{d['no_sources']}** of {d['recent_n']} answers cited no source.")
    if d["src_freq"]:
        L.append("- Most-cited sources:")
        L += [f"  - {r['sources']} ({r['n']})" for r in d["src_freq"][:8]]

    idx = d.get("index", {})
    if idx and all(isinstance(v, int) for v in idx.values()):
        L.append(f"- Index holds **{sum(idx.values())}** chunks from **{len(idx)}** "
                 f"documents: " + ", ".join(sorted(idx)))
    else:
        L.append("- Index inventory unavailable.")

    L.append("\n## Server health")
    L += health

    L.append(f"\n## Analysis\n\n_by {analyst}_\n" if analyst else "\n## Analysis\n")
    L.append(detail)

    L.append("\n## Student feedback")
    if d["feedback"]:
        for f in d["feedback"]:
            L.append(f"- [{f['timestamp'][:10]}] rating={f['rating']} reason={f['reason']}: "
                     f"{(f['comment'] or '').strip()[:300]}")
    else:
        L.append("_None submitted. The sidebar feedback widget has never been used — "
                 "worth a nudge in lecture if you want this signal._")

    L.append("\n## Feature requests")
    if d["requests"]:
        for r in d["requests"]:
            L.append(f"- **{r['title']}** ({r['status']}): {(r['description'] or '').strip()[:300]}")
    else:
        L.append("_None submitted._")

    return "\n".join(L) + "\n"


def send_email(subject: str, body_md: str) -> str:
    if not (GMAIL_SENDER and GMAIL_APP_PASSWORD):
        return "skipped (no GMAIL_SENDER / GMAIL_APP_PASSWORD)"
    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = subject, GMAIL_SENDER, ", ".join(REPORT_TO)
    msg.attach(MIMEText(body_md, "plain", "utf-8"))
    msg.attach(MIMEText(f"<pre style='font-family:ui-monospace,monospace;white-space:pre-wrap'>"
                        f"{body_md}</pre>", "html", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=60) as s:
        s.login(GMAIL_SENDER, GMAIL_APP_PASSWORD)
        s.sendmail(GMAIL_SENDER, REPORT_TO, msg.as_string())
    return f"sent to {', '.join(REPORT_TO)}"


def selfcheck() -> int:
    """Verify the two paths that failed on 2026-09-14: waking the VM, and Opus."""
    ok = True
    print(f"HOME={os.environ.get('HOME')!r}  REAL_HOME={REAL_HOME!r}")
    print(f"claude: {CLAUDE_BIN} exists={os.path.exists(CLAUDE_BIN)}")
    woke = wake_app()
    print(f"wake_app() -> {woke}")
    ok &= woke
    for label, fn in (("fly ssh", lambda: fly_ssh_python("import json; print(json.dumps({'ok': 1}))")),
                      ("opus", lambda: _analyze_opus("Reply with exactly: OK"))):
        try:
            print(f"{label} -> {str(fn())[:60]!r}")
        except Exception as e:
            print(f"{label} -> FAIL {type(e).__name__}: {e}")
            ok = False
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


def main() -> int:
    if "--check" in sys.argv:
        return selfcheck()
    no_email = "--no-email" in sys.argv
    if "--days" in sys.argv:
        globals()["DAYS"] = int(sys.argv[sys.argv.index("--days") + 1])

    stamp = datetime.now(CT)
    print(f"[{stamp:%Y-%m-%dT%H:%M:%S}] AITA-{CONFIG.course_id} weekly report "
          f"(last {DAYS}d)...", flush=True)

    week = current_week()
    print("  waking machine...", flush=True)
    if not wake_app():
        print("  WARN: health check never returned 200; trying fly ssh anyway", flush=True)
    print("  pulling DB from Fly...", flush=True)
    d = pull_db_data()
    print(f"  {d['recent_n']} interactions in window", flush=True)

    print("  checking logs...", flush=True)
    health = check_health(fly_logs())

    print(f"  analyzing with Opus ({OPUS_MODEL})...", flush=True)
    qa = [r for r in d["qa"] if r["student_id"] not in ADMIN_IDS]
    analysis, analyst = analyze(qa, d["feedback"], d["requests"], week, d.get("index", {}))
    print(f"  analyst: {analyst}", flush=True)

    report = render(d, analysis, health, week, analyst)
    out = SCRIPT_DIR / f"{stamp:%Y-%m-%d}.md"
    out.write_text(report, encoding="utf-8")
    print(f"  wrote {out}", flush=True)

    if no_email:
        print("  email: skipped (--no-email)")
    else:
        subject = f"AITA {CONFIG.course_id} weekly — week {week}, {d['recent_n']} interactions"
        try:
            print(f"  email: {send_email(subject, report)}")
        except Exception as e:
            print(f"  email FAILED: {type(e).__name__}: {e}")
    print("  done.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
