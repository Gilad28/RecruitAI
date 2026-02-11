#!/usr/bin/env python3
"""
Find startups on AngelList/Wellfound and discover their recruiter emails.
"""

import argparse
import sys
import os
import re
from pathlib import Path
import pandas as pd
import logging
from dotenv import load_dotenv

# Load from project root (find_emails.py sets cwd)
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.linkedin_search import LinkedInSearcher
from src.search import WebSearcher
from src.utils import get_registrable_domain, logger

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Query variations: expand user's terms to similar/related searches
QUERY_EXPANSIONS = {
    'ai': ['AI', 'machine learning', 'ML', 'artificial intelligence', 'deep learning', 'computer vision', 'NLP', 'generative AI'],
    'ml': ['machine learning', 'ML', 'AI', 'deep learning'],
    'machine': ['machine learning', 'ML', 'AI'],
    'fintech': ['fintech', 'finance', 'payments', 'banking', 'fintech startup'],
    'health': ['health', 'healthcare', 'biotech', 'medtech', 'health tech'],
    'software': ['software', 'SaaS', 'tech', 'software engineering'],
    'data': ['data', 'data science', 'analytics', 'big data'],
    'cyber': ['cybersecurity', 'security', 'infosec'],
    'edtech': ['edtech', 'education', 'learning'],
    'climate': ['climate', 'clean tech', 'sustainability', 'green tech'],
}


def _expand_query(query: str) -> list:
    """Generate similar queries from user input."""
    words = query.lower().split()
    bases = [query.strip()]
    for w in words:
        if len(w) < 3:
            continue
        for key, variants in QUERY_EXPANSIONS.items():
            if key in w or w in key:
                for v in variants[:5]:
                    bases.append(v)
                break
    # Always include first significant word as standalone
    for w in words:
        if len(w) >= 4 and w not in ('startup', 'internship', 'intern', 'hiring'):
            bases.append(w)
            break
    # Dedupe, keep original first
    seen = {query.strip().lower()}
    result = [query.strip()]
    for b in bases[1:]:
        if b.lower() not in seen:
            seen.add(b.lower())
            result.append(b)
    return result[:20]


def _build_search_queries(bases: list) -> list:
    """Build full search query list from base terms."""
    queries = []
    templates = [
        "{} startup",
        "{} startup company",
        "{} early stage startup",
        "{} seed stage startup",
        "{} startup founder",
        "{} Y Combinator",
        "{} startup Wellfound",
        "{} startup AngelList",
        "{} series A startup",
        "{} tech startup",
    ]
    for base in bases:
        for t in templates:
            q = t.format(base)
            if q not in queries:
                queries.append(q)
    # Add generic queries to find startup directories
    for g in ["YC startups", "Wellfound startups", "AngelList companies", "early stage startups"]:
        if g not in queries:
            queries.append(g)
    return queries


def find_startups_and_recruiters(
    query: str = "AI startup",
    max_startups: int = 200,
    output_csv: str = "startups_found.csv",
    exclude_companies: set = None,
) -> pd.DataFrame:
    """
    Find small startups and discover their founder/CEO/recruiter emails.
    Searches for startups on Wellfound/AngelList and finds decision-maker contacts.
    """
    logger.info(f"Searching for startups: {query} (target: {max_startups})")
    
    linkedin_searcher = LinkedInSearcher(rate_limit=1.0)
    web_searcher = WebSearcher(rate_limit=2.0)
    
    if not linkedin_searcher.api_key:
        logger.error("YOU_API_KEY not set. Cannot search LinkedIn.")
        logger.info("Set YOU_API_KEY environment variable to search for startups.")
        return pd.DataFrame()
    
    # Expand user query to similar terms, build many search queries
    bases = _expand_query(query)
    search_queries = _build_search_queries(bases)
    logger.info(f"Using {len(search_queries)} search variations across {len(bases)} related terms")
    
    all_companies = set()
    results = []
    exclude_companies = exclude_companies or set()
    if exclude_companies:
        logger.info(f"Skipping {len(exclude_companies)} already-contacted companies")
    
    query_idx = 0
    while len(results) < max_startups:
        if query_idx >= len(search_queries):
            logger.info(f"Exhausted {len(search_queries)} queries; found {len(results)} (target {max_startups})")
            break
        search_query = search_queries[query_idx]
        query_idx += 1
        logger.info(f"Searching [{query_idx}/{len(search_queries)}]: {search_query} ({len(results)}/{max_startups} so far)")
        
        # Focus on Wellfound/AngelList - more reliable than LinkedIn
        search_results = linkedin_searcher._search(f"{search_query} site:wellfound.com OR site:angel.co")
        
        logger.info(f"  Processing {len(search_results)} results from search")
        for result in search_results:
            title = result.get('title', '')
            url = result.get('url', '')
            desc = result.get('description', '')
            
            company_name = None
            
            # Prioritize Wellfound/AngelList links - these are most reliable
            if 'wellfound.com' in url or 'angel.co' in url:
                # Extract company name from Wellfound URL - MOST RELIABLE SOURCE
                # Try multiple URL patterns: /company/, /l/, /startups/
                wellfound_match = re.search(r'(?:wellfound|angel)\.(?:com|co)/(?:company|l|startups)/([^/?]+)', url)
                if wellfound_match:
                    company_slug = wellfound_match.group(1)
                    company_name = company_slug.replace('-', ' ').title()
                    logger.info(f"  Extracted from Wellfound URL: {company_name}")
                else:
                    logger.info(f"  Wellfound URL but couldn't extract: {url}")
            
            # Skip LinkedIn profiles entirely - too noisy and unreliable
            elif 'linkedin.com' in url:
                continue
            
            if not company_name:
                continue
            
            # Filter out common false positives and invalid names
            skip_words = {
                'LinkedIn', 'Profile', 'View', 'See', 'More', 'Jobs', 'Hiring', 
                'Wellfound', 'AngelList', 'Angel', 'Startup', 'Intern', 'Internship',
                'Program', 'Careers', 'Hire', 'Sign', 'Up', 'Part', 'Early', 'Industry',
                'Pricing', 'Software', 'Engineer', 'Top', 'Tech', 'Companies', 'Featured',
                'Lists', 'Virtual', 'The', 'Internect', 'ML', 'AI', 'Project', 'Labs',
                'Ventures', 'Solutions', 'Innovative', 'Unstuck', 'Parenthood'
            }
            
            # Check if name contains skip words or is too generic
            name_lower = company_name.lower()
            if any(word.lower() in name_lower for word in skip_words):
                logger.info(f"  Filtered out (skip word): {company_name}")
                continue
            
            # Must be 3-50 characters and look like a company name
            if len(company_name) < 3 or len(company_name) > 50:
                logger.info(f"  Filtered out (length): {company_name}")
                continue
            
            # Should not be all caps (likely not a real name)
            if company_name.isupper() and len(company_name) > 10:
                logger.info(f"  Filtered out (all caps): {company_name}")
                continue
            
            if company_name not in all_companies:
                if company_name in exclude_companies:
                    continue
                all_companies.add(company_name)
                logger.info(f"Found startup: {company_name}")
                
                # Discover domain
                domain = web_searcher.discover_domain(company_name)
                if not domain:
                    logger.warning(f"  ✗ No domain found for {company_name}, skipping")
                    continue
                if domain:
                    domain = get_registrable_domain(domain)
                    
                    # Find founders/CEOs/recruiters for this company
                    recruiters = linkedin_searcher.find_recruiters(company_name, domain, max_results=2)
                    
                    if recruiters:
                        # Prefer founder/CEO over recruiter
                        best_recruiter = recruiters[0]
                        for r in recruiters:
                            if 'founder' in r.get('role', '').lower() or 'ceo' in r.get('role', '').lower():
                                best_recruiter = r
                                break
                        
                        best_email = best_recruiter.get('primary_email', '')
                        recruiter_name = best_recruiter.get('full_name', '')
                        role = best_recruiter.get('role', 'Contact')
                        
                        results.append({
                            'company_name': company_name,
                            'domain': domain,
                            'best_email': best_email,
                            'recruiter_name': recruiter_name,
                            'best_score': 15.0,
                            'best_label': role.lower(),
                            'best_source_url': best_recruiter.get('linkedin_url', ''),
                            'best_context': f"LinkedIn {role}: {recruiter_name} - Small startup/company",
                            'backup_emails': ';'.join(best_recruiter.get('emails', [])[1:3]),
                            'confidence': 1.0,
                        })
                        logger.info(f"  ✓ Found {role}: {recruiter_name} ({best_email})")
                    else:
                        # Fallback: use common contact emails
                        for local in ['info', 'hello', 'contact', 'careers', 'team']:
                            fallback_email = f"{local}@{domain}"
                            results.append({
                                'company_name': company_name,
                                'domain': domain,
                                'best_email': fallback_email,
                                'recruiter_name': 'Team',
                                'best_score': 5.0,
                                'best_label': 'generic',
                                'best_source_url': '',
                                'best_context': f"Generic contact email - {company_name}",
                                'backup_emails': '',
                                'confidence': 0.5,
                            })
                            logger.info(f"  ✓ Fallback: {fallback_email} (no LinkedIn contact found)")
                            break
                    
                    if len(results) >= max_startups:
                        break
        
        if len(results) >= max_startups:
            break
    
    # Save to CSV
    if results:
        df = pd.DataFrame(results)
        df.to_csv(output_csv, index=False)
        logger.info(f"Saved {len(results)} startups to {output_csv}")
    else:
        logger.warning("No startups found. Make sure YOU_API_KEY is set.")
    
    return pd.DataFrame(results)


def main():
    parser = argparse.ArgumentParser(description='Find small startups and their founder/CEO/recruiter contacts')
    parser.add_argument('--query', '-q', default='AI startup', help='Search query (e.g., "AI startup", "fintech startup")')
    parser.add_argument('--max', '-m', type=int, default=200, help='Maximum startups to find')
    parser.add_argument('--output', '-o', default='startups_found.csv', help='Output CSV file')
    
    args = parser.parse_args()
    
    find_startups_and_recruiters(
        query=args.query,
        max_startups=args.max,
        output_csv=args.output
    )


if __name__ == '__main__':
    main()
