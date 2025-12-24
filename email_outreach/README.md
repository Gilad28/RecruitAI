# 📧 Email Outreach

Sends personalized cold emails to recruiters using GPT.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Configuration

Create `.env`:
```bash
YOUR_NAME=Gilad Heitner
YOUR_EMAIL=heitnergilad@gmail.com
OPENAI_API_KEY=sk-...

# For sending (optional)
GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
```

## Usage

```bash
# Preview emails (safe, no sending)
python outreach.py --resume ~/Documents/resume.pdf --preview

# Preview with P.S. about this tool
python outreach.py --resume ~/Documents/resume.pdf --preview --add-ps

# Preview specific companies
python outreach.py --resume ~/Documents/resume.pdf --preview -c Stripe -c Notion

# Use template instead of GPT (no API key needed)
python outreach.py --resume ~/Documents/resume.pdf --preview --use-template

# Send emails (requires GMAIL_APP_PASSWORD)
python outreach.py --resume ~/Documents/resume.pdf --send --add-ps
```

## Options

| Flag | Description |
|------|-------------|
| `--resume`, `-r` | Path to resume (PDF, DOCX, TXT) |
| `--preview` | Preview without sending |
| `--send` | Send emails |
| `--add-ps` | Add P.S. about this tool with GitHub link |
| `--use-template` | Use template instead of GPT |
| `--limit`, `-n` | Max emails to send |
| `--company`, `-c` | Filter to specific companies |
| `--delay` | Seconds between emails (default: 30) |

## Gmail App Password

1. Enable 2FA on your Google account
2. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. Create app password for "Mail"
4. Add to `.env` as `GMAIL_APP_PASSWORD`
