#!/usr/bin/env python3
"""Split the photos that still need labels into batches for Claude.

Writes <folder>/.shoebox/batches/batch-NNN.txt. Each line is:
    <id>\t<path Claude should Read>\t<original relative path>
The path is the thumbnail when one exists (cheaper to look at).

Usage:
    python3 batches.py <photo-folder> [--size 25] [--limit 0]
"""
import argparse
import json
import os
import shutil
import sys

STATE_DIR = ".shoebox"


def labelled_ids(state):
    done = set()
    ldir = os.path.join(state, "labels")
    if os.path.isdir(ldir):
        for fn in os.listdir(ldir):
            if not fn.endswith(".jsonl"):
                continue
            with open(os.path.join(ldir, fn)) as f:
                for line in f:
                    try:
                        done.add(json.loads(line)["id"])
                    except Exception:
                        pass
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--size", type=int, default=25, help="photos per batch")
    ap.add_argument("--limit", type=int, default=0, help="only batch the first N photos (0 = all)")
    args = ap.parse_args()

    root = os.path.abspath(os.path.expanduser(args.folder))
    state = os.path.join(root, STATE_DIR)
    mpath = os.path.join(state, "manifest.json")
    if not os.path.exists(mpath):
        sys.exit("No manifest. Run scan.py first.")
    manifest = json.load(open(mpath))
    done = labelled_ids(state)

    todo = [
        i for i in manifest["items"]
        if i["kind"] == "image" and not i.get("dup_of") and i["id"] not in done
    ]
    if args.limit:
        todo = todo[: args.limit]

    bdir = os.path.join(state, "batches")
    shutil.rmtree(bdir, ignore_errors=True)
    os.makedirs(bdir)
    os.makedirs(os.path.join(state, "labels"), exist_ok=True)

    paths = []
    for n, start in enumerate(range(0, len(todo), args.size), 1):
        chunk = todo[start: start + args.size]
        p = os.path.join(bdir, "batch-%03d.txt" % n)
        with open(p, "w") as f:
            for it in chunk:
                look = os.path.join(state, it["thumb"]) if it.get("thumb") else os.path.join(root, it["rel"])
                f.write("%s\t%s\t%s\n" % (it["id"], look, it["rel"]))
        paths.append(p)

    print("%d photos to label in %d batches (%d already labelled)" % (len(todo), len(paths), len(done)))
    for p in paths:
        print("BATCH=%s" % p)


if __name__ == "__main__":
    main()
