#!/usr/bin/env python3
"""
Recruiter Email Finder - CLI Tool

Find publicly listed recruiting-related email addresses on company-owned domains.
Respects robots.txt, rate-limits requests, and only crawls company domains.

Usage:
    python email_finder.py --input companies.csv --out emails_found.csv --db emails.db
"""

import argparse
import logging
import sys
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from src.db import EmailFinderDB
from src.search import WebSearcher
from src.crawl import DomainCrawler
from src.extract import EmailExtractor
from src.score import EmailScorer
from src.export import export_to_csv, print_summary
from src.utils import get_registrable_domain, logger
from src.linkedin_search import LinkedInSearcher

# Try to import rich for nice CLI output
try:
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
    from rich.logging import RichHandler
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


def setup_logging(verbose: bool = False):
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    
    if RICH_AVAILABLE:
        logging.basicConfig(
            level=level,
            format="%(message)s",
            handlers=[RichHandler(rich_tracebacks=True, show_path=False)]
        )
    else:
        logging.basicConfig(
            level=level,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )


def load_companies(input_path: str) -> pd.DataFrame:
    """Load companies from input CSV."""
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")
    
    df = pd.read_csv(input_path)
    
    # Check required columns
    if 'company_name' not in df.columns:
        raise ValueError("Input CSV must have 'company_name' column")
    
    # Add company_domain column if missing
    if 'company_domain' not in df.columns:
        df['company_domain'] = None
    
    return df


def process_company(
    company_name: str,
    company_domain: str,
    db: EmailFinderDB,
    searcher: WebSearcher,
    scorer: EmailScorer,
    linkedin_searcher: LinkedInSearcher,
    max_pages: int,
    rate_limit: float,
    use_playwright: bool,
    verbose: bool
) -> dict:
    """
    Process a single company: discover domain, search LinkedIn, crawl, extract, score emails.
    
    Returns:
        Dict with 'success', 'domain', 'emails_found', 'best_email', 'recruiters'
    """
    result = {
        'success': False,
        'domain': None,
        'emails_found': 0,
        'best_email': None,
        'recruiters': []
    }
    
    # Step 0: Determine domain
    if company_domain and pd.notna(company_domain):
        domain = get_registrable_domain(company_domain)
        logger.info(f"Using provided domain for {company_name}: {domain}")
    else:
        logger.info(f"Discovering domain for: {company_name}")
        domain = searcher.discover_domain(company_name)
        if not domain:
            logger.warning(f"Could not discover domain for: {company_name}")
            return result
    
    result['domain'] = domain
    
    # Add company to database
    company_id = db.add_company(company_name, domain)
    
    # Step 1: Search LinkedIn for recruiters (PRIMARY SOURCE)
    recruiters = linkedin_searcher.find_recruiters(company_name, domain, max_results=10)
    result['recruiters'] = recruiters
    
    extracted_emails = []
    
    # Add LinkedIn-found recruiter emails with high scores
    for recruiter in recruiters:
        for email in recruiter.get('emails', [])[:3]:  # Top 3 patterns per recruiter
            email_data = {
                'email': email,
                'context': f"LinkedIn recruiter: {recruiter['full_name']} - {recruiter.get('source', '')}",
                'source_url': recruiter.get('linkedin_url', 'LinkedIn search'),
                'is_personal': True,
                'is_linkedin': True,
                'recruiter_name': recruiter['full_name'],
            }
            if not db.email_exists(company_id, email):
                extracted_emails.append(email_data)
    
    if recruiters:
        logger.info(f"Found {len(recruiters)} recruiters from LinkedIn for {company_name}")
    
    # Step 2: Get seed URLs for website crawl (SECONDARY SOURCE)
    seed_urls = searcher.get_seed_urls(company_name, domain)
    
    # Step 3: Crawl website and extract emails
    if seed_urls:
        extractor = EmailExtractor(domain)
        
        def page_callback(url: str, final_url: str, html: str):
            """Callback to extract emails from each crawled page."""
            emails = extractor.extract_emails(html, final_url)
            for email_data in emails:
                if not db.email_exists(company_id, email_data['email']):
                    extracted_emails.append(email_data)
        
        crawler = DomainCrawler(
            target_domain=domain,
            db=db,
            company_id=company_id,
            rate_limit=rate_limit,
            max_pages=max_pages,
            use_playwright=use_playwright,
            verbose=verbose
        )
        
        pages_crawled = crawler.crawl(seed_urls, page_callback)
        logger.info(f"Crawled {pages_crawled} pages for {company_name}")
    
    # Step 4: Score and store emails
    for email_data in extracted_emails:
        # LinkedIn recruiter emails get a high base score
        is_linkedin = email_data.get('is_linkedin', False)
        is_personal = email_data.get('is_personal', False)
        
        if is_linkedin:
            # High score for LinkedIn-sourced personal emails
            score = 15.0
            label = 'recruiter'
            notes = f"From LinkedIn: {email_data.get('recruiter_name', '')}"
        else:
            score, label, notes = scorer.score_email(
                email_data['email'],
                email_data.get('context', ''),
                email_data.get('source_url', '')
            )
            # Boost personal-looking emails
            if is_personal:
                score += 5.0
        
        email_id = db.add_email(
            company_id=company_id,
            email=email_data['email'],
            score=score,
            label=label,
            source_url=email_data.get('source_url', ''),
            context=email_data.get('context', '')
        )
    
    result['emails_found'] = len(extracted_emails)
    
    # Step 5: Choose best email + backups
    company_emails = db.get_company_emails(company_id)
    
    if company_emails:
        # Convert to list of dicts for ranking
        email_list = [{
            'id': e['id'],
            'email': e['email'],
            'score': e['score'],
            'label': e['label'],
            'source_url': e['source_url'],
            'context': e['context']
        } for e in company_emails]
        
        best, backups, confidence, notes = scorer.rank_company_emails(email_list)
        
        if best:
            backup_ids = ','.join(str(b['id']) for b in backups)
            db.add_result(
                company_id=company_id,
                best_email_id=best['id'],
                backup_email_ids=backup_ids,
                confidence=confidence,
                notes=notes
            )
            result['best_email'] = best['email']
            result['success'] = True
            logger.info(f"Best email for {company_name}: {best['email']} (score: {best['score']:.1f})")
    else:
        # No emails found, still add result entry
        db.add_result(
            company_id=company_id,
            best_email_id=None,
            backup_email_ids='',
            confidence=0,
            notes='No recruiting emails found'
        )
        logger.warning(f"No emails found for {company_name}")
    
    return result


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Find recruiting email addresses on company-owned domains.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python email_finder.py --input companies.csv --out emails_found.csv
    python email_finder.py --input companies.csv --out emails.csv --db emails.db --verbose
    python email_finder.py --input companies.csv --out emails.csv --max-pages-per-company 50

Input CSV format:
    company_name,company_domain
    "Acme Corp",acme.com
    "TechStart Inc",  (domain will be discovered)
        """
    )
    
    parser.add_argument(
        '--input', '-i',
        required=True,
        help='Input CSV file with company_name and optional company_domain columns'
    )
    parser.add_argument(
        '--out', '-o',
        required=True,
        help='Output CSV file for results'
    )
    parser.add_argument(
        '--db',
        default='emails.db',
        help='SQLite database file (default: emails.db)'
    )
    parser.add_argument(
        '--max-pages-per-company',
        type=int,
        default=25,
        help='Maximum pages to crawl per company (default: 25)'
    )
    parser.add_argument(
        '--rate-limit',
        type=float,
        default=1.0,
        help='Seconds between requests per domain (default: 1.0)'
    )
    parser.add_argument(
        '--use-playwright',
        action='store_true',
        default=False,
        help='Use Playwright for JavaScript-rendered pages'
    )
    parser.add_argument(
        '--search-engine',
        default='duckduckgo',
        choices=['duckduckgo'],
        help='Search engine for domain discovery (default: duckduckgo)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.verbose)
    
    # Print banner
    if RICH_AVAILABLE:
        console = Console()
        console.print("\n[bold blue]╔══════════════════════════════════════════╗[/bold blue]")
        console.print("[bold blue]║[/bold blue]     [bold white]Recruiter Email Finder[/bold white]              [bold blue]║[/bold blue]")
        console.print("[bold blue]║[/bold blue]     [dim]Company-Domain Only Edition[/dim]        [bold blue]║[/bold blue]")
        console.print("[bold blue]╚══════════════════════════════════════════╝[/bold blue]\n")
    else:
        print("\n" + "=" * 45)
        print("    Recruiter Email Finder")
        print("    Company-Domain Only Edition")
        print("=" * 45 + "\n")
    
    try:
        # Load input
        logger.info(f"Loading companies from {args.input}")
        companies_df = load_companies(args.input)
        total_companies = len(companies_df)
        logger.info(f"Loaded {total_companies} companies")
        
        # Initialize components
        db = EmailFinderDB(args.db)
        searcher = WebSearcher(engine=args.search_engine, rate_limit=2.0)
        scorer = EmailScorer()
        linkedin_searcher = LinkedInSearcher(rate_limit=1.0)
        
        # Check for LinkedIn search capability
        if linkedin_searcher.api_key:
            logger.info("LinkedIn search enabled (Brave API)")
        else:
            logger.warning("LinkedIn search disabled - set BRAVE_API_KEY for recruiter search")
        
        # Process each company
        results = []
        
        if RICH_AVAILABLE:
            console = Console()
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=console
            ) as progress:
                task = progress.add_task("Processing companies...", total=total_companies)
                
                for idx, row in companies_df.iterrows():
                    company_name = row['company_name']
                    company_domain = row.get('company_domain')
                    
                    progress.update(task, description=f"Processing: {company_name}")
                    
                    result = process_company(
                        company_name=company_name,
                        company_domain=company_domain,
                        db=db,
                        searcher=searcher,
                        scorer=scorer,
                        linkedin_searcher=linkedin_searcher,
                        max_pages=args.max_pages_per_company,
                        rate_limit=args.rate_limit,
                        use_playwright=args.use_playwright,
                        verbose=args.verbose
                    )
                    results.append(result)
                    progress.advance(task)
        else:
            for idx, row in companies_df.iterrows():
                company_name = row['company_name']
                company_domain = row.get('company_domain')
                
                print(f"\n[{idx + 1}/{total_companies}] Processing: {company_name}")
                
                result = process_company(
                    company_name=company_name,
                    company_domain=company_domain,
                    db=db,
                    searcher=searcher,
                    scorer=scorer,
                    linkedin_searcher=linkedin_searcher,
                    max_pages=args.max_pages_per_company,
                    rate_limit=args.rate_limit,
                    use_playwright=args.use_playwright,
                    verbose=args.verbose
                )
                results.append(result)
        
        # Export results
        logger.info(f"Exporting results to {args.out}")
        exported = export_to_csv(db, args.out)
        
        # Print summary
        print_summary(db)
        
        # Final stats
        successful = sum(1 for r in results if r['success'])
        total_emails = sum(r['emails_found'] for r in results)
        
        print(f"\nCompleted: {successful}/{total_companies} companies with emails found")
        print(f"Total emails extracted: {total_emails}")
        print(f"Results saved to: {args.out}")
        print(f"Database saved to: {args.db}")
        
    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(1)
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()

