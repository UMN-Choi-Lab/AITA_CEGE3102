"""Split a transcripts JSONL into batch files for parallel judging, and print a
JSON manifest (list of batch file paths) to stdout.

Usage:
  python3 eval/split_transcripts.py --in eval/transcripts_baseline.jsonl \
      --tag baseline --size 15
"""
import os, sys, json, argparse, shutil

HERE = os.path.dirname(os.path.abspath(__file__))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--size", type=int, default=15)
    args = ap.parse_args()

    rows = [l for l in open(args.inp) if l.strip()]
    bdir = os.path.join(HERE, "batches", args.tag)
    vdir = os.path.join(HERE, "verdicts", args.tag)
    if os.path.isdir(bdir):
        shutil.rmtree(bdir)
    os.makedirs(bdir, exist_ok=True)
    os.makedirs(vdir, exist_ok=True)

    paths, counts = [], []
    for i in range(0, len(rows), args.size):
        name = f"batch_{i//args.size:03d}.jsonl"
        p = os.path.join(bdir, name)
        chunk = rows[i:i+args.size]
        with open(p, "w") as f:
            f.writelines(chunk)
        paths.append(p)
        counts.append(len(chunk))

    print(json.dumps({
        "tag": args.tag, "n_transcripts": len(rows), "n_batches": len(paths),
        "batch_dir": bdir, "verdict_dir": vdir, "rubric": os.path.join(HERE, "rubric.md"),
        "batches": paths, "counts": counts,
    }))

if __name__ == "__main__":
    main()
