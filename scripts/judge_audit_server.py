"""Local server for the human judge-audit web page.

Serves the audit UI at http://127.0.0.1:8765 and persists every judgment
immediately to results/judge_audit_human.json (keyed by file|question_id|mode).
No external network access; data never leaves the machine.
"""

import csv
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "results" / "judge_audit_sample_100.csv"
SAVE = ROOT / "results" / "judge_audit_human.json"
PAGE = Path(__file__).resolve().parent / "judge_audit.html"
PORT = 8765


def load_rows():
    with SAMPLE.open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    saved = {}
    if SAVE.exists():
        try:
            saved = json.loads(SAVE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            saved = {}
    for i, r in enumerate(rows):
        key = f"{r['file']}|{r['question_id']}|{r['mode']}"
        r["key"] = key
        r["idx"] = i
        s = saved.get(key) or {}
        r["human_verdict"] = s.get("verdict", "")
        r["notes"] = s.get("notes", "")
    return rows


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep the console quiet
        pass

    def _send(self, code, body, ctype):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, PAGE.read_text(encoding="utf-8"), "text/html")
        elif self.path == "/data":
            self._send(200, json.dumps(load_rows(), ensure_ascii=False),
                       "application/json")
        else:
            self._send(404, "not found", "text/plain")

    def do_POST(self):
        if self.path == "/save":
            n = int(self.headers.get("Content-Length", 0))
            try:
                payload = json.loads(self.rfile.read(n).decode("utf-8"))
                assert isinstance(payload, dict)
            except Exception:  # noqa: BLE001
                self._send(400, '{"ok": false}', "application/json")
                return
            tmp = SAVE.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                           encoding="utf-8")
            tmp.replace(SAVE)
            self._send(200, '{"ok": true}', "application/json")
        else:
            self._send(404, "not found", "text/plain")


if __name__ == "__main__":
    print(f"judge-audit server on http://127.0.0.1:{PORT}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
