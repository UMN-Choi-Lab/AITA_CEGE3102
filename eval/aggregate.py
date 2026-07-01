"""Aggregate judge verdicts into a metrics report.

Reads all verdict JSON files in eval/verdicts/<tag>/ (each a JSON array of verdicts)
plus the transcripts file (for category metadata), and prints + writes a report.

Usage:
  python3 eval/aggregate.py --tag baseline --transcripts eval/transcripts_baseline.jsonl
"""
import os, sys, json, glob, argparse, collections, statistics

HERE = os.path.dirname(os.path.abspath(__file__))
DIMS = ["guardrail_adherence", "correctness", "misconception_catch", "socratic_quality",
        "citation", "jailbreak_resistance", "relevance", "multiturn_coherence"]

def load_verdicts(vdir):
    out = {}
    for p in sorted(glob.glob(os.path.join(vdir, "*.json"))):
        try:
            arr = json.load(open(p))
        except Exception as e:
            print(f"  WARN bad verdict file {p}: {e}", file=sys.stderr); continue
        for v in arr:
            out[v["id"]] = v
    return out

def num(x):
    return x if isinstance(x, (int, float)) else None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--transcripts", required=True)
    args = ap.parse_args()

    meta = {}
    for l in open(args.transcripts):
        if l.strip():
            r = json.loads(l); meta[r["id"]] = r
    vdir = os.path.join(HERE, "verdicts", args.tag)
    verdicts = load_verdicts(vdir)

    ids = [i for i in meta if i in verdicts]
    missing = [i for i in meta if i not in verdicts]
    n = len(ids)
    passes = sum(1 for i in ids if verdicts[i].get("overall_pass"))
    crit = [i for i in ids if verdicts[i].get("severity") == "critical"]

    # per-category pass rate
    cat_tot = collections.Counter(); cat_pass = collections.Counter()
    for i in ids:
        c = meta[i]["category"]; cat_tot[c] += 1
        if verdicts[i].get("overall_pass"): cat_pass[c] += 1
    # dimension means (ignoring NA)
    dim_vals = {d: [] for d in DIMS}
    for i in ids:
        for d in DIMS:
            v = num(verdicts[i].get(d))
            if v is not None: dim_vals[d].append(v)
    # failure tag histogram
    tags = collections.Counter()
    for i in ids:
        if not verdicts[i].get("overall_pass"):
            for t in (verdicts[i].get("tags") or []): tags[t] += 1

    report = {
        "tag": args.tag, "n_scored": n, "n_missing": len(missing),
        "overall_pass_rate": round(passes / n, 4) if n else 0,
        "critical_failures": len(crit),
        "pass_rate_by_category": {c: round(cat_pass[c]/cat_tot[c], 3) for c in sorted(cat_tot)},
        "dimension_means": {d: round(statistics.mean(v), 3) if v else None for d, v in dim_vals.items()},
        "failure_tags": dict(tags.most_common()),
        "critical_ids": crit[:50],
        "missing_ids": missing[:20],
    }
    outp = os.path.join(HERE, f"report_{args.tag}.json")
    json.dump(report, open(outp, "w"), indent=2)

    print(f"==== REPORT [{args.tag}] ====")
    print(f"scored {n} (missing {len(missing)})")
    print(f"OVERALL PASS RATE: {report['overall_pass_rate']*100:.1f}%   critical: {len(crit)}")
    print("\nby category:")
    for c, r in sorted(report["pass_rate_by_category"].items(), key=lambda x: x[1]):
        print(f"  {c:24s} {r*100:5.1f}%  (n={cat_tot[c]})")
    print("\ndimension means (0-2, NA ignored):")
    for d, m in report["dimension_means"].items():
        print(f"  {d:22s} {m}")
    print("\ntop failure tags:", dict(tags.most_common(12)))
    print(f"\nwrote {outp}")

if __name__ == "__main__":
    main()
