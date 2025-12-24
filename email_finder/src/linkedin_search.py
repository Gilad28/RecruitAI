"""
LinkedIn search via You.com API to find recruiter names.
Uses the youdotcom SDK.
"""

import os
import re
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# Common email patterns
EMAIL_PATTERNS = [
    '{first}.{last}',
    '{first}{last}',
    '{f}{last}',
    '{first}.{l}',
    '{first}_{last}',
    '{f}.{last}',
    '{last}.{first}',
    '{first}-{last}',
]

# Pattern to extract names from LinkedIn titles
NAME_PATTERNS = [
    re.compile(r'^([A-Z][a-z]+)\s+([A-Z][a-z]+)\s*[-–—|·]'),  # "John Smith - ..."
    re.compile(r'^([A-Z][a-z]+)\s+([A-Z][a-z]+)\s*$'),  # Just "John Smith"
]


class LinkedInSearcher:
    """Search for recruiters via LinkedIn using You.com API."""
    
    def __init__(self, api_key: Optional[str] = None, rate_limit: float = 1.0):
        self.api_key = api_key or os.environ.get('YOU_API_KEY') or os.environ.get('BRAVE_API_KEY', '')
        self.rate_limit = rate_limit
        self._you_client = None
        
        if not self.api_key:
            logger.warning("No API key provided. Set YOU_API_KEY environment variable.")
    
    def _get_client(self):
        """Get or create You.com client."""
        if self._you_client is None and self.api_key:
            try:
                from youdotcom import You
                self._you_client = You(self.api_key)
            except ImportError:
                logger.error("youdotcom package not installed. Run: pip install youdotcom")
                return None
            except Exception as e:
                logger.error(f"Failed to create You.com client: {e}")
                return None
        return self._you_client
    
    def _search(self, query: str) -> List[Dict]:
        """Search using You.com API."""
        client = self._get_client()
        if not client:
            return []
        
        try:
            res = client.search.unified(query=query)
            
            results = []
            
            # The results are in res.results.web
            if hasattr(res, 'results') and hasattr(res.results, 'web') and res.results.web:
                for hit in res.results.web:
                    results.append({
                        'title': getattr(hit, 'title', '') or '',
                        'url': getattr(hit, 'url', '') or '',
                        'description': getattr(hit, 'description', '') or '',
                    })
            
            logger.info(f"You.com returned {len(results)} results for: {query[:50]}...")
            return results
            
        except Exception as e:
            logger.error(f"You.com search failed: {e}")
            return []
    
    def _is_valid_name(self, first_name: str, last_name: str) -> bool:
        """Validate that names look like real names."""
        if len(first_name) < 2 or len(last_name) < 2:
            return False
        if len(first_name) > 15 or len(last_name) > 15:
            return False
        
        skip_words = {
            'The', 'This', 'That', 'What', 'How', 'Why', 'Our', 'Your',
            'View', 'See', 'Get', 'New', 'Top', 'Best', 'More', 'All',
            'About', 'Jobs', 'Find', 'Work', 'Join', 'Meet', 'Team',
            'Open', 'Apply', 'Sign', 'Log', 'Create', 'Search',
            'Company', 'People', 'Talent', 'Career', 'Careers',
            'Senior', 'Junior', 'Lead', 'Head', 'Director', 'Manager',
            'LinkedIn', 'Profile', 'Page', 'Site', 'Web',
        }
        if first_name in skip_words or last_name in skip_words:
            return False
        
        return True
    
    def _extract_name_from_title(self, title: str) -> Optional[tuple]:
        """Extract first and last name from a LinkedIn title."""
        for pattern in NAME_PATTERNS:
            match = pattern.match(title.strip())
            if match:
                first = match.group(1)
                last = match.group(2)
                if self._is_valid_name(first, last):
                    return first, last
        return None
    
    def _generate_emails(self, first_name: str, last_name: str, domain: str) -> List[str]:
        """Generate likely email addresses from a name."""
        first = first_name.lower()
        last = last_name.lower()
        f = first[0] if first else ''
        l = last[0] if last else ''
        
        emails = []
        for pattern in EMAIL_PATTERNS:
            try:
                email = pattern.format(first=first, last=last, f=f, l=l)
                emails.append(f"{email}@{domain}")
            except (KeyError, IndexError):
                continue
        
        return emails
    
    def find_recruiters(self, company_name: str, domain: str, max_results: int = 10) -> List[Dict]:
        """
        Find recruiters for a company via LinkedIn search.
        
        Returns list of:
        {
            'first_name': 'John',
            'last_name': 'Smith',
            'full_name': 'John Smith',
            'linkedin_url': 'linkedin.com/in/...',
            'emails': ['john.smith@company.com', 'jsmith@company.com', ...]
        }
        """
        if not self.api_key:
            logger.warning("No API key - skipping LinkedIn search")
            return []
        
        logger.info(f"Searching LinkedIn for recruiters at {company_name}")
        
        all_recruiters = []
        seen_names = set()
        
        # Search query
        query = f'{company_name} recruiter LinkedIn'
        results = self._search(query)
        
        for result in results:
            title = result.get('title', '')
            url = result.get('url', '')
            
            # Only process LinkedIn profile results
            if 'linkedin.com/in/' not in url:
                continue
            
            name = self._extract_name_from_title(title)
            if not name:
                continue
            
            first_name, last_name = name
            name_key = f"{first_name.lower()} {last_name.lower()}"
            
            if name_key in seen_names:
                continue
            seen_names.add(name_key)
            
            emails = self._generate_emails(first_name, last_name, domain)
            
            recruiter = {
                'first_name': first_name,
                'last_name': last_name,
                'full_name': f"{first_name} {last_name}",
                'linkedin_url': url,
                'emails': emails,
                'primary_email': emails[0] if emails else '',
                'source': title[:100],
            }
            all_recruiters.append(recruiter)
            
            logger.info(f"Found recruiter: {recruiter['full_name']} -> {recruiter['primary_email']}")
            
            if len(all_recruiters) >= max_results:
                break
        
        logger.info(f"Found {len(all_recruiters)} recruiters for {company_name}")
        return all_recruiters
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._you_client:
            try:
                self._you_client.__exit__(exc_type, exc_val, exc_tb)
            except:
                pass
