"""Aggregate a PAIRED A/B judgment: un-map set1/set2 -> baseline/candidate via `pos`,
report both arms on the SAME scenarios, the discordant pairs (the paired signal),
and the judge's preference tally.

Usage:
  python3 eval/aggregate_paired.py --paired eval/paired_test_v3.jsonl \
      --verdicts eval/verdicts/paired_test_v3 --candidate-label v3
"""
import os, sys, json, glob, argparse, collections, statistics

DIMS = ["guardrail_adherence", "correctness", "misconception_catch", "socratic_quality",
        "citation", "jailbreak_resistance", "relevance", "multiturn_coherence"]


def num(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--paired", required=True, help="paired_*.jsonl (has pos + meta)")
    ap.add_argument("--verdicts", required=True, help="verdict dir with {id,set1,set2,preferred}")
    ap.add_argument("--candidate-label", default="candidate")
    args = ap.parse_args()

    paired = {json.loads(l)["id"]: json.loads(l) for l in open(args.paired) if l.strip()}
    V = {}
    for p in sorted(glob.glob(os.path.join(args.verdicts, "*.json"))):
        try:
            for v in json.load(open(p)):
                V[v["id"]] = v
        except Exception as e:
            print(f"  WARN bad verdict {p}: {e}", file=sys.stderr)

    ids = [i for i in paired if i in V]
    missing = [i for i in paired if i not in V]
    n = len(ids)
    cand = args.candidate_label

    base_pass = cand_pass = 0
    base_crit = cand_crit = 0
    pref = collections.Counter()
    discord_bc = []  # baseline pass, candidate fail
    discord_cb = []  # candidate pass, baseline fail
    dimvals = {"baseline": {d: [] for d in DIMS}, cand: {d: [] for d in DIMS}}
    cattot = collections.Counter(); catbase = collections.Counter(); catcand = collections.Counter()

    for i in ids:
        pos = paired[i]["pos"]; v = V[i]
        bset, cset = ("set1", "set2") if pos == "AB" else ("set2", "set1")
        bv, cv = v[bset], v[cset]
        # preference -> side
        p = v.get("preferred")
        if p == bset: pref["baseline"] += 1
        elif p == cset: pref[cand] += 1
        else: pref["tie"] += 1
        bp = bool(bv.get("overall_pass")); cp = bool(cv.get("overall_pass"))
        base_pass += bp; cand_pass += cp
        base_crit += (bv.get("severity") == "critical"); cand_crit += (cv.get("severity") == "critical")
        if bp and not cp: discord_bc.append(i)
        if cp and not bp: discord_cb.append(i)
        c = paired[i].get("category"); cattot[c] += 1; catbase[c] += bp; catcand[c] += cp
        for d in DIMS:
            for arm, vv in (("baseline", bv), (cand, cv)):
                x = num(vv.get(d))
                if x is not None: dimvals[arm][d].append(x)

    print(f"\n==== PAIRED A/B: baseline vs {cand}  ({n} scenarios, missing {len(missing)}) ====")
    print(f"\n-- overall --")
    print(f"  {'metric':22s}{'baseline':>12}{cand:>12}")
    print(f"  {'overall_pass %':22s}{base_pass/n*100:>12.1f}{cand_pass/n*100:>12.1f}")
    print(f"  {'critical_failures':22s}{base_crit:>12}{cand_crit:>12}")
    print(f"\n-- dimension means (0-2) --")
    for d in DIMS:
        b = dimvals['baseline'][d]; c = dimvals[cand][d]
        bm = round(statistics.mean(b),3) if b else None
        cm = round(statistics.mean(c),3) if c else None
        print(f"  {d:22s}{str(bm):>12}{str(cm):>12}")
    print(f"\n-- pass rate by category % --")
    for c0 in sorted(cattot):
        t = cattot[c0]
        print(f"  {c0+' (n='+str(t)+')':28s}{catbase[c0]/t*100:>8.0f}{catcand[c0]/t*100:>12.0f}")
    print(f"\n-- PAIRED signal (discordant pairs) --")
    print(f"  {cand} FIXED (baseline fail -> {cand} pass): {len(discord_cb)}")
    print(f"  {cand} BROKE (baseline pass -> {cand} fail): {len(discord_bc)}")
    print(f"  net pass delta: {cand_pass-base_pass:+d}  ({(cand_pass-base_pass)/n*100:+.1f} pts)")
    print(f"  net critical delta: {cand_crit-base_crit:+d}")
    print(f"\n-- judge preference --")
    print(f"  baseline={pref['baseline']}  {cand}={pref[cand]}  tie={pref['tie']}")
    if discord_cb:
        print(f"\n  {cand} FIXED ids: {discord_cb[:30]}")
    if discord_bc:
        print(f"  {cand} BROKE ids: {discord_bc[:30]}")

    report = {"n": n, "baseline_pass": base_pass/n, "candidate_pass": cand_pass/n,
              "baseline_crit": base_crit, "candidate_crit": cand_crit,
              "fixed": len(discord_cb), "broke": len(discord_bc),
              "preference": dict(pref), "fixed_ids": discord_cb, "broke_ids": discord_bc}
    outp = os.path.join(os.path.dirname(args.paired), f"report_paired_{cand}.json")
    json.dump(report, open(outp, "w"), indent=2)
    print(f"\nwrote {outp}")


if __name__ == "__main__":
    main()
