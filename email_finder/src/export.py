"""
Export functionality for email finder results.
"""

import logging
from typing import Optional

import pandas as pd

from .db import EmailFinderDB

logger = logging.getLogger(__name__)


def export_to_csv(db: EmailFinderDB, output_path: str) -> int:
    """
    Export results to CSV file.
    
    Args:
        db: Database instance
        output_path: Path for output CSV file
        
    Returns:
        Number of rows exported
    """
    logger.info(f"Exporting results to {output_path}")
    
    # Get all results from database
    results = db.get_all_results()
    
    if not results:
        logger.warning("No results to export")
        # Create empty CSV with headers
        df = pd.DataFrame(columns=[
            'company_name', 'domain', 'best_email', 'best_score',
            'best_label', 'best_source_url', 'best_context',
            'backup_emails', 'confidence'
        ])
        df.to_csv(output_path, index=False)
        return 0
    
    # Build DataFrame
    rows = []
    for row in results:
        # Get backup emails as semicolon-separated string
        backup_ids = row['backup_email_ids'] or ''
        backup_emails = db.get_backup_emails(backup_ids)
        backup_str = ';'.join(backup_emails) if backup_emails else ''
        
        rows.append({
            'company_name': row['company_name'],
            'domain': row['domain'],
            'best_email': row['best_email'] or '',
            'best_score': row['best_score'] or 0,
            'best_label': row['best_label'] or 'unknown',
            'best_source_url': row['best_source_url'] or '',
            'best_context': (row['best_context'] or '')[:500],  # Limit context length
            'backup_emails': backup_str,
            'confidence': row['confidence'] or 0,
        })
    
    df = pd.DataFrame(rows)
    
    # Sort by company name
    df = df.sort_values('company_name')
    
    # Export to CSV
    df.to_csv(output_path, index=False, encoding='utf-8')
    
    logger.info(f"Exported {len(rows)} companies to {output_path}")
    
    return len(rows)


def print_summary(db: EmailFinderDB):
    """Print a summary of results to console."""
    results = db.get_all_results()
    
    if not results:
        print("\nNo results found.")
        return
    
    total = len(results)
    with_email = sum(1 for r in results if r['best_email'])
    recruiting = sum(1 for r in results if r['best_label'] == 'recruiting')
    careers = sum(1 for r in results if r['best_label'] == 'careers')
    avg_confidence = sum(r['confidence'] or 0 for r in results) / total if total else 0
    
    print("\n" + "=" * 50)
    print("EMAIL FINDER RESULTS SUMMARY")
    print("=" * 50)
    print(f"Total companies processed: {total}")
    print(f"Companies with email found: {with_email} ({100*with_email/total:.1f}%)")
    print(f"Recruiting-labeled emails: {recruiting}")
    print(f"Careers-labeled emails: {careers}")
    print(f"Average confidence: {avg_confidence:.2f}")
    print("=" * 50)
    
    # Show top results
    print("\nTop Results:")
    print("-" * 50)
    
    sorted_results = sorted(results, key=lambda x: x['confidence'] or 0, reverse=True)
    
    for i, row in enumerate(sorted_results[:10], 1):
        email = row['best_email'] or 'N/A'
        company = row['company_name']
        label = row['best_label'] or 'unknown'
        confidence = row['confidence'] or 0
        print(f"{i:2}. {company}: {email} [{label}] (conf: {confidence:.2f})")
    
    print("-" * 50)

