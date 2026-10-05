"""Retrieval eval: does the context the model sees contain the source that answers?

Each line of retrieval_set.jsonl names the sources (by file name) that hold the
answer; any one of them counts. The context is assembled exactly as rag.chat
does it, minus the LLM call. Off-topic items pass when nothing is retrieved.

    OPENAI_API_KEY=$AIGATEWAY_API_KEY OPENAI_BASE_URL=https://api.aigateway.umn.edu/v1 \
        .venv/bin/python eval/retrieval_eval.py baseline

Writes eval/results/<tag>.json; pass two tags to compare: ... compare a b
"""
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
WEEK = 11  # instructional week the expectations assume (current HW = HW9)


def gather(rag, q, tries=4):
    """Context for q; the Vertex embed call times out now and then, so retry."""
    import httpx
    from google.auth.exceptions import TransportError
    import openai
    # The gateway speaks the OpenAI protocol, so an embed timeout surfaces as
    # openai.APITimeoutError there and as httpx/TransportError on Vertex.
    timeouts = (httpx.TimeoutException, TransportError,
                openai.APITimeoutError, openai.APIConnectionError)
    for t in range(tries):
        try:
            return _gather(rag, q)
        except timeouts:
            print(f"  (embed timeout, retry {t + 1})")
    return _gather(rag, q)


def _gather(rag, q):
    if hasattr(rag, "gather_context"):                  # history already folded into q
        return rag.gather_context(q, current_week=WEEK)
    ctx = rag.retrieve(q, current_week=WEEK)         # aita_core <= 0.7.3
    ctx = rag._inject_current_hw(q, ctx, WEEK)
    return rag._inject_exam_review(q, ctx, WEEK)


def run(tag):
    from config import CONFIG
    from aita_core.config import set_config
    CONFIG.retrieval_k = int(os.getenv("K", CONFIG.retrieval_k))   # K=8 to try a wider k
    set_config(CONFIG)
    from aita_core import rag

    items = [json.loads(l) for l in open(os.path.join(HERE, "retrieval_set.jsonl"))]
    rows = []
    for it in items:
        hist = [h if isinstance(h, dict) else {"role": "user", "content": h}
                for h in it.get("history", [])]
        q = it["q"]
        if hist and hasattr(rag, "_standalone_query"):       # aita_core >= 0.7.5
            q = rag._standalone_query(it["q"], hist)
            print(f"  rewrite {it['id']}: {it['q']!r} -> {q!r}")
        ctx = gather(rag, q)
        names = [c["source"].split(": ", 1)[-1] for c in ctx]
        if it["expect"]:
            rank = next((i + 1 for i, n in enumerate(names) if n in it["expect"]), None)
            ok = rank is not None
        else:
            rank, ok = None, not ctx
        rows.append({"id": it["id"], "cat": it["cat"], "ok": ok, "rank": rank,
                     "n": len(ctx), "chars": sum(len(c["text"]) for c in ctx),
                     "got": names})
        print(f"{'PASS' if ok else 'FAIL'} {it['id']:6s} rank={rank or '-'}  {it['q'][:50]:50s} {names[:4]}")
    os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
    json.dump(rows, open(os.path.join(HERE, "results", f"{tag}.json"), "w"), indent=1)
    summary(rows, tag)


def summary(rows, tag):
    by = collections.defaultdict(list)
    for r in rows:
        by[r["cat"]].append(r)
    print(f"\n== {tag}")
    for cat, rs in by.items():
        print(f"  {cat:11s} {sum(r['ok'] for r in rs):2d}/{len(rs)}")
    on = [r for r in rows if r["cat"] not in ("offtopic", "greeting")]   # pass = no context
    mrr = sum(1 / r["rank"] for r in on if r["rank"]) / len(on)
    print(f"  {'TOTAL':11s} {sum(r['ok'] for r in rows):2d}/{len(rows)}   MRR {mrr:.3f}   "
          f"mean context {sum(r['chars'] for r in on) / len(on):,.0f} chars in "
          f"{sum(r['n'] for r in on) / len(on):.1f} chunks")


def compare(a, b):
    ra = {r["id"]: r for r in json.load(open(os.path.join(HERE, "results", f"{a}.json")))}
    rb = json.load(open(os.path.join(HERE, "results", f"{b}.json")))
    for r in rb:
        if r["ok"] != ra[r["id"]]["ok"]:
            print(f"  {'fixed' if r['ok'] else 'BROKE'} {r['id']}: {ra[r['id']]['got'][:3]} -> {r['got'][:3]}")
    summary(list(ra.values()), a)
    summary(rb, b)


if __name__ == "__main__":
    if sys.argv[1] == "compare":
        compare(sys.argv[2], sys.argv[3])
    else:
        run(sys.argv[1])
