#!/usr/bin/env python3
"""Cull dashboard server (local only, standard library).

Serves the dashboard for one scanned photo folder at
http://127.0.0.1:8787 and lets it:
  - read every photo with Claude's labels and your own edits
  - save your edits (folder, role, tags, star) to .cull/overrides.json
  - copy or move photos into "<folder>/Culled/<Folder>/"
  - undo the last move
  - export a CSV shot list

It never deletes a file. Duplicates go to "Culled/_Duplicates".

Usage:
    python3 serve.py <photo-folder> [--port 8787] [--open]
"""
import argparse
import csv
import io
import json
import mimetypes
import os
import shutil
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DASHBOARD = os.path.join(REPO, "dashboard", "index.html")
CONFIG = os.path.join(REPO, "cull.config.json")
STATE_DIR = ".cull"
OUT_DIR = "Culled"
LOCK = threading.Lock()


class Library:
    def __init__(self, root):
        self.root = root
        self.state = os.path.join(root, STATE_DIR)
        self.config = json.load(open(CONFIG))

    def path(self, name):
        return os.path.join(self.state, name)

    def manifest(self):
        return json.load(open(self.path("manifest.json")))

    def labels(self):
        out = {}
        ldir = self.path("labels")
        if os.path.isdir(ldir):
            for fn in sorted(os.listdir(ldir)):
                if not fn.endswith(".jsonl"):
                    continue
                with open(os.path.join(ldir, fn)) as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            rec = json.loads(line)
                            out[rec["id"]] = rec
                        except Exception:
                            pass
        return out

    def overrides(self):
        p = self.path("overrides.json")
        return json.load(open(p)) if os.path.exists(p) else {}

    def save_overrides(self, data):
        p = self.path("overrides.json")
        with open(p + ".tmp", "w") as f:
            json.dump(data, f, indent=1)
        os.replace(p + ".tmp", p)

    def items(self):
        m = self.manifest()
        labels, over = self.labels(), self.overrides()
        folders = self.config["folders"]
        rows = []
        for it in m["items"]:
            row = dict(it)
            lab = labels.get(it["id"], {})
            row["labelled"] = bool(lab)
            row["folder"] = lab.get("folder") if lab.get("folder") in folders else (lab and "Other") or None
            row["role"] = lab.get("role")
            row["tags"] = lab.get("tags", [])
            row["quality"] = lab.get("quality")
            row["caption"] = lab.get("caption", "")
            row["note"] = lab.get("note", "")
            row.update(over.get(it["id"], {}))
            rows.append(row)
        return m, rows

    def by_id(self):
        return {i["id"]: i for i in self.manifest()["items"]}


def safe_name(name):
    keep = "".join(c for c in name if c not in '/\\:*?"<>|').strip().strip(".")
    return keep or "Other"


def unique_dest(dest):
    if not os.path.exists(dest):
        return dest
    base, ext = os.path.splitext(dest)
    n = 2
    while os.path.exists("%s (%d)%s" % (base, n, ext)):
        n += 1
    return "%s (%d)%s" % (base, n, ext)


def make_handler(lib):
    class H(BaseHTTPRequestHandler):
        server_version = "Cull/1"

        def log_message(self, fmt, *a):
            pass

        def _host_ok(self):
            host = (self.headers.get("Host") or "").split(":")[0]
            return host in ("127.0.0.1", "localhost")

        def _send(self, code, body, ctype="application/json", extra=None):
            if isinstance(body, (dict, list)):
                body = json.dumps(body).encode()
            elif isinstance(body, str):
                body = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _file(self, path, ctype=None, cache="private, max-age=3600"):
            if not os.path.isfile(path):
                return self._send(404, {"error": "not found"})
            ctype = ctype or mimetypes.guess_type(path)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(os.path.getsize(path)))
            self.send_header("Cache-Control", cache)
            self.end_headers()
            with open(path, "rb") as f:
                shutil.copyfileobj(f, self.wfile)

        def do_GET(self):
            if not self._host_ok():
                return self._send(403, {"error": "bad host"})
            p = urlparse(self.path).path
            if p in ("/", "/index.html"):
                return self._file(DASHBOARD, "text/html; charset=utf-8", "no-store")
            if p == "/api/data":
                m, rows = lib.items()
                return self._send(200, {
                    "root": lib.root, "name": os.path.basename(lib.root),
                    "stats": m["stats"], "pillow": m.get("pillow"),
                    "folders": lib.config["folders"], "roles": lib.config["roles"],
                    "items": rows,
                    "can_undo": os.path.exists(lib.path("apply-log.json")),
                })
            if p.startswith("/thumb/") or p.startswith("/file/"):
                kind, _, fid = p[1:].partition("/")
                it = lib.by_id().get(fid)
                if not it:
                    return self._send(404, {"error": "unknown id"})
                if kind == "thumb" and it.get("thumb"):
                    return self._file(os.path.join(lib.state, it["thumb"]))
                if it["ext"] in (".heic", ".heif", ".tif", ".tiff") and it.get("thumb"):
                    return self._file(os.path.join(lib.state, it["thumb"]))
                return self._file(os.path.join(lib.root, it["rel"]))
            if p == "/api/export.csv":
                _, rows = lib.items()
                buf = io.StringIO()
                w = csv.writer(buf)
                w.writerow(["file", "folder", "role", "quality", "starred", "tags", "caption", "width", "height", "duplicate"])
                rows.sort(key=lambda r: (r.get("folder") or "~", -(r.get("quality") or 0)))
                for r in rows:
                    w.writerow([
                        r["rel"], r.get("folder") or "", r.get("role") or "", r.get("quality") or "",
                        "yes" if r.get("starred") else "", ", ".join(r.get("tags") or []), r.get("caption") or "",
                        r.get("w") or "", r.get("h") or "", "yes" if r.get("dup_of") else "",
                    ])
                return self._send(200, buf.getvalue(), "text/csv; charset=utf-8",
                                  {"Content-Disposition": 'attachment; filename="shot-list.csv"'})
            return self._send(404, {"error": "not found"})

        def do_POST(self):
            # The custom header blocks cross-site form posts: a browser sends
            # it only after a CORS preflight, which this server never allows.
            if not self._host_ok() or self.headers.get("X-Cull") != "1":
                return self._send(403, {"error": "forbidden"})
            p = urlparse(self.path).path
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
            except Exception:
                return self._send(400, {"error": "bad json"})
            with LOCK:
                if p == "/api/override":
                    return self._send(200, self.override(body))
                if p == "/api/apply":
                    return self._send(200, self.apply(body))
                if p == "/api/undo":
                    return self._send(200, self.undo())
            return self._send(404, {"error": "not found"})

        def override(self, body):
            ids = body.get("ids") or []
            changes = body.get("set") or {}
            allowed = {"folder", "role", "tags", "starred", "quality"}
            known = lib.by_id()
            over = lib.overrides()
            for fid in ids:
                if fid not in known:
                    continue
                cur = over.setdefault(fid, {})
                for k, v in changes.items():
                    if k in allowed:
                        cur[k] = v
            lib.save_overrides(over)
            return {"ok": True, "updated": len(ids)}

        def apply(self, body):
            mode = "move" if body.get("mode") == "move" else "copy"
            skip_rejects = bool(body.get("skip_rejects", True))
            _, rows = lib.items()
            out = os.path.join(lib.root, OUT_DIR)
            log, counts = [], {}
            for r in rows:
                if r.get("dup_of") or (r.get("near_of") and body.get("near_as_dupes")):
                    folder = "_Duplicates"
                elif r.get("role") == "reject":
                    if skip_rejects:
                        continue
                    folder = "_Rejects"
                else:
                    folder = r.get("folder")
                    if not folder:
                        continue
                src = os.path.join(lib.root, r["rel"])
                if not os.path.isfile(src):
                    continue
                dest_dir = os.path.join(out, safe_name(folder))
                os.makedirs(dest_dir, exist_ok=True)
                dest = unique_dest(os.path.join(dest_dir, os.path.basename(r["rel"])))
                if mode == "move":
                    shutil.move(src, dest)
                else:
                    shutil.copy2(src, dest)
                log.append({"from": src, "to": dest})
                counts[folder] = counts.get(folder, 0) + 1
            if mode == "move" and log:
                with open(lib.path("apply-log.json"), "w") as f:
                    json.dump({"at": int(time.time()), "moves": log}, f, indent=1)
            return {"ok": True, "mode": mode, "files": len(log), "folders": counts, "out": out}

        def undo(self):
            p = lib.path("apply-log.json")
            if not os.path.exists(p):
                return {"ok": False, "error": "nothing to undo"}
            moves = json.load(open(p))["moves"]
            back = 0
            for mv in reversed(moves):
                if os.path.exists(mv["to"]) and not os.path.exists(mv["from"]):
                    os.makedirs(os.path.dirname(mv["from"]), exist_ok=True)
                    shutil.move(mv["to"], mv["from"])
                    back += 1
            os.remove(p)
            out = os.path.join(lib.root, OUT_DIR)
            for dirpath, _, _ in sorted(os.walk(out), key=lambda x: -len(x[0])):
                try:
                    os.rmdir(dirpath)  # only removes folders left empty
                except OSError:
                    pass
            return {"ok": True, "restored": back}

    return H


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--open", action="store_true", help="open the browser")
    args = ap.parse_args()

    root = os.path.abspath(os.path.expanduser(args.folder))
    if not os.path.exists(os.path.join(root, STATE_DIR, "manifest.json")):
        sys.exit("No scan found in %s. Run scan.py first." % root)
    lib = Library(root)
    port = args.port or lib.config.get("port", 8787)
    srv = None
    for p in range(port, port + 20):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", p), make_handler(lib))
            port = p
            break
        except OSError:
            continue
    if not srv:
        sys.exit("No free port near %d" % port)
    url = "http://127.0.0.1:%d" % port
    print("Cull dashboard: %s  (Ctrl+C to stop)" % url, flush=True)
    if args.open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
