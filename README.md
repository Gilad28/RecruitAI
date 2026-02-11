# RecruitAI

Find recruiter emails from startups → send personalized outreach.

## Setup

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

**Single `.env` at project root** – copy `.env.example` to `.env` and fill in, or run `python merge_env.py` to merge from subfolders.

| Key | Use |
|-----|-----|
| YOU_API_KEY | Find recruiters (You.com) |
| OPENAI_API_KEY | Email generation |
| YOUR_NAME, YOUR_EMAIL | Sender info |
| GMAIL_APP_PASSWORD | Sending |
| APOLLO_API_KEY | Email verification |
| RESUME_PATH | Optional; default `~/Documents/GiladHeitnerSpring2026.pdf` |

## Usage

### Web UI (recommended)

```bash
python app.py
```

Open http://localhost:5000 to find recruiters, view lists, and send emails.

### CLI

**1. Find recruiters** → writes `recruiters.csv`

```bash
python find_emails.py -q "AI startup internship" -m 50 -o recruiters.csv
```

**2. Send emails** (defaults to `recruiters.csv`)

```bash
python send_emails.py --resume resume.pdf --preview
python send_emails.py --resume resume.pdf --send --limit 20 --yes
```

## Project layout

```
RecruitAI/
├── .env              # Your secrets (single file at root)
├── app.py            # Web UI
├── find_emails.py    # CLI: find recruiters
├── send_emails.py    # CLI: send outreach
├── requirements.txt
├── email_finder/     # Find logic (LinkedIn, domain discovery)
├── email_outreach/   # Send logic (outreach, Apollo verify)
└── templates/        # Web UI
```

## License

MIT
