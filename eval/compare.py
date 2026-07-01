"""Side-by-side comparison of judge verdicts across variants on a common id set.

Restricts to the INTERSECTION of ids scored by every variant (and an optional
--subset id file, e.g. dev.jsonl) so all variants share the same denominator.

Usage:
  python3 eval/compare.py --transcripts eval/transcripts_baseline.jsonl \
    --subset eval/dev.jsonl \
    --variant baseline:eval/verdicts/baseline \
    --variant v1:eval/verdicts/dev_v1 \
    --variant v2:eval/verdicts/dev_v2
"""
import os, sys, json, glob, argparse, collections, statistics

DIMS = ["guardrail_adherence", "correctness", "misconception_catch", "socratic_quality",
        "citation", "jailbreak_resistance", "relevance", "multiturn_coherence"]


def load_verdicts(vdir):
    out = {}
    for p in sorted(glob.glob(os.path.join(vdir, "*.json"))):
        try:
            for v in json.load(open(p)):
                out[v["id"]] = v
        except Exception as e:
            print(f"  WARN bad verdict file {p}: {e}", file=sys.stderr)
    return out


def num(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--transcripts", required=True, help="for category metadata")
    ap.add_argument("--subset", default="", help="optional id-restriction file (jsonl with id field)")
    ap.add_argument("--variant", action="append", required=True, help="label:verdict_dir (repeatable)")
    args = ap.parse_args()

    meta = {}
    for l in open(args.transcripts):
        if l.strip():
            r = json.loads(l); meta[r["id"]] = r

    subset = None
    if args.subset:
        subset = set(json.loads(l)["id"] for l in open(args.subset) if l.strip())

    variants = []
    for spec in args.variant:
        label, vdir = spec.split(":", 1)
        variants.append((label, load_verdicts(vdir)))

    # common id set = intersection of all variants' scored ids (∩ subset ∩ meta)
    common = set(meta)
    if subset is not None:
        common &= subset
    for _, V in variants:
        common &= set(V)
    common = sorted(common)
    n = len(common)
    print(f"\n==== VARIANT COMPARISON on {n} common scenarios ====")
    if subset is not None:
        for label, V in variants:
            extra = (set(V) & (subset or set(meta))) - set(common)
            miss = (subset & set(meta)) - set(V)
            print(f"  [{label}] scored {len(set(V) & subset)} of subset; {len(miss)} unscored")

    cats = sorted(set(meta[i]["category"] for i in common))

    def col(label, V):
        passes = sum(1 for i in common if V[i].get("overall_pass"))
        crit = sum(1 for i in common if V[i].get("severity") == "critical")
        dimmean = {}
        for d in DIMS:
            vals = [num(V[i].get(d)) for i in common]
            vals = [x for x in vals if x is not None]
            dimmean[d] = round(statistics.mean(vals), 3) if vals else None
        catpass = {}
        for c in cats:
            ids = [i for i in common if meta[i]["category"] == c]
            catpass[c] = round(sum(1 for i in ids if V[i].get("overall_pass")) / len(ids), 3) if ids else None
        tags = collections.Counter()
        for i in common:
            if not V[i].get("overall_pass"):
                for t in (V[i].get("tags") or []): tags[t] += 1
        return {"pass": passes / n if n else 0, "crit": crit, "dim": dimmean,
                "cat": catpass, "tags": tags}

    cols = [(label, col(label, V)) for label, V in variants]

    w = 14
    def row(name, fmt):
        print(f"  {name:24s}" + "".join(f"{fmt(c):>{w}}" for _, c in cols))

    print("\n-- overall --")
    print(f"  {'metric':24s}" + "".join(f"{label:>{w}}" for label, _ in cols))
    row("overall_pass %", lambda c: f"{c['pass']*100:.1f}")
    row("critical_failures", lambda c: f"{c['crit']}")
    print("\n-- dimension means (0-2) --")
    for d in DIMS:
        row(d, lambda c, d=d: f"{c['dim'][d]}")
    print("\n-- pass rate by category % --")
    for c0 in cats:
        n_c = sum(1 for i in common if meta[i]["category"] == c0)
        row(f"{c0} (n={n_c})", lambda c, c0=c0: f"{c['cat'][c0]*100:.0f}" if c['cat'][c0] is not None else "-")
    print("\n-- top failure tags --")
    for label, c in cols:
        print(f"  [{label}] {dict(c['tags'].most_common(8))}")

if __name__ == "__main__":
    main()
