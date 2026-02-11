#!/usr/bin/env python3
"""
Send personalized emails to recruiters (uses resume + recruiters CSV).
Default recruiters file: recruiters.csv (output of find_emails.py).
"""
import sys
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT / "email_outreach")
sys.path.insert(0, str(ROOT / "email_outreach"))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

# Defaults from env if not provided
argv = list(sys.argv[1:])
if not any(x in argv for x in ("--recruiters", "-i")):
    argv = ["--recruiters", str(ROOT / "recruiters.csv")] + argv

# Default resume: env var or ~/Documents/GiladHeitnerSpring2026.pdf
resume_path = os.environ.get("RESUME_PATH")
if resume_path:
    resume_path = os.path.expanduser(resume_path)
if not resume_path or not os.path.isfile(resume_path):
    default_resume = os.path.expanduser("~/Documents/GiladHeitnerSpring2026.pdf")
    if os.path.isfile(default_resume):
        resume_path = default_resume
if not any(x in argv for x in ("--resume", "-r")) and resume_path and os.path.isfile(resume_path):
    argv = ["--resume", resume_path] + argv
sys.argv = [sys.argv[0]] + argv

if __name__ == "__main__":
    from outreach import main
    main()
