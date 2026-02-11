#!/usr/bin/env python3
"""
RecruitAI Web UI - Find recruiters, view lists, send emails.
"""
import os
import sys
import csv
import json
import subprocess
import threading
from pathlib import Path

from flask import Flask, render_template, jsonify, request
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

app = Flask(__name__)
app.config["RECRUITERS_CSV"] = ROOT / "recruiters.csv"
app.config["SENT_JSON"] = ROOT / "email_outreach" / "sent_emails.json"
app.config["RESUME_PATH"] = os.environ.get("RESUME_PATH", str(Path.home() / "Documents" / "GiladHeitnerSpring2026.pdf"))

# Background job status
_jobs = {}
_job_counter = 0


def _run_find(query: str, max_count: int, job_id: str):
    import re
    try:
        _jobs[job_id] = {
            "status": "running",
            "output": "",
            "progress": {"queries": 0, "total_queries": 0, "found": 0, "target": max_count},
            "logs": []
        }
        
        proc = subprocess.Popen(
            [sys.executable, str(ROOT / "find_emails.py"),
             "-q", query, "-m", str(max_count), "-o", str(app.config["RECRUITERS_CSV"])],
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        output_lines = []
        for line in proc.stdout:
            output_lines.append(line)
            _jobs[job_id]["logs"] = output_lines[-50:]  # Keep last 50 lines
            
            # Parse progress from logs
            if "Searching [" in line:
                match = re.search(r'\[(\d+)/(\d+)\].*\((\d+)/(\d+)', line)
                if match:
                    _jobs[job_id]["progress"] = {
                        "queries": int(match.group(1)),
                        "total_queries": int(match.group(2)),
                        "found": int(match.group(3)),
                        "target": int(match.group(4))
                    }
            elif "Found startup:" in line:
                _jobs[job_id]["progress"]["found"] = _jobs[job_id]["progress"].get("found", 0) + 1
        
        proc.wait(timeout=600)
        full_output = "".join(output_lines)
        
        _jobs[job_id] = {
            "status": "done" if proc.returncode == 0 else "error",
            "returncode": proc.returncode,
            "output": full_output[-2000:],
            "progress": _jobs[job_id]["progress"],
            "logs": output_lines[-50:]
        }
    except Exception as e:
        _jobs[job_id] = {"status": "error", "error": str(e)}
    except subprocess.TimeoutExpired:
        _jobs[job_id] = {"status": "error", "error": "Timeout"}


def _run_send(limit: int, job_id: str):
    import re
    try:
        resume = app.config["RESUME_PATH"]
        if not os.path.isfile(os.path.expanduser(resume)):
            _jobs[job_id] = {"status": "error", "error": f"Resume not found: {resume}"}
            return
        
        _jobs[job_id] = {
            "status": "running",
            "output": "",
            "progress": {"sent": 0, "total": limit},
            "logs": []
        }
        
        cmd = [
            sys.executable, str(ROOT / "send_emails.py"),
            "--resume", os.path.expanduser(resume),
            "--recruiters", str(app.config["RECRUITERS_CSV"]),
            "--send", "--limit", str(limit), "--yes",
            "--use-template", "--add-ps",
        ]
        
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        output_lines = []
        for line in proc.stdout:
            output_lines.append(line)
            _jobs[job_id]["logs"] = output_lines[-50:]
            
            # Parse progress from logs
            if "Sent email" in line or "✓" in line:
                _jobs[job_id]["progress"]["sent"] = _jobs[job_id]["progress"].get("sent", 0) + 1
            elif match := re.search(r'Sending (\d+)/(\d+)', line):
                _jobs[job_id]["progress"]["sent"] = int(match.group(1))
                _jobs[job_id]["progress"]["total"] = int(match.group(2))
        
        proc.wait(timeout=3600)
        full_output = "".join(output_lines)
        
        _jobs[job_id] = {
            "status": "done" if proc.returncode == 0 else "error",
            "returncode": proc.returncode,
            "output": full_output[-3000:],
            "progress": _jobs[job_id]["progress"],
            "logs": output_lines[-50:]
        }
    except Exception as e:
        _jobs[job_id] = {"status": "error", "error": str(e)}
    except subprocess.TimeoutExpired:
        _jobs[job_id] = {"status": "error", "error": "Timeout"}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/recruiters")
def api_recruiters():
    csv_path = app.config["RECRUITERS_CSV"]
    if not csv_path.exists():
        return jsonify({"recruiters": [], "total": 0})
    try:
        with open(csv_path, "r") as f:
            rows = list(csv.DictReader(f))
        sent = _load_sent()
        sent_emails = {e.get("email", "").lower() for e in sent.get("sent", [])}
        sent_companies = {e.get("company", "").strip() for e in sent.get("sent", []) if e.get("company")}
        for r in rows:
            email = (r.get("best_email") or "").strip().lower()
            company = (r.get("company_name") or "").strip()
            r["already_sent"] = email in sent_emails or company in sent_companies
        return jsonify({"recruiters": rows, "total": len(rows)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _load_sent():
    path = app.config["SENT_JSON"]
    if not path.exists():
        return {"sent": []}
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {"sent": []}


@app.route("/api/sent")
def api_sent():
    data = _load_sent()
    sent = data.get("sent", [])
    return jsonify({"sent": sent, "total": len(sent)})


@app.route("/api/find", methods=["POST"])
def api_find():
    global _job_counter
    data = request.get_json() or {}
    query = data.get("query", "AI startup internship")
    max_count = min(int(data.get("max", 50)), 200)
    _job_counter += 1
    job_id = str(_job_counter)
    t = threading.Thread(target=_run_find, args=(query, max_count, job_id))
    t.daemon = True
    t.start()
    return jsonify({"job_id": job_id})


@app.route("/api/find/status/<job_id>")
def api_find_status(job_id):
    if job_id not in _jobs:
        return jsonify({"status": "unknown"})
    return jsonify(_jobs[job_id])


@app.route("/api/send", methods=["POST"])
def api_send():
    global _job_counter
    data = request.get_json() or {}
    limit = min(int(data.get("limit", 20)), 50)
    _job_counter += 1
    job_id = str(_job_counter)
    t = threading.Thread(target=_run_send, args=(limit, job_id))
    t.daemon = True
    t.start()
    return jsonify({"job_id": job_id})


@app.route("/api/send/status/<job_id>")
def api_send_status(job_id):
    if job_id not in _jobs:
        return jsonify({"status": "unknown"})
    return jsonify(_jobs[job_id])


if __name__ == "__main__":
    # debug=False: reloader restarts when find_emails writes recruiters.csv, breaking requests
    app.run(debug=False, port=5000)
