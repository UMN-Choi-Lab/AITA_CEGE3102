"""Deterministic stratified dev/test split of scenarios (by category+turn_type).
Tune prompts on dev; report the final unbiased number on test.

Usage: python3 eval/split_dev_test.py --test-frac 0.35
Writes eval/dev.jsonl and eval/test.jsonl.
"""
import os, sys, json, argparse, collections, random

HERE = os.path.dirname(os.path.abspath(__file__))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default=os.path.join(HERE, "scenarios.jsonl"))
    ap.add_argument("--test-frac", type=float, default=0.35)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    rows = [json.loads(l) for l in open(args.inp) if l.strip()]
    strata = collections.defaultdict(list)
    for r in rows:
        strata[(r["category"], r["turn_type"])].append(r)

    rng = random.Random(args.seed)
    dev, test = [], []
    for key, items in sorted(strata.items()):
        items = sorted(items, key=lambda r: r["id"])
        rng.shuffle(items)
        n_test = max(1, round(len(items) * args.test_frac)) if len(items) > 1 else 0
        test += items[:n_test]
        dev += items[n_test:]

    dev.sort(key=lambda r: r["id"]); test.sort(key=lambda r: r["id"])
    open(os.path.join(HERE, "dev.jsonl"), "w").write("\n".join(json.dumps(r) for r in dev) + "\n")
    open(os.path.join(HERE, "test.jsonl"), "w").write("\n".join(json.dumps(r) for r in test) + "\n")
    print(f"dev={len(dev)}  test={len(test)}  (test_frac={args.test_frac})")
    dc = collections.Counter(r["category"] for r in dev)
    tc = collections.Counter(r["category"] for r in test)
    for c in sorted(set(dc) | set(tc)):
        print(f"  {c:24s} dev={dc[c]:3d} test={tc[c]:3d}")

if __name__ == "__main__":
    main()
