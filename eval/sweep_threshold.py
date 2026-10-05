"""Sweep retrieval_min_score on the current index and report pass/fail per threshold.

A cosine threshold is specific to the embedding model that produced the index, so
it must be re-derived whenever the model changes. One retrieval pass is taken with
the threshold at 0; because _balance_sources preserves score order when no balance
rule is set, every higher threshold is exactly a score-prefix of that pass and can
be simulated without re-embedding.

    OPENAI_API_KEY=... OPENAI_BASE_URL=... .venv/bin/python eval/sweep_threshold.py
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
WEEK = 11

from config import CONFIG
from aita_core.config import set_config
CONFIG.retrieval_min_score = 0.0
set_config(CONFIG)
from aita_core import rag

items = [json.loads(l) for l in open(os.path.join(HERE, "retrieval_set.jsonl"))]
probe = []
for it in items:
    hist = [h if isinstance(h, dict) else {"role": "user", "content": h}
            for h in it.get("history", [])]
    q = it["q"]
    if hist:
        q = rag._standalone_query(it["q"], hist)
    chunks = rag.retrieve(q, current_week=WEEK)
    probe.append({"id": it["id"], "cat": it["cat"], "expect": it["expect"], "q": q,
                  "hits": [(c["source"].split(": ", 1)[-1], round(c["score"], 4))
                           for c in chunks]})
    top = probe[-1]["hits"][0][1] if probe[-1]["hits"] else None
    print("  %-7s top=%s  %s" % (it["id"], top, [h[0][:28] for h in probe[-1]["hits"][:2]]))

json.dump(probe, open(os.path.join(HERE, "results", "sweep_probe.json"), "w"), indent=1)

print("\n%-8s %7s %9s %9s %8s" % ("thresh", "TOTAL", "answerable", "must-empty", "mean n"))
for th in [0.0, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.62]:
    ok = ans_ok = emp_ok = 0
    ans = emp = 0
    nchunks = []
    for p in probe:
        kept = [h for h in p["hits"] if h[1] >= th]
        if p["expect"]:
            ans += 1
            good = any(n in p["expect"] for n, _ in kept)
            ans_ok += good; ok += good
            nchunks.append(len(kept))
        else:
            emp += 1
            good = not kept
            emp_ok += good; ok += good
    print("%-8.2f %4d/%-3d %6d/%-3d %6d/%-3d %8.1f"
          % (th, ok, len(probe), ans_ok, ans, emp_ok, emp, sum(nchunks)/len(nchunks)))
