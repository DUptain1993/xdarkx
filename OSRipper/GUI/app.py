#!/usr/bin/env python3
"""
OSRipper GUI — Web-based interface
Designed to run locally on Termux / proot / Android.
Open http://localhost:7070 in any browser after starting.
"""

import os
import re
import sys
import uuid
import json
import queue
import signal
import threading
import subprocess
from pathlib import Path

# Strip ANSI/VT100 escape sequences from terminal output before sending to browser
_ANSI_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

from flask import (
    Flask, render_template, request, jsonify,
    Response, send_file, abort
)

# ── Paths ──────────────────────────────────────────────────────────────────────
GUI_DIR     = Path(__file__).parent.resolve()
ROOT_DIR    = GUI_DIR.parent.resolve()
RESULTS_DIR = ROOT_DIR / "results"
UPLOAD_DIR  = GUI_DIR / "uploads"

UPLOAD_DIR.mkdir(exist_ok=True)
RESULTS_DIR.mkdir(exist_ok=True)

# ── Flask app ──────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024  # 32 MB upload limit

# ── Job registry ───────────────────────────────────────────────────────────────
# Structure: { job_id: { queue, pid, done, command } }
_jobs: dict = {}
_jobs_lock = threading.Lock()


# File extensions / patterns that osripper generates as raw payloads
_PAYLOAD_SUFFIXES = {".py", ".sh", ".bin", ".exe", ""}  # "" = no extension

# Directories / files to never treat as generated payloads
_SKIP_ROOTS = {
    "src", "tests", "GUI", ".git", "debian", "docs",
    "img", "webroot", "dist", "__pycache__",
}
_SKIP_NAMES = {
    "setup.py", "pyproject.toml", "pytest.ini",
    "requirements.txt", "usage.md",
}


def _collect_loose_payloads(cwd: Path, results_dir: Path, snapshot: set) -> None:
    """
    After a job finishes, move any *new* payload files that landed in the project
    root (cwd) into results/.  This covers the case where no --obfuscate /
    --compile flag was given, so Generator.cleanup_and_move_results() never ran.
    """
    for item in list(cwd.iterdir()):
        if item.is_dir():
            continue
        if item.name in _SKIP_NAMES:
            continue
        if item.suffix not in _PAYLOAD_SUFFIXES:
            continue
        if item.resolve() == results_dir.resolve():
            continue
        # Only move files that did NOT exist before the job started
        if str(item) in snapshot:
            continue
        dest = results_dir / item.name
        try:
            item.rename(dest)
        except Exception:
            pass  # best-effort


def _worker(job_id: str, cmd: list, cwd: Path) -> None:
    """Run *cmd* in a subprocess, push every output line into the job queue."""
    q = _jobs[job_id]["queue"]

    # Snapshot existing files in cwd so we can detect newly created ones
    try:
        before = {str(p) for p in cwd.iterdir() if p.is_file()}
    except Exception:
        before = set()

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=str(cwd),
        )
        with _jobs_lock:
            _jobs[job_id]["pid"] = proc.pid

        for line in proc.stdout:
            clean = _ANSI_RE.sub("", line).rstrip("\n")
            if clean:  # skip blank lines left after stripping escape-only lines
                q.put(clean)

        proc.wait()
        rc = proc.returncode
        q.put(f"__EXIT__{rc}")

        # Move any loose payload files to results/
        if rc == 0:
            _collect_loose_payloads(cwd, RESULTS_DIR, before)

    except FileNotFoundError:
        q.put("[!] 'osripper-cli' not found. Run: pip3 install -e .. from the OSRipper root.")
        q.put("__EXIT__127")
    except Exception as exc:
        q.put(f"[!] Unexpected error: {exc}")
        q.put("__EXIT__1")
    finally:
        with _jobs_lock:
            if job_id in _jobs:
                _jobs[job_id]["done"] = True


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/generate", methods=["POST"])
def generate():
    """Build and launch an osripper-cli command; return a job_id."""
    data  = request.form
    files = request.files
    cmd_type = data.get("command", "").strip()

    if cmd_type not in ("bind", "reverse", "staged", "doh", "custom", "server", "setup"):
        return jsonify({"error": f"Unknown command: {cmd_type}"}), 400

    cmd = ["osripper-cli", cmd_type]

    # ── Command-specific arguments ──────────────────────────────────────────
    if cmd_type == "bind":
        port = data.get("port", "").strip()
        if not port:
            return jsonify({"error": "Port is required"}), 400
        cmd += ["-p", port]

    elif cmd_type in ("reverse", "staged"):
        host = data.get("host", "").strip()
        port = data.get("port", "").strip()
        if not host:
            return jsonify({"error": "Host is required"}), 400
        if not port:
            return jsonify({"error": "Port is required"}), 400
        cmd += ["-H", host, "-p", port]

    elif cmd_type == "doh":
        domain = data.get("domain", "").strip()
        if not domain:
            return jsonify({"error": "Domain is required"}), 400
        cmd += ["-d", domain]

    elif cmd_type == "custom":
        script = files.get("script")
        if not script or not script.filename:
            return jsonify({"error": "A .py script file is required"}), 400
        if not script.filename.endswith(".py"):
            return jsonify({"error": "Script must be a .py file"}), 400
        safe_name  = f"{uuid.uuid4().hex}_{Path(script.filename).name}"
        script_path = UPLOAD_DIR / safe_name
        script.save(str(script_path))
        cmd += ["--script", str(script_path)]

    elif cmd_type == "server":
        domain = data.get("domain", "").strip()
        if not domain:
            return jsonify({"error": "Domain is required"}), 400
        cmd.append(domain)
        port = data.get("port", "5000").strip()
        cmd += ["--port", port]
        if data.get("https") == "true":
            cmd.append("--https")
        if data.get("debug") == "true":
            cmd.append("--debug")

    elif cmd_type == "setup":
        if data.get("system") == "true":
            cmd.append("--system")

    # ── Common payload options (not for server / setup) ─────────────────────
    if cmd_type not in ("server", "setup"):
        output_name = (data.get("output") or "payload").strip() or "payload"
        cmd += ["-o", output_name]
        if data.get("obfuscate")    == "true": cmd.append("--obfuscate")
        if data.get("enhanced")     == "true": cmd.append("--enhanced")
        if data.get("compile")      == "true": cmd.append("--compile")
        if data.get("delay")        == "true": cmd.append("--delay")
        if data.get("no_randomize") == "true": cmd.append("--no-randomize-output")

    # ── Spawn job ────────────────────────────────────────────────────────────
    job_id = uuid.uuid4().hex
    with _jobs_lock:
        _jobs[job_id] = {
            "queue":   queue.Queue(),
            "pid":     None,
            "done":    False,
            "command": " ".join(str(a) for a in cmd),
        }

    thread = threading.Thread(target=_worker, args=(job_id, cmd, ROOT_DIR), daemon=True)
    thread.start()

    return jsonify({"job_id": job_id, "command": _jobs[job_id]["command"]})


@app.route("/api/stream/<job_id>")
def stream(job_id: str):
    """Server-Sent Events: stream live output for a running job."""
    with _jobs_lock:
        if job_id not in _jobs:
            return jsonify({"error": "Job not found"}), 404

    def event_generator():
        q = _jobs[job_id]["queue"]
        while True:
            try:
                line = q.get(timeout=25)
                if line.startswith("__EXIT__"):
                    rc = line[8:]
                    yield f"data: {json.dumps({'type': 'exit', 'code': rc})}\n\n"
                    break
                yield f"data: {json.dumps({'type': 'output', 'text': line})}\n\n"
            except queue.Empty:
                yield f"data: {json.dumps({'type': 'keepalive'})}\n\n"

    return Response(
        event_generator(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/kill/<job_id>", methods=["POST"])
def kill_job(job_id: str):
    """Send SIGTERM to the process associated with a job."""
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    pid = job.get("pid")
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            return jsonify({"ok": True, "pid": pid})
        except ProcessLookupError:
            return jsonify({"ok": True, "note": "Process already finished"})
        except PermissionError as exc:
            return jsonify({"error": str(exc)}), 403
    return jsonify({"error": "Process not yet started"}), 409


@app.route("/api/files")
def list_files():
    """Return a sorted list of files in the results directory."""
    files = []
    if RESULTS_DIR.exists():
        for f in sorted(RESULTS_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if f.is_file():
                stat = f.stat()
                files.append({
                    "name":     f.name,
                    "size":     stat.st_size,
                    "modified": stat.st_mtime,
                })
    return jsonify({"files": files})


@app.route("/api/download/<path:filename>")
def download(filename: str):
    """Download a file from the results directory."""
    filepath = (RESULTS_DIR / filename).resolve()
    # Guard against path traversal
    try:
        filepath.relative_to(RESULTS_DIR.resolve())
    except ValueError:
        abort(403)
    if not filepath.is_file():
        abort(404)
    return send_file(str(filepath), as_attachment=True)


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="OSRipper GUI server")
    parser.add_argument("--host", default="127.0.0.1",
                        help="Bind address (use 0.0.0.0 for LAN access)")
    parser.add_argument("--port", type=int, default=7070,
                        help="HTTP port (default: 7070)")
    args = parser.parse_args()

    url = f"http://{args.host}:{args.port}"
    print(f"\n  ╔══════════════════════════════════╗")
    print(f"  ║   🏴‍☠️  OSRipper GUI  v0.4.2      ║")
    print(f"  ║   Open in browser: {url:<14}║")
    print(f"  ╚══════════════════════════════════╝\n")

    app.run(host=args.host, port=args.port, debug=False, threaded=True)
