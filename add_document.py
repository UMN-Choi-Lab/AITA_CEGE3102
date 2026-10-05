"""Build the CEGE 3102 FAISS index.

Standard aita-core collectors for handouts, slides and the syllabus; custom
collectors for homework and labs so that every chunk is ONE problem with a header,
the writing rubric / submission boilerplate repeated in every assignment PDF lives
in a single document, and three documents that did not exist are generated: the
writing/submission guidelines, the Excel tips the lab handouts contain, and the
Fall 2026 assignment calendar.

Why (weekly digest 2026-09-21): the rubric page repeated in all 12 HW PDFs acted as
a retrieval attractor (Lab 11 was the sole source for a dozen contentless turns),
and whole-assignment chunks could not answer "what is part d asking on homework 2".

Dates: the HW/Lab PDFs carry last year's calendar ("Due Wednesday, September 17" is a
Thursday in 2026), so the stale line is dropped and the Fall 2026 date is derived
from config (semester_start + hw_num_to_week / lab_num_to_week), which follows
Syllabus.tex. The PDFs themselves are untouched.

Run from the repo root on a UMN network with AI Gateway creds:

    set -a; . ./.env; set +a
    export OPENAI_API_KEY="$AIGATEWAY_API_KEY" OPENAI_BASE_URL="https://api.aigateway.umn.edu/v1"
    /home/chois/gitsrcs/AITA3101/.venv/bin/python add_document.py            # rebuild index
    /home/chois/gitsrcs/AITA3101/.venv/bin/python add_document.py --dry-run  # collect + self-check only

Changing the embedding model invalidates retrieval_min_score: re-derive it with
eval/sweep_threshold.py and confirm with eval/retrieval_eval.py before deploying.
"""
import datetime as dt
import os
import re
import sys

from config import CONFIG
from aita_core.ingest import (
    _extract_pdf_text, chunk_documents, collect_handouts, collect_slides,
    collect_syllabus, get_week_for_filename, run_ingestion,
)

HW_DIR = os.path.join(CONFIG.course_materials_dir, "Homework handouts", "Homework handouts")
SUPP_DIR = os.path.join(CONFIG.course_materials_dir, "Supplements")  # generated copies, for review
BODY_CAP = CONFIG.chunk_size - 150  # header + body must fit one chunk

# Wednesdays with a quiz or exam, by instructional week: Syllabus.tex "Schedule" table.
WED_EVENTS = {3: "Quiz 1", 4: "Quiz 2", 5: "Quiz 3", 6: "Quiz 4", 7: "Midterm exam 1",
              8: "Quiz 5", 9: "Quiz 6", 10: "Quiz 7", 11: "Quiz 8", 12: "Midterm exam 2",
              13: "Quiz 9", 14: "Quiz 10", 15: "Quiz 11"}
FINAL_EXAM = ("Final exam: the syllabus lists Tuesday 12/16, 10:30am-12:30pm (UMN-scheduled "
              "time). Confirm the date and room on onestop.umn.edu.")

GUIDELINES_LABEL = "Homework: Writing and submission guidelines"
TIPS_LABEL = "Supplement: Excel tips from the lab handouts"
CALENDAR_LABEL = "Supplement: Course calendar (Fall 2026)"

_BOILERPLATE = re.compile(
    r"Show work and include units.*?(?:described on the last page\.|in your submission\)\.)\s*", re.S)
_RUBRIC_START = "I will be grading these aspects"
_STALE_DATE = re.compile(r"^(?:Due|In-class on) \w+day, \w+ \d+.*$\n?", re.M)
_TITLE = re.compile(r"^CEGE 3102: (?:Homework|Lab) \d+\s*$\n?", re.M)
_PAGE_NO = re.compile(r"^\d+\s*$\n?", re.M)
_PROBLEM = re.compile(r"^Problem (\d+)\b", re.M)
_PART = re.compile(r"^\([a-z]\)", re.M)
_TIPS = re.compile(r"You may find the Excel.*", re.S)


def _natkey(s):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


def wednesday(week):
    start = dt.date.fromisoformat(CONFIG.semester_start)  # Monday of week 1
    return start + dt.timedelta(days=7 * (week - 1) + 2)


def fmt(d):
    return f"{d:%A, %B} {d.day}, {d.year}"


def _week(filename):
    return get_week_for_filename(filename, CONFIG.topic_num_to_week, CONFIG.hw_num_to_week,
                                 CONFIG.lab_num_to_week, CONFIG.study_guide_to_week)


def _doc(text, label, path, week):
    return {"text": text.strip(),
            "metadata": {"source": path, "source_label": label, "max_week": week}}


def _clean(text):
    for rx in (_PAGE_NO, _TITLE, _STALE_DATE, _BOILERPLATE):
        text = rx.sub("", text)
    return text.strip()


def _capped(header, body, cap=BODY_CAP):
    """header+body as one chunk; if too long, split at (a)/(b) part boundaries, repeating the header."""
    if len(body) <= cap:
        return [f"{header}\n{body}"]
    bounds = [m.start() for m in _PART.finditer(body) if m.start() > 0] + [len(body)]
    segs, start, prev = [], 0, 0
    for b in bounds:
        if b - start > cap and prev > start:
            segs.append(body[start:prev])
            start = prev
        prev = b
    segs.append(body[start:])
    # A single part (or the stem before part (a)) can itself exceed the cap: cut it at
    # the last line break before the cap rather than letting chunk_text split mid-sentence.
    hard = []
    for seg in segs:
        while len(seg) > cap:
            cut = seg.rfind("\n", 0, cap)
            cut = cut if cut > cap // 2 else cap
            hard.append(seg[:cut])
            seg = seg[cut:]
        hard.append(seg)
    return [f"{header}{' (continued)' if i else ''}\n{s.strip()}"
            for i, s in enumerate(hard) if s.strip()]


def _hw_files():
    for fn in sorted(os.listdir(HW_DIR), key=_natkey):
        if fn.endswith(".pdf") and "solution" not in fn.lower():
            yield fn, os.path.join(HW_DIR, fn)


def collect_homework_problems(config):
    """Homework: overview + one doc per problem. Labs: one doc (split at parts if long)."""
    docs = []
    for fn, path in _hw_files():
        label, raw = f"Homework: {fn}", _extract_pdf_text(path)
        m = re.match(r"HW(\d+)", fn)
        if m:
            n = int(m.group(1))
            week = config.hw_num_to_week[n]
            due = f"due {fmt(wednesday(week))} at the start of class (Week {week})"
            rub = raw.find(_RUBRIC_START)
            body = _clean(raw[:rub] if rub > 0 else raw)
            starts = [pm.start() for pm in _PROBLEM.finditer(body)]
            probs = [body[a:b].strip() for a, b in zip(starts, starts[1:] + [len(body)])]
            intro = body[:starts[0]].strip() if starts else ""
            blurbs = []
            for p in probs:
                first, _, rest = p.partition("\n")
                blurbs.append(f"{first.strip()}: {' '.join(rest.split())[:140]}...")
            overview = (f"CEGE 3102 Homework {n} (HW{n}) — overview. {due[0].upper() + due[1:]}. "
                        f"Submit on Canvas.\n{intro}\n{len(probs)} problems:\n" + "\n".join(blurbs))
            docs.append(_doc(overview, label, path, week))
            for p in probs:
                first, _, rest = p.partition("\n")
                header = f"HW{n} — {first.strip()} — CEGE 3102 Homework {n}, {due}"
                docs += [_doc(t, label, path, week) for t in _capped(header, rest.strip())]
            print(f"  {label}: {len(probs)} problems -> {1 + len(probs)} docs ({due})")
        else:
            n = int(re.match(r"Lab\s*(\d+)", fn).group(1))
            week = config.lab_num_to_week[n]
            header = f"Lab {n} — in-class lab on {fmt(wednesday(week))} (Week {week})"
            parts = _capped(header, _clean(raw))
            docs += [_doc(t, label, path, week) for t in parts]
            print(f"  {label}: {len(parts)} doc(s) (Week {week})")
    return docs


def collect_guidelines(config):
    """The submission rules + writing rubric that every HW/Lab PDF repeats, once."""
    # HW2's rubric page, not HW1's: HW1 carries an older 5/3/1/0 scale, HW2-HW12 all use 2/1/0.
    hw2 = _PAGE_NO.sub("", _extract_pdf_text(os.path.join(HW_DIR, "HW2.pdf")))
    lab1 = _PAGE_NO.sub("", _extract_pdf_text(os.path.join(HW_DIR, "Lab 1.pdf")))
    hw_rules = _BOILERPLATE.search(hw2).group(0).strip()
    lab_rules = _BOILERPLATE.search(lab1).group(0).strip()
    rubric = hw2[hw2.find(_RUBRIC_START):].strip()
    rules = ("CEGE 3102 homework and lab submission rules (printed at the top of every "
             f"assignment).\n\nHomework:\n{hw_rules}\n\nLabs:\n{lab_rules}")
    rub = ("CEGE 3102 homework writing-clarity rubric (printed on the last page of every "
           "homework; each item is scored on the levels shown, from Fulfilled down to Not "
           f"effective).\n\n{rubric}")
    return [_doc(rules, GUIDELINES_LABEL, "", 1), _doc(rub, GUIDELINES_LABEL, "", 1)]


def collect_lab_tips(config):
    """The Excel function tips embedded in some lab handouts, de-duplicated into one doc."""
    bullets, labs = {}, []
    for fn, path in _hw_files():
        if not fn.startswith("Lab"):
            continue
        m = _TIPS.search(_PAGE_NO.sub("", _extract_pdf_text(path)))
        if not m:
            continue
        labs.append(fn[:-4])
        for b in re.split(r"\n?•\s*", m.group(0))[1:]:
            b = " ".join(b.split())
            bullets.setdefault(b.split("(")[0].strip().lower(), b)
    text = (f"Excel tips from the CEGE 3102 lab handouts ({', '.join(labs)}). The labs say: "
            "\"You may find the Excel " + ", ".join(sorted(bullets)) + " functions useful.\"\n"
            + "\n".join(f"• {b}" for _, b in sorted(bullets.items())))
    return [_doc(text, TIPS_LABEL, "", 1)]


def collect_calendar(config):
    """Fall 2026 due dates, labs, quizzes and exams, derived from config + the syllabus table."""
    start = dt.date.fromisoformat(config.semester_start)
    hw_by_week = {w: n for n, w in config.hw_num_to_week.items()}
    lab_by_week = {w: n for n, w in config.lab_num_to_week.items()}
    rows = []
    for w, topics in sorted(config.week_topics.items()):
        mon, wed = start + dt.timedelta(days=7 * (w - 1)), wednesday(w)
        items = []
        if w in WED_EVENTS:
            items.append(f"{WED_EVENTS[w]} on {fmt(wed)}")
        if w in hw_by_week:
            items.append(f"HW{hw_by_week[w]} due {fmt(wed)} at the start of class")
        if w in lab_by_week:
            items.append(f"Lab {lab_by_week[w]} in class on {fmt(wed)}")
        rows.append(f"Week {w} (Monday {mon:%B} {mon.day}): {'; '.join(topics)}. "
                    + ("; ".join(items) + "." if items else "No quiz, homework due, or lab."))
    hw_list = "\n".join(f"- HW{n} (Homework {n}): due {fmt(wednesday(w))}, Week {w}"
                        for n, w in sorted(config.hw_num_to_week.items()))
    lab_list = "\n".join(f"- Lab {n}: in class {fmt(wednesday(w))}, Week {w}"
                         for n, w in sorted(config.lab_num_to_week.items()))
    exam_list = "\n".join(f"- {name}: {fmt(wednesday(w))}, Week {w}"
                          for w, name in sorted(WED_EVENTS.items()))
    preamble = ("CEGE 3102 Fall 2026 course calendar. Classes meet Monday and Wednesday; the "
                "first class is Wednesday, September 9, 2026. Homework is due Wednesdays at the "
                "start of class, labs are in class on Wednesdays, and quizzes and exams are on "
                "Wednesdays. Dates follow the Fall 2026 syllabus, which notes that dates and "
                "topics may change; Canvas is authoritative.")
    dates = (f"{preamble}\n\nHomework due dates:\n{hw_list}\n\nLab dates:\n{lab_list}\n\n"
             f"Quizzes and exams:\n{exam_list}\n{FINAL_EXAM}")
    weekly = f"{preamble}\n\nWeek by week:\n" + "\n".join(rows) + f"\n{FINAL_EXAM}"
    return [_doc(dates, CALENDAR_LABEL, "", 1), _doc(weekly, CALENDAR_LABEL, "", 1)]


COLLECTORS = [
    ("lecture handouts", collect_handouts),
    ("homework and labs (one problem per chunk)", collect_homework_problems),
    ("slide content", collect_slides),
    ("syllabus", collect_syllabus),
    ("writing and submission guidelines", collect_guidelines),
    ("Excel tips from the labs", collect_lab_tips),
    ("course calendar", collect_calendar),
]


def collect_all():
    docs = []
    for name, fn in COLLECTORS:
        print(f"\nCollecting {name}...")
        docs += fn(CONFIG)
    return docs


def selfcheck(docs):
    """Fails loudly if a problem spans chunks or boilerplate leaked back in."""
    by_label = {}
    for d in docs:
        lab, t = d["metadata"]["source_label"], d["text"]
        by_label[lab] = by_label.get(lab, 0) + 1
        if lab.startswith("Homework: ") and lab != GUIDELINES_LABEL:
            assert _RUBRIC_START not in t, f"rubric leaked into {lab}"
            assert "Show work and include units" not in t, f"boilerplate leaked into {lab}"
            assert not _STALE_DATE.search(t), f"stale PDF date left in {lab}"
            assert len(t) <= CONFIG.chunk_size, f"{lab} doc is {len(t)} chars; would span chunks"
    for n in range(1, 13):
        assert by_label.get(f"Homework: HW{n}.pdf", 0) >= 6, f"HW{n}: expected overview + 5 problems"
    assert by_label[GUIDELINES_LABEL] == 2 and by_label[CALENDAR_LABEL] == 2 and by_label[TIPS_LABEL] == 1
    chunks = chunk_documents(docs, CONFIG.chunk_size, CONFIG.chunk_overlap)
    kinds = {}
    for d in docs:
        k = d["metadata"]["source_label"].split(":")[0]
        kinds[k] = kinds.get(k, 0) + 1
    print(f"\nself-check OK: {len(docs)} docs -> {len(chunks)} chunks; docs by kind: {kinds}")
    return chunks


def write_supplements(docs):
    os.makedirs(SUPP_DIR, exist_ok=True)
    for label in (GUIDELINES_LABEL, TIPS_LABEL, CALENDAR_LABEL):
        body = "\n\n---\n\n".join(d["text"] for d in docs if d["metadata"]["source_label"] == label)
        name = label.split(": ", 1)[1].replace("/", "-") + ".md"
        with open(os.path.join(SUPP_DIR, name), "w", encoding="utf-8") as f:
            f.write(f"<!-- generated by add_document.py; edit the generator, not this file -->\n{body}\n")


if __name__ == "__main__":
    docs = collect_all()
    selfcheck(docs)
    write_supplements(docs)
    if "--dry-run" in sys.argv:
        print("dry run: no embeddings, index unchanged")
        sys.exit(0)
    run_ingestion(CONFIG, collectors=[("all documents (pre-collected)", lambda cfg: docs)])
