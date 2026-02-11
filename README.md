# RecruitAI

**Automated startup outreach system:** Find small startups → discover founder/CEO/recruiter contacts → send personalized emails.

## Features

- 🔍 **Smart startup discovery** via Wellfound/AngelList
- 👥 **Targets decision-makers**: Founders, CEOs, and recruiters
- 📧 **Automated email generation** with AI-powered personalization
- 🎯 **No active postings needed** - reaches out to any small company
- 🌐 **Modern web UI** with live progress tracking
- ✅ **Email verification** via Apollo.io
- 📊 **Track sent emails** to avoid duplicates

## Setup

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

**Environment setup:** Copy `.env.example` to `.env` and fill in your API keys:

| Key | Purpose |
|-----|---------|
| YOU_API_KEY | Search for startups and contacts (You.com) |
| OPENAI_API_KEY | Generate personalized email content |
| YOUR_NAME, YOUR_EMAIL | Your sender information |
| GMAIL_APP_PASSWORD | Send emails via Gmail ([setup guide](https://support.google.com/accounts/answer/185833)) |
| APOLLO_API_KEY | Verify email addresses (optional) |
| RESUME_PATH | Path to your resume (optional; defaults to `~/Documents/GiladHeitnerSpring2026.pdf`) |

## Usage

### Web UI (Recommended)

```bash
python app.py
```

**Open http://localhost:5000** for the full interface:

- **Find Emails**: Search for startups (e.g., "AI startup", "fintech startup")
- **Recruiters**: View found contacts with status
- **Already Sent**: Track email history
- **Send Emails**: Trigger automated outreach
- **Live Progress**: Real-time progress bars and logs

### CLI

**Find startup contacts:**

```bash
python find_emails.py -q "AI startup" -m 50 -o recruiters.csv
```

**Preview emails before sending:**

```bash
python send_emails.py --resume resume.pdf --preview
```

**Send automated outreach:**

```bash
python send_emails.py --resume resume.pdf --send --limit 20 --yes
```

## How It Works

1. **Discovery**: Searches Wellfound/AngelList for startups matching your query
2. **Domain lookup**: Finds company websites automatically
3. **Contact search**: Searches LinkedIn for founders, CEOs, and recruiters
4. **Email generation**: Creates personalized outreach emails
5. **Verification**: Validates emails via Apollo.io (optional)
6. **Sending**: Sends via Gmail with tracking

## Project Structure

```
RecruitAI/
├── .env                    # API keys and configuration
├── app.py                  # Flask web UI with live progress
├── find_emails.py          # CLI: discover startups and contacts
├── send_emails.py          # CLI: send personalized outreach
├── requirements.txt        # Python dependencies
├── email_finder/
│   ├── find_startups.py    # Startup discovery logic
│   └── src/
│       ├── linkedin_search.py  # Find founders/CEOs/recruiters
│       ├── search.py           # Domain discovery
│       └── utils.py            # Helper functions
├── email_outreach/
│   ├── outreach.py         # Email generation and sending
│   └── src/
│       └── apollo_verify.py    # Email verification
└── templates/
    └── index.html          # Web UI interface
```

## Example Workflow

```bash
# Start the web UI
python app.py

# Or use CLI:
# 1. Find 50 AI startups
python find_emails.py -q "AI startup" -m 50

# 2. Preview generated emails
python send_emails.py --preview

# 3. Send to 20 contacts
python send_emails.py --send --limit 20 --yes
```

## License

MIT
