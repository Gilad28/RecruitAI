#!/usr/bin/env python3
"""
Recruiter Outreach - Personalized Email Sender

Sends tailored emails to recruiters using your resume and company context.

Usage:
    python outreach.py --resume resume.pdf --recruiters emails_found.csv --preview
    python outreach.py --resume resume.pdf --recruiters emails_found.csv --send
"""

import os
import sys
import csv
import json
import smtplib
import ssl
import socket
import dns.resolver
import logging
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
from typing import Optional, List, Dict, Tuple
import time

from dotenv import load_dotenv
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn

# Load from project root (send_emails.py sets cwd)
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

console = Console()

# ============================================================================
# Company/Internship Details
# ============================================================================

# Details about internship companies - update these with actual information
INTERNSHIP_DETAILS = {
    'worknet': {
        'name': 'Worknet.ai',
        'website': 'https://worknet.ai',
        'description': 'AI-powered recruitment platform',
        'funding': '$X million',  # Update with actual funding amount
        'work': 'Built production GenAI chatbots and AI agents'  # Update with specific work done
    },
    'lettuce': {
        'name': 'Lettuce',
        'website': 'https://lettuce.com',  # Update with actual website
        'description': 'AI company',  # Update with actual description
        'funding': '$X million',  # Update with actual funding amount
        'work': 'Developed AI applications using LangChain and OpenAI APIs'  # Update with specific work done
    }
}

# ============================================================================
# Resume Parsing
# ============================================================================

def parse_resume(resume_path: str) -> str:
    """Extract text from resume (PDF, DOCX, or TXT)."""
    path = Path(resume_path)
    
    if not path.exists():
        raise FileNotFoundError(f"Resume not found: {resume_path}")
    
    suffix = path.suffix.lower()
    
    if suffix == '.pdf':
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(resume_path)
            text = ""
            for page in reader.pages:
                text += page.extract_text() + "\n"
            return text.strip()
        except ImportError:
            raise ImportError("PyPDF2 required for PDF parsing. Run: pip install PyPDF2")
    
    elif suffix == '.docx':
        try:
            from docx import Document
            doc = Document(resume_path)
            text = "\n".join([para.text for para in doc.paragraphs])
            return text.strip()
        except ImportError:
            raise ImportError("python-docx required for DOCX parsing. Run: pip install python-docx")
    
    elif suffix in ['.txt', '.md']:
        return path.read_text().strip()
    
    else:
        raise ValueError(f"Unsupported resume format: {suffix}. Use PDF, DOCX, or TXT.")


# ============================================================================
# Email Generation with LLM
# ============================================================================

def generate_email_with_llm(
    recruiter_name: str,
    company_name: str,
    recruiter_email: str,
    resume_text: str,
    your_name: str,
    your_email: str,
    custom_intro: Optional[str] = None,
) -> Dict[str, str]:
    """Generate personalized email using OpenAI or Anthropic API."""
    
    # Build internship details text
    worknet = INTERNSHIP_DETAILS['worknet']
    lettuce = INTERNSHIP_DETAILS['lettuce']
    internship_details = f"""
INTERNSHIP EXPERIENCE:
1. {worknet['name']} ({worknet['website']}) - {worknet['description']}, raised {worknet['funding']}. {worknet['work']}.
2. {lettuce['name']} ({lettuce['website']}) - {lettuce['description']}, raised {lettuce['funding']}. {lettuce['work']}.
"""

    prompt = f"""You are helping a computer science student write a personalized cold outreach email to a recruiter to land an INTERNSHIP.

RECRUITER INFO:
- Name: {recruiter_name}
- Company: {company_name}
- Email: {recruiter_email}

STUDENT INFO:
- Name: {your_name}
- Email: {your_email}
- Currently pursuing B.S. in Computer Science at Washington State University
- Just completed Junior year
- LinkedIn: [Include LinkedIn profile URL]
- Resume: [Attach resume]

{internship_details}

STUDENT'S RESUME:
{resume_text[:4000]}

{f"CUSTOM INTRO/CONTEXT: {custom_intro}" if custom_intro else ""}

MAIN ASSETS TO HIGHLIGHT:
1. References - Two internships at {worknet['name']} and {lettuce['name']} (see details above)
2. Practical GenAI experience - Built production AI applications, chatbots, and agents
3. Resourcefulness and attitude - Proactive, self-directed, eager to learn and contribute

Write a professional but warm cold outreach email that:
1. Has a compelling subject line that mentions the company and internship interest
2. Opens with a brief, genuine hook about the company (something specific about their product/mission)
3. Clearly states they are a CS student who just completed Junior year, actively seeking an INTERNSHIP opportunity
4. Highlights the three main assets: (a) References from two internships, (b) Practical GenAI experience building production systems, (c) Resourcefulness and positive attitude
5. Mentions the internships with brief context about what those companies do and funding raised (keep it concise)
6. Includes links to resume and LinkedIn profile
7. Shows enthusiasm for learning and contributing at {company_name}
8. Ends with a soft call-to-action (asking about internship opportunities or a brief chat)
9. Is concise (under 200 words for the body)
10. Sounds genuine, eager, and student-appropriate - not overly formal

IMPORTANT: Include hyperlinks to {worknet['website']} and {lettuce['website']} when mentioning those companies.

Return your response as JSON with these exact keys:
{{
    "subject": "The email subject line",
    "body": "The email body (plain text, with proper line breaks and hyperlinks)"
}}

Only return the JSON, nothing else."""

    # Try OpenAI first
    openai_key = os.environ.get('OPENAI_API_KEY')
    anthropic_key = os.environ.get('ANTHROPIC_API_KEY')
    
    if openai_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=openai_key)
            
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024,
            )
            response_text = response.choices[0].message.content.strip()
        except ImportError:
            raise ImportError("openai package required. Run: pip install openai")
    
    elif anthropic_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=anthropic_key)
            
            message = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}]
            )
            response_text = message.content[0].text.strip()
        except ImportError:
            raise ImportError("anthropic package required. Run: pip install anthropic")
    
    else:
        raise ValueError("No API key found. Set OPENAI_API_KEY or ANTHROPIC_API_KEY in .env")
    
    # Parse JSON response
    try:
        # Handle potential markdown code blocks
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        result = json.loads(response_text)
        return result
    except json.JSONDecodeError:
        # Fallback: try to extract subject and body manually
        return {
            "subject": f"Excited about opportunities at {company_name}",
            "body": response_text
        }


def generate_email_template(
    recruiter_name: str,
    company_name: str,
    resume_text: str,
    your_name: str,
) -> Dict[str, str]:
    """Generate email using a template (no LLM required)."""
    
    resume_lower = resume_text.lower()
    
    # Detect key skills from resume
    skill_keywords = {
        'python': 'Python',
        'langchain': 'LangChain',
        'openai': 'OpenAI APIs',
        'genai': 'GenAI',
        'llm': 'LLMs',
        'rag': 'RAG',
        'javascript': 'JavaScript',
        'typescript': 'TypeScript',
        'react': 'React',
        'aws': 'AWS',
        'docker': 'Docker',
        'sql': 'SQL',
        'pinecone': 'Pinecone',
        'machine learning': 'Machine Learning',
    }
    
    found_skills = []
    for keyword, display_name in skill_keywords.items():
        if keyword in resume_lower:
            found_skills.append(display_name)
    
    # Prioritize AI skills
    ai_skills = ['LangChain', 'OpenAI APIs', 'GenAI', 'LLMs', 'RAG', 'Pinecone']
    priority_skills = [s for s in found_skills if s in ai_skills]
    other_skills = [s for s in found_skills if s not in ai_skills]
    ordered_skills = priority_skills[:3] + other_skills[:2]
    
    skills_text = ", ".join(ordered_skills[:4]) if ordered_skills else "software development and AI"
    
    # Determine focus area
    if any(s in found_skills for s in ai_skills):
        focus = "AI/ML engineering and building production GenAI applications"
    else:
        focus = "full-stack development"
    
    # Get internship details
    worknet = INTERNSHIP_DETAILS['worknet']
    lettuce = INTERNSHIP_DETAILS['lettuce']
    
    subject = f"CS Student Seeking AI/Software Internship at {company_name}"
    
    # Get LinkedIn URL from environment
    linkedin_url = os.getenv('LINKEDIN_URL', '')
    linkedin_text = f"\n\nYou can find me on LinkedIn: {linkedin_url}" if linkedin_url else ""
    
    body = f"""Hi {recruiter_name.split()[0] if recruiter_name else 'there'},

I came across your profile and noticed you're part of the talent team at {company_name}. I'm a Computer Science student at Washington State University who just completed my Junior year, and I'm actively seeking an internship. I'm genuinely excited about what you're building.

I've completed two AI internships that I'm really proud of:
- {worknet['name']} ({worknet['website']}) - {worknet['description']}, raised {worknet['funding']}. {worknet['work']}.
- {lettuce['name']} ({lettuce['website']}) - {lettuce['description']}, raised {lettuce['funding']}. {lettuce['work']}.

These experiences gave me hands-on GenAI experience building production systems using {skills_text}, and I'd love to bring that practical knowledge and resourceful attitude to {company_name}.

I've attached my resume.{linkedin_text}

Are there any internship opportunities I should apply for, or would you be open to a quick chat?

Thanks so much,
{your_name}"""

    return {"subject": subject, "body": body}


# ============================================================================
# Email Pattern Generation
# ============================================================================

def generate_email_patterns(first_name: str, last_name: str, domain: str) -> List[str]:
    """
    Generate comprehensive email pattern variations to try.
    Includes all combinations of first name, last name, initials, and separators.
    Given "Gilad Heitner" and "stripe.com", generates patterns like:
    - gilad.heitner@, heitner.gilad@, giladheitner@, heitnergilad@
    - g.heitner@, h.gilad@, gheitner@, hgilad@
    - And many more variations...
    """
    first = first_name.lower().strip()
    last = last_name.lower().strip()
    
    if not first or not last:
        return []
    
    f = first[0] if first else ''
    l = last[0] if last else ''
    
    patterns = [
        # First.Last variations
        f"{first}.{last}@{domain}",           # gilad.heitner@
        f"{first}_{last}@{domain}",           # gilad_heitner@
        f"{first}-{last}@{domain}",           # gilad-heitner@
        f"{first}{last}@{domain}",            # giladheitner@
        
        # Last.First variations (reversed)
        f"{last}.{first}@{domain}",          # heitner.gilad@
        f"{last}_{first}@{domain}",           # heitner_gilad@
        f"{last}-{first}@{domain}",          # heitner-gilad@
        f"{last}{first}@{domain}",            # heitnergilad@
        
        # Initial + Last variations
        f"{f}{last}@{domain}",               # gheitner@
        f"{f}.{last}@{domain}",              # g.heitner@
        f"{f}_{last}@{domain}",              # g_heitner@
        f"{f}-{last}@{domain}",              # g-heitner@
        
        # Last + Initial variations
        f"{last}{f}@{domain}",               # heitnerg@
        f"{last}.{f}@{domain}",              # heitner.g@
        f"{last}_{f}@{domain}",              # heitner_g@
        f"{last}-{f}@{domain}",              # heitner-g@
        
        # First + Last Initial variations
        f"{first}{l}@{domain}",              # giladh@
        f"{first}.{l}@{domain}",             # gilad.h@
        f"{first}_{l}@{domain}",             # gilad_h@
        f"{first}-{l}@{domain}",             # gilad-h@
        
        # Last Initial + First variations
        f"{l}{first}@{domain}",              # hgilad@
        f"{l}.{first}@{domain}",             # h.gilad@
        f"{l}_{first}@{domain}",             # h_gilad@
        f"{l}-{first}@{domain}",             # h-gilad@
        
        # Initial.Initial variations
        f"{f}{l}@{domain}",                  # gh@
        f"{f}.{l}@{domain}",                 # g.h@
        f"{f}_{l}@{domain}",                 # g_h@
        f"{f}-{l}@{domain}",                 # g-h@
        f"{l}{f}@{domain}",                  # hg@
        f"{l}.{f}@{domain}",                 # h.g@
        
        # First name only
        f"{first}@{domain}",                 # gilad@
        
        # Last name only
        f"{last}@{domain}",                  # heitner@
        
        # First.Last with numbers (common for duplicates)
        f"{first}.{last}1@{domain}",         # gilad.heitner1@
        f"{first}{last}1@{domain}",          # giladheitner1@
        f"{first}.{last}2@{domain}",         # gilad.heitner2@
    ]
    
    # Remove duplicates while preserving order
    seen = set()
    unique_patterns = []
    for p in patterns:
        if p not in seen and '@' in p:  # Ensure valid email format
            seen.add(p)
            unique_patterns.append(p)
    
    return unique_patterns


def extract_name_parts(recruiter_name: str) -> Tuple[str, str]:
    """Extract first and last name from a full name."""
    parts = recruiter_name.strip().split()
    if len(parts) >= 2:
        return parts[0], parts[-1]  # First and last
    elif len(parts) == 1:
        return parts[0], ""
    return "", ""


# ============================================================================
# Email Verification
# ============================================================================

# Import Apollo verifier
try:
    from src.apollo_verify import ApolloVerifier
    APOLLO_AVAILABLE = True
except ImportError:
    APOLLO_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("Apollo.io verification not available")

def verify_email(email: str, timeout: int = 10, person_name: Optional[str] = None, company_name: Optional[str] = None) -> Tuple[bool, str]:
    """
    Verify if an email address is valid by checking:
    1. Apollo.io API (if available) - verify person exists (skipped for generic emails like recruiting@)
    2. MX records exist for the domain
    3. SMTP server accepts the recipient (RCPT TO)
    
    Returns: (is_valid, reason)
    """
    apollo_valid = None
    apollo_reason = None
    
    # Generic role emails (recruiting@, careers@, etc.) - skip Apollo, only use SMTP
    local = email.split('@')[0].lower() if '@' in email else ''
    is_generic = local in ('recruiting', 'careers', 'hr', 'talent', 'jobs', 'hiring', 'people')
    
    # Step 0: Try Apollo.io verification (skip for generic emails - Apollo looks for people, not roles)
    if APOLLO_AVAILABLE and not is_generic:
        try:
            apollo = ApolloVerifier()
            is_valid, reason = apollo.verify_email(email, person_name, company_name)
            apollo_valid = is_valid
            apollo_reason = reason
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.debug(f"Apollo.io verification failed: {e}")
    
    try:
        domain = email.split('@')[1]
    except IndexError:
        return False, "Invalid email format"
    
    # Step 1: Check MX records
    try:
        mx_records = dns.resolver.resolve(domain, 'MX')
        mx_host = str(mx_records[0].exchange).rstrip('.')
    except dns.resolver.NXDOMAIN:
        return False, f"Domain {domain} does not exist"
    except dns.resolver.NoAnswer:
        return False, f"No MX records for {domain}"
    except dns.resolver.NoNameservers:
        return False, f"No nameservers for {domain}"
    except Exception as e:
        return False, f"DNS error: {e}"
    
    # Step 2: Try SMTP verification
    smtp_success = False
    smtp_code = None
    smtp_message = None
    smtp_error = None
    
    try:
        # Connect to mail server
        smtp = smtplib.SMTP(timeout=timeout)
        smtp.connect(mx_host, 25)
        smtp.helo('gmail.com')
        smtp.mail('verify@gmail.com')
        
        # Check if recipient exists
        code, message = smtp.rcpt(email)
        smtp.quit()
        
        smtp_code = code
        smtp_message = message
        
        if code == 250:
            smtp_success = True
        elif code == 550:
            # Explicit rejection - mailbox does not exist
            return False, "Mailbox does not exist (SMTP 550)"
        elif code == 553:
            # Invalid mailbox
            return False, "Invalid mailbox (SMTP 553)"
            
    except smtplib.SMTPServerDisconnected:
        smtp_error = "Server disconnected"
    except smtplib.SMTPConnectError:
        smtp_error = "Cannot connect to verify"
    except socket.timeout:
        smtp_error = "Timeout"
    except Exception as e:
        smtp_error = f"SMTP error: {e}"
    
    # Decision logic: be strict - require positive confirmation
    if smtp_success:
        # SMTP explicitly accepted (code 250)
        result_reason = "Valid (SMTP 250)"
        if apollo_reason:
            result_reason += f" | Apollo: {apollo_reason}"
        return True, result_reason
    
    # SMTP was inconclusive or failed
    if apollo_valid is True:
        # Apollo says valid, SMTP inconclusive - trust Apollo
        result_reason = f"Valid (Apollo verified, SMTP inconclusive"
        if smtp_error:
            result_reason += f": {smtp_error}"
        elif smtp_code:
            result_reason += f", code {smtp_code}"
        result_reason += ")"
        return True, result_reason
    
    if apollo_valid is False:
        # Apollo says invalid - reject even if SMTP is inconclusive
        result_reason = f"Invalid (Apollo: {apollo_reason}"
        if smtp_error:
            result_reason += f", SMTP: {smtp_error}"
        elif smtp_code:
            result_reason += f", SMTP code {smtp_code}"
        result_reason += ")"
        return False, result_reason
    
    # No Apollo result, SMTP inconclusive
    # For generic emails (recruiting@, careers@, etc.), accept if no explicit rejection (550/553)
    if is_generic and smtp_code not in (550, 553):
        return True, f"Generic email accepted (MX ok, SMTP: {smtp_code or smtp_error or 'inconclusive'})"
    result_reason = "Inconclusive verification"
    if smtp_error:
        result_reason += f" (SMTP: {smtp_error})"
    elif smtp_code:
        result_reason += f" (SMTP code {smtp_code}, not 250)"
    else:
        result_reason += " (SMTP check failed)"
    return False, result_reason


def batch_verify_emails(emails: List[str], console) -> Dict[str, Tuple[bool, str]]:
    """Verify multiple emails and return results."""
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
    
    results = {}
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console
    ) as progress:
        task = progress.add_task("Verifying emails...", total=len(emails))
        
        for email in emails:
            progress.update(task, description=f"Verifying {email}...")
            is_valid, reason = verify_email(email)
            results[email] = (is_valid, reason)
            progress.advance(task)
    
    return results


def find_valid_email_pattern(
    recruiter_name: str, 
    original_email: str, 
    console,
    max_patterns: int = 50,  # Increased to try more patterns
    company_name: Optional[str] = None
) -> Tuple[Optional[str], str]:
    """
    Try multiple email patterns and return the first valid one.
    
    Returns: (valid_email or None, status_message)
    """
    # Extract domain from original email
    try:
        domain = original_email.split('@')[1]
    except IndexError:
        return None, "Invalid email format"
    
    # First check if original email works
    is_valid, reason = verify_email(original_email, timeout=5, person_name=recruiter_name, company_name=company_name)
    if is_valid:
        return original_email, f"Original valid: {reason}"
    
    # Extract name parts
    first_name, last_name = extract_name_parts(recruiter_name)
    if not first_name or not last_name:
        # Try to extract from email local part
        local_part = original_email.split('@')[0]
        parts = local_part.replace('.', ' ').replace('_', ' ').replace('-', ' ').split()
        if len(parts) >= 2:
            first_name, last_name = parts[0], parts[-1]
        else:
            return None, "Cannot extract name for pattern generation"
    
    # Generate patterns
    patterns = generate_email_patterns(first_name, last_name, domain)
    
    # Remove the original email from patterns (we already checked it)
    patterns = [p for p in patterns if p.lower() != original_email.lower()][:max_patterns]
    
    console.print(f"      [dim]Trying {len(patterns)} patterns for {first_name} {last_name}...[/dim]")
    
    # Try each pattern
    for pattern in patterns:
        is_valid, reason = verify_email(pattern, timeout=5, person_name=recruiter_name, company_name=company_name)
        if is_valid:
            return pattern, f"Pattern found: {pattern} ({reason})"
    
    return None, f"No valid pattern found (tried {len(patterns) + 1} variations)"


def batch_find_valid_emails(
    recruiters: List[Dict], 
    console
) -> Dict[str, Dict]:
    """
    For each recruiter, find a valid email pattern.
    
    Returns dict mapping original email -> {
        'valid_email': str or None,
        'recruiter_name': str,
        'status': str
    }
    """
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
    
    results = {}
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console
    ) as progress:
        task = progress.add_task("Finding valid emails...", total=len(recruiters))
        
        for rec in recruiters:
            original_email = rec.get('best_email', '')
            company = rec.get('company_name', '')
            
            # Get recruiter name
            context = rec.get('best_context', '')
            recruiter_name = ""
            if "LinkedIn recruiter:" in context:
                recruiter_name = context.split("LinkedIn recruiter:")[1].split("-")[0].strip()
            if not recruiter_name:
                local_part = original_email.split('@')[0]
                recruiter_name = local_part.replace('.', ' ').replace('_', ' ').title()
            
            progress.update(task, description=f"Checking {company}: {recruiter_name}...")
            
            valid_email, status = find_valid_email_pattern(
                recruiter_name, 
                original_email, 
                console,
                company_name=company
            )
            
            results[original_email] = {
                'valid_email': valid_email,
                'recruiter_name': recruiter_name,
                'company': company,
                'status': status
            }
            
            progress.advance(task)
    
    return results


# ============================================================================
# Email Sending
# ============================================================================

def send_email_smtp(
    to_email: str,
    subject: str,
    body: str,
    from_email: str,
    from_name: str,
    resume_path: Optional[str] = None,
    smtp_server: str = "smtp.gmail.com",
    smtp_port: int = 587,
    smtp_password: Optional[str] = None,
) -> bool:
    """Send email via SMTP with optional resume attachment."""
    
    password = smtp_password or os.environ.get('SMTP_PASSWORD') or os.environ.get('GMAIL_APP_PASSWORD')
    if not password:
        raise ValueError("SMTP_PASSWORD or GMAIL_APP_PASSWORD not set in environment")
    
    # Create message
    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{from_email}>"
    msg["To"] = to_email
    
    # Add plain text body
    msg.attach(MIMEText(body, "plain"))
    
    # Attach resume if provided
    if resume_path and Path(resume_path).exists():
        try:
            with open(resume_path, "rb") as attachment:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(attachment.read())
            
            encoders.encode_base64(part)
            resume_filename = Path(resume_path).name
            part.add_header(
                'Content-Disposition',
                f'attachment; filename= {resume_filename}',
            )
            msg.attach(part)
        except Exception as e:
            console.print(f"[yellow]Warning: Could not attach resume: {e}[/yellow]")
    
    # Send
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls(context=context)
            server.login(from_email, password)
            server.sendmail(from_email, to_email, msg.as_string())
        return True
    except Exception as e:
        console.print(f"[red]Failed to send email: {e}[/red]")
        return False


# ============================================================================
# Tracking
# ============================================================================

def load_sent_log(log_path: str = "sent_emails.json") -> Dict:
    """Load the log of sent emails."""
    if Path(log_path).exists():
        with open(log_path) as f:
            return json.load(f)
    return {"sent": []}


def save_sent_log(log: Dict, log_path: str = "sent_emails.json"):
    """Save the log of sent emails."""
    with open(log_path, 'w') as f:
        json.dump(log, f, indent=2, default=str)


def was_email_sent(email: str, log: Dict) -> bool:
    """Check if we already sent to this email."""
    return email.lower() in [e.get('email', '').lower() for e in log.get('sent', [])]


def get_companies_sent_to(log: Dict) -> set:
    """Get set of company names we've already sent emails to."""
    return {e.get('company', '').strip() for e in log.get('sent', []) if e.get('company')}


def was_company_contacted(company_name: str, log: Dict) -> bool:
    """Check if we already sent to this company."""
    sent_companies = get_companies_sent_to(log)
    return company_name.strip() in sent_companies


def get_emails_sent_today(log: Dict) -> int:
    """Count how many emails were sent today."""
    today = datetime.now().date().isoformat()
    return sum(1 for entry in log.get('sent', []) 
               if entry.get('sent_at', '').startswith(today))


# ============================================================================
# CLI
# ============================================================================

@click.command()
@click.option('--resume', '-r', required=True, help='Path to your resume (PDF, DOCX, or TXT)')
@click.option('--recruiters', '-i', default='../email_finder/emails_found.csv', help='Path to recruiters CSV')
@click.option('--preview', is_flag=True, help='Preview emails without sending')
@click.option('--send', 'do_send', is_flag=True, help='Actually send the emails')
@click.option('--use-template', is_flag=True, help='Use template instead of LLM (no API key needed)')
@click.option('--your-name', envvar='YOUR_NAME', help='Your full name')
@click.option('--your-email', envvar='YOUR_EMAIL', help='Your email address')
@click.option('--limit', '-n', type=int, default=None, help='Limit number of emails to send')
@click.option('--delay', type=float, default=30.0, help='Delay between emails in seconds')
@click.option('--company', '-c', multiple=True, help='Only send to specific companies')
@click.option('--add-ps', is_flag=True, help='Add P.S. about this being a custom-built tool with GitHub link')
@click.option('--github-url', default='https://github.com/Gilad28/RecruitAI', help='GitHub repo URL for the P.S.')
@click.option('--verify/--no-verify', default=True, help='Verify emails before sending (default: verify)')
@click.option('--skip-invalid', is_flag=True, default=True, help='Skip emails that fail verification')
@click.option('--daily-limit', type=int, default=None, help='Maximum emails to send per day (for spreading out sends)')
@click.option('--yes', 'confirm_send', is_flag=True, help='Skip confirmation and send immediately')
def main(resume, recruiters, preview, do_send, use_template, your_name, your_email, limit, delay, company, add_ps, github_url, verify, skip_invalid, daily_limit, confirm_send):
    """Send personalized outreach emails to recruiters."""
    
    console.print(Panel.fit(
        "[bold cyan]📧 Recruiter Outreach[/bold cyan]\n"
        "Personalized emails for your job search",
        border_style="cyan"
    ))
    
    # Validate inputs
    if not your_name:
        your_name = click.prompt("Your full name")
    if not your_email:
        your_email = click.prompt("Your email address")
    
    if do_send and preview:
        console.print("[yellow]Both --preview and --send specified. Running in preview mode.[/yellow]")
        do_send = False
    
    if not preview and not do_send:
        console.print("[yellow]No action specified. Use --preview or --send[/yellow]")
        preview = True
    
    # Parse resume
    console.print(f"\n[bold]📄 Loading resume:[/bold] {resume}")
    try:
        resume_text = parse_resume(resume)
        console.print(f"   [green]✓[/green] Extracted {len(resume_text)} characters")
    except Exception as e:
        console.print(f"[red]Error loading resume: {e}[/red]")
        sys.exit(1)
    
    # Load recruiters
    console.print(f"\n[bold]👥 Loading recruiters:[/bold] {recruiters}")
    try:
        with open(recruiters, 'r') as f:
            reader = csv.DictReader(f)
            all_recruiters = list(reader)
    except Exception as e:
        console.print(f"[red]Error loading recruiters: {e}[/red]")
        sys.exit(1)
    
    # Filter recruiters
    recruiters_to_email = []
    for rec in all_recruiters:
        email = rec.get('best_email', '').strip()
        if not email:
            continue
        
        company_name = rec.get('company_name', '')
        if company and company_name not in company:
            continue
        
        recruiters_to_email.append(rec)

    # Load sent log early so we can skip already-contacted companies/emails BEFORE verification
    sent_log = load_sent_log()
    sent_companies = get_companies_sent_to(sent_log)
    if sent_companies:
        console.print(
            f"\n[dim]Already contacted {len(sent_companies)} companies; will skip them.[/dim]"
        )

    recruiters_to_email = [
        r for r in recruiters_to_email
        if not was_email_sent(r.get('best_email', ''), sent_log)
        and not was_company_contacted(r.get('company_name', ''), sent_log)
    ]

    if limit:
        recruiters_to_email = recruiters_to_email[:limit]

    console.print(f"   [green]✓[/green] Found {len(recruiters_to_email)} recruiters to contact")
    
    # Verify emails and try alternative patterns
    email_updates = {}  # Maps original email -> valid email to use
    
    if verify and recruiters_to_email:
        console.print(f"\n[bold]🔍 Verifying emails & finding valid patterns...[/bold]")
        
        validation_results = batch_find_valid_emails(recruiters_to_email, console)
        
        # Process results
        valid_count = 0
        invalid_count = 0
        pattern_found_count = 0
        
        console.print("\n[bold]Email Verification Results:[/bold]")
        for original_email, result in validation_results.items():
            valid_email = result['valid_email']
            status = result['status']
            company = result['company']
            
            if valid_email:
                valid_count += 1
                if valid_email != original_email:
                    pattern_found_count += 1
                    console.print(f"   [green]✓[/green] {company}: [yellow]{original_email}[/yellow] → [green]{valid_email}[/green]")
                    email_updates[original_email] = valid_email
                else:
                    console.print(f"   [green]✓[/green] {company}: {original_email}")
            else:
                invalid_count += 1
                console.print(f"   [red]✗[/red] {company}: {original_email} - {status}")
        
        console.print(f"\n   [green]✓ Valid:[/green] {valid_count}  [yellow]⟳ Pattern fixed:[/yellow] {pattern_found_count}  [red]✗ Invalid:[/red] {invalid_count}")
        
        # Update recruiters with corrected emails
        for rec in recruiters_to_email:
            original = rec.get('best_email', '')
            if original in email_updates:
                rec['best_email'] = email_updates[original]
                rec['original_email'] = original  # Keep track of original
        
        # Filter out invalid emails if skip_invalid is True
        if skip_invalid and invalid_count > 0:
            recruiters_to_email = [
                r for r in recruiters_to_email 
                if validation_results.get(r.get('original_email', r.get('best_email', '')), {}).get('valid_email')
            ]
            console.print(f"\n   [yellow]Continuing with {len(recruiters_to_email)} verified emails[/yellow]")
    
    # Show table of recruiters
    table = Table(title="Recruiters to Contact")
    table.add_column("Company", style="cyan")
    table.add_column("Email", style="green")
    table.add_column("Status", style="yellow")
    
    for rec in recruiters_to_email:
        email = rec.get('best_email', '')
        company_name = rec.get('company_name', '')
        status = "Already sent" if was_email_sent(email, sent_log) else "Ready"
        table.add_row(company_name, email, status)
    
    console.print(table)
    
    # Filter out already sent emails AND companies
    sent_companies = get_companies_sent_to(sent_log)
    console.print(f"\n[dim]Already contacted {len(sent_companies)} companies: {', '.join(sorted(sent_companies)[:10])}{'...' if len(sent_companies) > 10 else ''}[/dim]")
    
    recruiters_to_email = [
        r for r in recruiters_to_email 
        if not was_email_sent(r.get('best_email', ''), sent_log)
        and not was_company_contacted(r.get('company_name', ''), sent_log)
    ]
    
    if len(recruiters_to_email) < len([r for r in recruiters_to_email if not was_email_sent(r.get('best_email', ''), sent_log)]):
        filtered_by_company = len([r for r in recruiters_to_email if not was_email_sent(r.get('best_email', ''), sent_log)]) - len(recruiters_to_email)
        console.print(f"[yellow]Filtered out {filtered_by_company} recruiters from already-contacted companies[/yellow]")
    
    if not recruiters_to_email:
        console.print("\n[yellow]No new recruiters to contact.[/yellow]")
        return
    
    console.print(f"\n[bold]📝 Generating {len(recruiters_to_email)} personalized emails...[/bold]\n")
    
    emails_to_send = []
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("Generating emails...", total=len(recruiters_to_email))
        
        for rec in recruiters_to_email:
            email = rec.get('best_email', '')
            company_name = rec.get('company_name', '')
            
            # Extract recruiter name from context or email
            context = rec.get('best_context', '')
            recruiter_name = ""
            if "LinkedIn recruiter:" in context:
                recruiter_name = context.split("LinkedIn recruiter:")[1].split("-")[0].strip()
            if not recruiter_name:
                local_part = email.split('@')[0]
                recruiter_name = local_part.replace('.', ' ').replace('_', ' ').title()
            
            progress.update(task, description=f"Generating for {company_name}...")
            
            try:
                if use_template:
                    email_content = generate_email_template(
                        recruiter_name=recruiter_name,
                        company_name=company_name,
                        resume_text=resume_text,
                        your_name=your_name,
                    )
                else:
                    email_content = generate_email_with_llm(
                        recruiter_name=recruiter_name,
                        company_name=company_name,
                        recruiter_email=email,
                        resume_text=resume_text,
                        your_name=your_name,
                        your_email=your_email,
                    )
                
                # Add P.S. if requested
                body = email_content['body']
                if add_ps:
                    ps_text = f"\n\nP.S. I built a tool that finds recruiters via LinkedIn, generates personalized emails with LLMs (OpenAI), and sends them - that's how I found you and wrote this! I reviewed it before sending. Check it out: {github_url}"
                    body += ps_text
                
                emails_to_send.append({
                    'to_email': email,
                    'to_name': recruiter_name,
                    'company': company_name,
                    'subject': email_content['subject'],
                    'body': body,
                })
                
            except Exception as e:
                console.print(f"[red]Error generating email for {company_name}: {e}[/red]")
            
            progress.advance(task)
    
    # Preview emails
    if preview or not do_send:
        console.print("\n[bold cyan]═══ EMAIL PREVIEWS ═══[/bold cyan]\n")
        
        for i, email_data in enumerate(emails_to_send, 1):
            console.print(Panel(
                f"[bold]To:[/bold] {email_data['to_name']} <{email_data['to_email']}>\n"
                f"[bold]Company:[/bold] {email_data['company']}\n"
                f"[bold]Subject:[/bold] {email_data['subject']}\n\n"
                f"{email_data['body']}",
                title=f"Email {i}/{len(emails_to_send)}",
                border_style="green"
            ))
            console.print()
        
        if not do_send:
            console.print("[yellow]Preview mode - no emails sent.[/yellow]")
            console.print("[dim]Run with --send to actually send these emails.[/dim]")
            return
    
    # Send emails
    if do_send:
        # Check daily limit
        if daily_limit:
            emails_sent_today = get_emails_sent_today(sent_log)
            remaining_today = daily_limit - emails_sent_today
            
            if remaining_today <= 0:
                console.print(f"\n[yellow]⚠ Daily limit reached ({daily_limit} emails/day). Already sent {emails_sent_today} today.[/yellow]")
                console.print("[dim]Run again tomorrow or increase --daily-limit[/dim]")
                return
            
            if len(emails_to_send) > remaining_today:
                console.print(f"\n[yellow]⚠ Daily limit: {daily_limit} emails/day. Already sent {emails_sent_today} today.[/yellow]")
                console.print(f"[yellow]Will send {remaining_today} emails now (out of {len(emails_to_send)} total).[/yellow]")
                emails_to_send = emails_to_send[:remaining_today]
        
        if not confirm_send and not Confirm.ask(f"\n[bold red]Send {len(emails_to_send)} emails?[/bold red]"):
            console.print("[yellow]Cancelled.[/yellow]")
            return
        
        console.print(f"\n[bold]📤 Sending {len(emails_to_send)} emails...[/bold]\n")
        
        sent_count = 0
        for i, email_data in enumerate(emails_to_send, 1):
            console.print(f"[{i}/{len(emails_to_send)}] Sending to {email_data['to_email']}...")
            
            try:
                success = send_email_smtp(
                    to_email=email_data['to_email'],
                    subject=email_data['subject'],
                    body=email_data['body'],
                    from_email=your_email,
                    from_name=your_name,
                    resume_path=resume,
                )
                
                if success:
                    console.print(f"   [green]✓ Sent![/green]")
                    sent_count += 1
                    
                    # Log it
                    sent_log['sent'].append({
                        'email': email_data['to_email'],
                        'company': email_data['company'],
                        'subject': email_data['subject'],
                        'sent_at': datetime.now().isoformat(),
                    })
                    save_sent_log(sent_log)
                else:
                    console.print(f"   [red]✗ Failed[/red]")
                
                # Delay between emails
                if i < len(emails_to_send):
                    console.print(f"   [dim]Waiting {delay}s...[/dim]")
                    time.sleep(delay)
                    
            except Exception as e:
                console.print(f"   [red]✗ Error: {e}[/red]")
        
        console.print(f"\n[bold green]✓ Sent {sent_count}/{len(emails_to_send)} emails![/bold green]")


if __name__ == '__main__':
    main()

