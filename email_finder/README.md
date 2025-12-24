# 🔍 Email Finder

Finds recruiter emails at target companies via LinkedIn search.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Configuration

Create `.env`:
```bash
YOU_API_KEY=your-you-dot-com-api-key
```

Get your API key at [you.com/api](https://you.com/api)

## Usage

```bash
# Edit companies.csv with your target companies
# Then run:
python email_finder.py -i companies.csv -o emails_found.csv

# Limit pages crawled per company
python email_finder.py -i companies.csv -o emails_found.csv --max-pages-per-company 5

# Verbose output
python email_finder.py -i companies.csv -o emails_found.csv -v
```

## Input Format

`companies.csv`:
```csv
company_name,company_domain
Stripe,stripe.com
Notion,notion.so
Cloudflare,cloudflare.com
```

## Output

- `emails_found.csv` - Best recruiter email per company
- `emails.db` - SQLite database with all data

## How It Works

1. Searches LinkedIn via You.com API for "{company} recruiter"
2. Extracts recruiter names from search results
3. Generates likely email patterns (first.last@domain.com, etc.)
4. Optionally crawls company website for additional emails
5. Scores and ranks results
