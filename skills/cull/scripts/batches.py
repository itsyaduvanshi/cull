#!/usr/bin/env python3
"""Split the photos and videos that still need labels into batches.

Writes <folder>/.cull/batches/batch-NNN.txt. Each line is:
    <id>\t<path Claude should Read>\t<original relative path>\t<about>
The path is the thumbnail for a photo, the 6-frame contact sheet for a
video. <about> says "photo" or describes the video (duration, size,
orientation, audio, frame times).

Usage:
    python3 batches.py <photo-folder> [--size 25] [--limit 0]
"""
import argparse
import json
import os
import shutil
import sys

STATE_DIR = ".cull"


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


def describe_video(it):
    parts = ["video"]
    d = it.get("duration")
    if d:
        parts.append("%d:%02d long" % (int(d) // 60, int(d) % 60))
    w, h = it.get("w"), it.get("h")
    if w and h:
        orient = "vertical 9:16" if h > w * 1.2 else "horizontal" if w > h * 1.2 else "square"
        parts.append("%dx%d %s" % (w, h, orient))
    if it.get("fps"):
        parts.append("%g fps%s" % (it["fps"], " (slow-motion capable)" if it["fps"] >= 90 else ""))
    parts.append("has audio" if it.get("audio") else "no audio")
    if it.get("frame_times"):
        parts.append("sheet frames at " + ", ".join("%.1fs" % t for t in it["frame_times"]))
    elif it["kind"] == "video":
        parts.append("no frames (ffmpeg missing): judge from the file name only")
    return "; ".join(parts)


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
        if not i.get("dup_of") and i["id"] not in done
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
                if it["kind"] == "video":
                    look = os.path.join(state, it.get("sheet") or it.get("thumb") or "") if (it.get("sheet") or it.get("thumb")) else "-"
                    about = describe_video(it)
                else:
                    look = os.path.join(state, it["thumb"]) if it.get("thumb") else os.path.join(root, it["rel"])
                    about = "photo"
                f.write("%s\t%s\t%s\t%s\n" % (it["id"], look, it["rel"], about))
        paths.append(p)

    nv = sum(1 for i in todo if i["kind"] == "video")
    print("%d files to label (%d photos, %d videos) in %d batches (%d already labelled)" % (len(todo), len(todo) - nv, nv, len(paths), len(done)))
    for p in paths:
        print("BATCH=%s" % p)


if __name__ == "__main__":
    main()
