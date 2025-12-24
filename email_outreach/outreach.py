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
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Optional, List, Dict
import time

from dotenv import load_dotenv
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn

# Load environment variables
load_dotenv()

console = Console()

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
    
    prompt = f"""You are helping a computer science student write a personalized cold outreach email to a recruiter to land an INTERNSHIP.

RECRUITER INFO:
- Name: {recruiter_name}
- Company: {company_name}
- Email: {recruiter_email}

STUDENT INFO:
- Name: {your_name}
- Email: {your_email}
- Currently pursuing B.S. in Computer Science at Washington State University

STUDENT'S RESUME:
{resume_text[:4000]}

{f"CUSTOM INTRO/CONTEXT: {custom_intro}" if custom_intro else ""}

Write a professional but warm cold outreach email that:
1. Has a compelling subject line that mentions the company and internship interest
2. Opens with a brief, genuine hook about the company (something specific about their product/mission)
3. Clearly states they are a CS student actively seeking an INTERNSHIP opportunity
4. Quickly highlights 2-3 relevant skills/experiences (especially their AI/GenAI internship experience at LettuceCo and Worknet.ai)
5. Shows enthusiasm for learning and contributing at {company_name}
6. Ends with a soft call-to-action (asking about internship opportunities or a brief chat)
7. Is concise (under 150 words for the body)
8. Sounds genuine, eager, and student-appropriate - not overly formal

Return your response as JSON with these exact keys:
{{
    "subject": "The email subject line",
    "body": "The email body (plain text, with proper line breaks)"
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
    
    subject = f"CS Student Seeking AI/Software Internship at {company_name}"
    
    body = f"""Hi {recruiter_name.split()[0] if recruiter_name else 'there'},

I came across your profile and noticed you're part of the talent team at {company_name}. I'm a Computer Science student at Washington State University actively seeking an internship, and I'm genuinely excited about what you're building.

I've already completed two AI internships where I built production chatbots and AI agents using {skills_text}. I'd love to bring that hands-on experience to {company_name} and continue learning from your team.

Are there any internship opportunities I should apply for, or would you be open to a quick chat?

Thanks so much,
{your_name}"""

    return {"subject": subject, "body": body}


# ============================================================================
# Email Sending
# ============================================================================

def send_email_smtp(
    to_email: str,
    subject: str,
    body: str,
    from_email: str,
    from_name: str,
    smtp_server: str = "smtp.gmail.com",
    smtp_port: int = 587,
    smtp_password: Optional[str] = None,
) -> bool:
    """Send email via SMTP."""
    
    password = smtp_password or os.environ.get('SMTP_PASSWORD') or os.environ.get('GMAIL_APP_PASSWORD')
    if not password:
        raise ValueError("SMTP_PASSWORD or GMAIL_APP_PASSWORD not set in environment")
    
    # Create message
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{from_email}>"
    msg["To"] = to_email
    
    # Add plain text body
    msg.attach(MIMEText(body, "plain"))
    
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
@click.option('--github-url', default='https://github.com/giladheitner/RecruitAI', help='GitHub repo URL for the P.S.')
def main(resume, recruiters, preview, do_send, use_template, your_name, your_email, limit, delay, company, add_ps, github_url):
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
    
    if limit:
        recruiters_to_email = recruiters_to_email[:limit]
    
    console.print(f"   [green]✓[/green] Found {len(recruiters_to_email)} recruiters to contact")
    
    # Load sent log
    sent_log = load_sent_log()
    
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
    
    # Filter out already sent
    recruiters_to_email = [r for r in recruiters_to_email if not was_email_sent(r.get('best_email', ''), sent_log)]
    
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
                    ps_text = f"\n\nP.S. I built a tool that finds recruiters via LinkedIn, generates personalized emails with GPT, and sends them - that's how I found you and wrote this! I reviewed it before sending. Check it out: {github_url}"
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
        if not Confirm.ask(f"\n[bold red]Send {len(emails_to_send)} emails?[/bold red]"):
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

