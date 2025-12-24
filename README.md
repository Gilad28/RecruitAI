# 🚀 RecruitAI

An AI-powered toolkit for finding tech recruiters and sending personalized outreach emails.

## What It Does

1. **`email_finder/`** - Finds recruiters at target companies via LinkedIn search
2. **`email_outreach/`** - Generates and sends personalized emails using GPT

## Quick Start

### 1. Find Recruiters

```bash
cd email_finder
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Add your You.com API key to .env
echo "YOU_API_KEY=your-key-here" > .env

# Edit companies.csv with target companies, then run:
python email_finder.py -i companies.csv -o emails_found.csv
```

### 2. Send Personalized Emails

```bash
cd email_outreach
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Add your OpenAI key to .env
echo "OPENAI_API_KEY=your-key-here" > .env
echo "YOUR_NAME=Your Name" >> .env
echo "YOUR_EMAIL=your@email.com" >> .env

# Preview emails (no sending)
python outreach.py --resume /path/to/resume.pdf --preview

# Add P.S. about this tool
python outreach.py --resume /path/to/resume.pdf --preview --add-ps

# Send emails (requires Gmail App Password)
python outreach.py --resume /path/to/resume.pdf --send
```

## Features

- 🔍 **LinkedIn Search** - Finds recruiters via You.com API
- 🤖 **GPT Personalization** - Each email is uniquely tailored per company
- 📄 **Resume Parsing** - Extracts skills from PDF/DOCX/TXT
- 📧 **Gmail Integration** - Sends via SMTP with rate limiting
- 📊 **Tracking** - Prevents duplicate sends
- 🎯 **Internship Focus** - Optimized for student job seekers

## API Keys Needed

| Service | Purpose | Get It |
|---------|---------|--------|
| You.com | LinkedIn search | [you.com/api](https://you.com/api) |
| OpenAI | Email generation | [platform.openai.com](https://platform.openai.com) |
| Gmail App Password | Sending emails | [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) |

## Example Output

```
To: amy.salazar@stripe.com
Subject: Exploring Internship Opportunities at Stripe!

Hi Amy,

I admire Stripe's commitment to making online payments accessible...
I'm a CS student at Washington State University seeking an internship...

P.S. I built a tool that finds recruiters via LinkedIn, generates 
personalized emails with GPT, and sends them - that's how I found 
you and wrote this! I reviewed it before sending.
```

## License

MIT

