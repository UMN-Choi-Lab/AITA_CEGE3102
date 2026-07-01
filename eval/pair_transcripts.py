"""Pair two runs' transcripts by scenario id for a controlled A/B (paired) judgment.

Each paired record holds BOTH TA response-sets for the same scenario (same frozen
student turns via --replay), presented as set1/set2 with a deterministic, per-index
alternating order (pos = "AB" or "BA") to cancel judge position-bias. aggregate_paired.py
un-maps set1/set2 back to baseline/candidate using pos.

Usage:
  python3 eval/pair_transcripts.py --baseline eval/transcripts_baseline.jsonl \
     --candidate eval/transcripts_test_v3.jsonl --subset eval/test.jsonl \
     --out eval/paired_test_v3.jsonl
"""
import os, sys, json, argparse

META = ["category", "guardrail_critical", "week", "current_week", "topic",
        "turn_type", "expected_behavior", "embedded_error"]


def load(path):
    return {json.loads(l)["id"]: json.loads(l) for l in open(path) if l.strip()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--subset", default="", help="restrict to ids in this jsonl")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    B = load(args.baseline)
    C = load(args.candidate)
    ids = set(B) & set(C)
    if args.subset:
        ids &= set(json.loads(l)["id"] for l in open(args.subset) if l.strip())
    ids = sorted(ids)

    out = []
    for k, i in enumerate(ids):
        pos = "AB" if k % 2 == 0 else "BA"  # deterministic alternation cancels position bias
        base_t = B[i]["transcript"]
        cand_t = C[i]["transcript"]
        if pos == "AB":
            set1, set2 = base_t, cand_t
        else:
            set1, set2 = cand_t, base_t
        rec = {"id": i, "pos": pos, "set1": set1, "set2": set2}
        for m in META:
            rec[m] = B[i].get(m)
        out.append(rec)

    with open(args.out, "w") as f:
        for r in out:
            f.write(json.dumps(r) + "\n")
    print(f"paired {len(out)} scenarios -> {args.out}  "
          f"(baseline∩candidate{'∩subset' if args.subset else ''}); "
          f"pos AB={sum(1 for r in out if r['pos']=='AB')} BA={sum(1 for r in out if r['pos']=='BA')}")


if __name__ == "__main__":
    main()
