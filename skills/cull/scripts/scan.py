#!/usr/bin/env python3
"""Cull scanner.

Walks a folder of photos and videos and writes
<folder>/.cull/manifest.json: file size, dimensions, a content hash
(exact duplicates), burst groups, transparency and, when Pillow is
installed, a blur score and a perceptual hash (near duplicates).

For videos (needs ffmpeg/ffprobe): duration, resolution, orientation,
frame rate, audio, a thumbnail and a contact sheet of 6 frames that
Claude reads to understand the clip.

Thumbnails are small, so Claude spends far fewer tokens per file.

Never changes or deletes the user's files. Python 3.8+, standard
library only; Pillow (pip install pillow), ffmpeg and macOS `sips` are
used when present.

Usage:
    python3 scan.py <photo-folder> [--thumb 512] [--no-thumbs]
"""
import argparse
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import time

try:
    from PIL import Image, ImageFilter, ImageStat  # optional

    try:
        import pillow_heif  # optional HEIC support for Pillow

        pillow_heif.register_heif_opener()
    except Exception:
        pass
    HAVE_PIL = True
except Exception:
    HAVE_PIL = False

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".heif", ".bmp", ".tif", ".tiff"}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}
SKIP_DIRS = {".cull", "Culled", ".git", "node_modules", "__MACOSX"}
STATE_DIR = ".cull"
FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
SHEET_FRAMES = 6


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def quick_hash(path, size):
    """Full SHA-256 for small files; for big videos, hash size + 3 slices."""
    if size <= 32 << 20:
        return sha256(path)
    h = hashlib.sha256(str(size).encode())
    with open(path, "rb") as f:
        h.update(f.read(4 << 20))
        f.seek(size // 2)
        h.update(f.read(4 << 20))
        f.seek(-(4 << 20), 2)
        h.update(f.read())
    return "q" + h.hexdigest()


def probe_video(path):
    info = {}
    if not FFPROBE:
        return info
    try:
        out = subprocess.run(
            [FFPROBE, "-v", "error", "-print_format", "json", "-show_streams", "-show_format", path],
            capture_output=True, text=True, timeout=60,
        ).stdout
        d = json.loads(out or "{}")
    except Exception:
        return info
    streams = d.get("streams", [])
    v = next((x for x in streams if x.get("codec_type") == "video"), None)
    info["audio"] = any(x.get("codec_type") == "audio" for x in streams)
    try:
        info["duration"] = round(float(d.get("format", {}).get("duration") or (v or {}).get("duration") or 0), 2)
    except ValueError:
        info["duration"] = 0
    if v:
        w, h = int(v.get("width") or 0), int(v.get("height") or 0)
        rot = 0
        try:
            rot = int((v.get("tags") or {}).get("rotate", 0))
        except ValueError:
            pass
        for sd in v.get("side_data_list") or []:
            if "rotation" in sd:
                try:
                    rot = int(float(sd["rotation"]))
                except ValueError:
                    pass
        if abs(rot) % 180 == 90:
            w, h = h, w
        info["w"], info["h"] = w, h
        try:
            num, den = (v.get("avg_frame_rate") or v.get("r_frame_rate") or "0/1").split("/")
            info["fps"] = round(float(num) / float(den), 2) if float(den) else None
        except Exception:
            info["fps"] = None
        info["codec"] = v.get("codec_name")
    return info


def grab_frame(path, t, dst, box):
    r = subprocess.run(
        [FFMPEG, "-v", "error", "-y", "-ss", "%.3f" % t, "-i", path, "-frames:v", "1",
         "-vf", "scale=%d:%d:force_original_aspect_ratio=decrease" % (box, box), "-q:v", "4", dst],
        capture_output=True, timeout=120,
    )
    return r.returncode == 0 and os.path.exists(dst)


def video_frames(path, it, state):
    """Thumbnail + contact sheet (3x2 frames, left to right, top to bottom)."""
    if not FFMPEG:
        return
    dur = it.get("duration") or 0
    times = [round(dur * (k + 0.5) / SHEET_FRAMES, 2) for k in range(SHEET_FRAMES)] if dur > 0 else [0]
    thumb = os.path.join(state, "thumbs", it["id"] + ".jpg")
    if grab_frame(path, times[len(times) // 2] if dur > 0 else 0, thumb, 512):
        it["thumb"] = "thumbs/" + it["id"] + ".jpg"
    sheets = os.path.join(state, "sheets")
    os.makedirs(sheets, exist_ok=True)
    sheet = os.path.join(sheets, it["id"] + ".jpg")
    if len(times) == 1:
        if it.get("thumb"):
            shutil.copy(thumb, sheet)
            it["sheet"], it["frame_times"] = "sheets/" + it["id"] + ".jpg", times
        return
    if HAVE_PIL:
        tmp = []
        for k, t in enumerate(times):
            f = os.path.join(sheets, "%s_%d.jpg" % (it["id"], k))
            if grab_frame(path, t, f, 360):
                tmp.append(f)
        if tmp:
            frames = [Image.open(f).convert("RGB") for f in tmp]
            fw = max(f.width for f in frames)
            fh = max(f.height for f in frames)
            cols = 3
            rows = (len(frames) + cols - 1) // cols
            canvas = Image.new("RGB", (fw * cols + 4 * (cols - 1), fh * rows + 4 * (rows - 1)), (20, 18, 16))
            for k, fr in enumerate(frames):
                canvas.paste(fr, ((k % cols) * (fw + 4), (k // cols) * (fh + 4)))
            canvas.save(sheet, quality=80)
            for fr in frames:
                fr.close()
            for f in tmp:
                os.remove(f)
    else:
        r = subprocess.run(
            [FFMPEG, "-v", "error", "-y", "-i", path, "-vf",
             "fps=%f,scale=360:360:force_original_aspect_ratio=decrease,tile=3x2" % (SHEET_FRAMES / dur),
             "-frames:v", "1", "-q:v", "4", sheet],
            capture_output=True, timeout=600,
        )
    if os.path.exists(sheet):
        it["sheet"] = "sheets/" + it["id"] + ".jpg"
        it["frame_times"] = times


def png_info(path):
    """Width, height and whether the PNG can be transparent."""
    with open(path, "rb") as f:
        if f.read(8) != b"\x89PNG\r\n\x1a\n":
            return None
        alpha = False
        w = h = 0
        while True:
            head = f.read(8)
            if len(head) < 8:
                break
            length, ctype = struct.unpack(">I4s", head)
            if ctype == b"IHDR":
                data = f.read(length)
                w, h = struct.unpack(">II", data[:8])
                alpha = data[9] in (4, 6)  # grey+alpha, rgba
                f.read(4)
                continue
            if ctype == b"tRNS":
                alpha = True
                break
            if ctype == b"IDAT":
                break
            f.seek(length + 4, 1)
        return w, h, alpha


def jpeg_size(path):
    with open(path, "rb") as f:
        if f.read(2) != b"\xff\xd8":
            return None
        while True:
            b = f.read(1)
            while b and b != b"\xff":
                b = f.read(1)
            while b == b"\xff":
                b = f.read(1)
            if not b:
                return None
            marker = b[0]
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                continue
            seg = f.read(2)
            if len(seg) < 2:
                return None
            length = struct.unpack(">H", seg)[0]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                data = f.read(5)
                h, w = struct.unpack(">HH", data[1:5])
                return w, h
            f.seek(length - 2, 1)


def sips_size(path):
    if not shutil.which("sips"):
        return None
    try:
        out = subprocess.run(
            ["sips", "-g", "pixelWidth", "-g", "pixelHeight", path],
            capture_output=True, text=True, timeout=20,
        ).stdout
        vals = {}
        for line in out.splitlines():
            parts = line.strip().split(":")
            if len(parts) == 2 and parts[0] in ("pixelWidth", "pixelHeight"):
                vals[parts[0]] = int(parts[1])
        if len(vals) == 2:
            return vals["pixelWidth"], vals["pixelHeight"]
    except Exception:
        pass
    return None


def pil_metrics(img):
    """Blur score (higher is sharper), brightness 0-255, 64-bit dHash."""
    grey = img.convert("L")
    small = grey.copy()
    small.thumbnail((512, 512))
    edges = small.filter(ImageFilter.FIND_EDGES)
    blur = ImageStat.Stat(edges).var[0]
    brightness = ImageStat.Stat(small).mean[0]
    d = grey.resize((9, 8))
    px = list(d.getdata())
    bits = 0
    for row in range(8):
        for col in range(8):
            bits = (bits << 1) | (1 if px[row * 9 + col] > px[row * 9 + col + 1] else 0)
    return round(blur, 1), round(brightness, 1), "%016x" % bits


def make_thumb(src, dst, size):
    if HAVE_PIL:
        try:
            with Image.open(src) as im:
                im.thumbnail((size, size))
                if im.mode not in ("RGB", "RGBA"):
                    im = im.convert("RGBA" if "A" in im.getbands() else "RGB")
                if dst.endswith(".jpg") and im.mode == "RGBA":
                    im = im.convert("RGB")
                im.save(dst, quality=82)
            return True
        except Exception:
            pass
    if shutil.which("sips"):
        fmt = "png" if dst.endswith(".png") else "jpeg"
        r = subprocess.run(
            ["sips", "-Z", str(size), "-s", "format", fmt, src, "--out", dst],
            capture_output=True, timeout=60,
        )
        return r.returncode == 0 and os.path.exists(dst)
    return False


def file_id(rel):
    return hashlib.sha1(rel.encode("utf-8")).hexdigest()[:12]


def hamming(a, b):
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder")
    ap.add_argument("--thumb", type=int, default=512, help="thumbnail long edge in px")
    ap.add_argument("--no-thumbs", action="store_true")
    ap.add_argument("--near", type=int, default=5, help="max dHash distance for near duplicates")
    args = ap.parse_args()

    root = os.path.abspath(os.path.expanduser(args.folder))
    if not os.path.isdir(root):
        sys.exit("Not a folder: %s" % root)
    state = os.path.join(root, STATE_DIR)
    thumbs = os.path.join(state, "thumbs")
    os.makedirs(thumbs, exist_ok=True)

    old = {}
    mpath = os.path.join(state, "manifest.json")
    if os.path.exists(mpath):
        try:
            for it in json.load(open(mpath))["items"]:
                old[it["rel"]] = it
        except Exception:
            old = {}

    items = []
    t0 = time.time()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for name in sorted(filenames):
            if name.startswith("."):
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext in IMAGE_EXT:
                kind = "image"
            elif ext in VIDEO_EXT:
                kind = "video"
            else:
                continue
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, root)
            st = os.stat(path)
            prev = old.get(rel)
            if prev and prev.get("size") == st.st_size and prev.get("mtime") == int(st.st_mtime):
                items.append(prev)  # unchanged since last scan
                continue

            it = {
                "id": file_id(rel), "rel": rel, "name": name, "ext": ext, "kind": kind,
                "size": st.st_size, "mtime": int(st.st_mtime),
                "w": None, "h": None, "alpha": False,
                "sha256": quick_hash(path, st.st_size), "thumb": None,
            }
            if kind == "video":
                it.update(probe_video(path))
                video_frames(path, it, state)
                if HAVE_PIL and it.get("thumb"):
                    try:
                        with Image.open(os.path.join(state, it["thumb"])) as im:
                            it["blur"], it["brightness"], it["dhash"] = pil_metrics(im)
                    except Exception:
                        pass
            if kind == "image":
                dims = None
                if ext == ".png":
                    info = png_info(path)
                    if info:
                        dims, it["alpha"] = info[:2], info[2]
                elif ext in (".jpg", ".jpeg"):
                    dims = jpeg_size(path)
                if HAVE_PIL:
                    try:
                        with Image.open(path) as im:
                            dims = dims or im.size
                            it["alpha"] = it["alpha"] or ("A" in im.getbands())
                            it["blur"], it["brightness"], it["dhash"] = pil_metrics(im)
                    except Exception:
                        pass
                if not dims:
                    dims = sips_size(path)
                if dims:
                    it["w"], it["h"] = int(dims[0]), int(dims[1])
                if not args.no_thumbs:
                    tname = it["id"] + (".png" if it["alpha"] else ".jpg")
                    if make_thumb(path, os.path.join(thumbs, tname), args.thumb):
                        it["thumb"] = "thumbs/" + tname
                if HAVE_PIL and "dhash" not in it and it["thumb"]:
                    # e.g. HEIC without pillow-heif: measure the sips thumbnail
                    try:
                        with Image.open(os.path.join(state, it["thumb"])) as im:
                            it["blur"], it["brightness"], it["dhash"] = pil_metrics(im)
                    except Exception:
                        pass
            items.append(it)
            if len(items) % 50 == 0:
                print("  scanned %d files..." % len(items), flush=True)

    # Exact duplicates: same bytes. Keep the oldest copy.
    by_hash = {}
    for it in items:
        it.pop("dup_of", None)
        it.pop("near_of", None)
        it.pop("burst", None)
        by_hash.setdefault(it["sha256"], []).append(it)
    dup_count = dup_bytes = 0
    for group in by_hash.values():
        if len(group) > 1:
            group.sort(key=lambda x: (x["mtime"], x["rel"]))
            for extra in group[1:]:
                extra["dup_of"] = group[0]["id"]
                dup_count += 1
                dup_bytes += extra["size"]

    # Near duplicates (needs Pillow): similar dHash, keep the sharpest.
    near_count = 0
    hashed = [i for i in items if i.get("dhash") and not i.get("dup_of")]
    seen = set()
    for i, a in enumerate(hashed):
        if a["id"] in seen:
            continue
        group = [a]
        for b in hashed[i + 1:]:
            if b["id"] not in seen and b["kind"] == a["kind"] and hamming(a["dhash"], b["dhash"]) <= args.near:
                group.append(b)
        if len(group) > 1:
            group.sort(key=lambda x: -(x.get("blur") or 0))
            for extra in group[1:]:
                extra["near_of"] = group[0]["id"]
                seen.add(extra["id"])
                near_count += 1
            seen.add(group[0]["id"])

    # Bursts: same size photos taken within 3 seconds of each other.
    imgs = sorted((i for i in items if i["kind"] == "image" and not i.get("dup_of")), key=lambda x: (x["mtime"], x["rel"]))
    burst_n = 0
    for prev, cur in zip(imgs, imgs[1:]):
        if cur["mtime"] - prev["mtime"] <= 3 and (cur["w"], cur["h"]) == (prev["w"], prev["h"]):
            if "burst" not in prev:
                burst_n += 1
                prev["burst"] = "b%d" % burst_n
            cur["burst"] = prev["burst"]

    manifest = {
        "version": 1,
        "root": root,
        "scanned_at": int(time.time()),
        "pillow": HAVE_PIL,
        "stats": {
            "files": len(items),
            "images": sum(1 for i in items if i["kind"] == "image"),
            "videos": sum(1 for i in items if i["kind"] == "video"),
            "bytes": sum(i["size"] for i in items),
            "exact_duplicates": dup_count,
            "duplicate_bytes": dup_bytes,
            "near_duplicates": near_count,
        },
        "items": items,
    }
    tmp = mpath + ".tmp"
    with open(tmp, "w") as f:
        json.dump(manifest, f, indent=1)
    os.replace(tmp, mpath)

    labelled = set()
    ldir = os.path.join(state, "labels")
    if os.path.isdir(ldir):
        for fn in os.listdir(ldir):
            if fn.endswith(".jsonl"):
                for line in open(os.path.join(ldir, fn)):
                    try:
                        labelled.add(json.loads(line)["id"])
                    except Exception:
                        pass
    todo = [i for i in items if not i.get("dup_of") and i["id"] not in labelled]

    s = manifest["stats"]
    print("Scanned %s in %.1fs" % (root, time.time() - t0))
    print("  %d files (%d images, %d videos), %.1f MB" % (s["files"], s["images"], s["videos"], s["bytes"] / 1e6))
    print("  %d exact duplicates (%.1f MB), %d near duplicates" % (dup_count, dup_bytes / 1e6, near_count))
    print("  %d files still need labels" % len(todo))
    if not HAVE_PIL:
        print("  tip: pip3 install pillow  (adds blur score and near-duplicate detection)")
    if s["videos"] and not FFMPEG:
        print("  tip: install ffmpeg so Claude can see inside videos (brew install ffmpeg)")
    print("STATE=%s" % state)


if __name__ == "__main__":
    main()
