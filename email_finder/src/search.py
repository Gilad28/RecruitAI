"""
Web search functionality for domain discovery and seed URL gathering.
Uses DuckDuckGo HTML search as the default engine.
"""

import re
import logging
from typing import List, Optional, Set
from urllib.parse import quote_plus, urlparse, parse_qs
import time

import requests
from bs4 import BeautifulSoup

from .utils import (
    get_registrable_domain, is_excluded_domain, normalize_url,
    get_session, USER_AGENT, CONNECT_TIMEOUT, READ_TIMEOUT
)

logger = logging.getLogger(__name__)


class WebSearcher:
    """Web search for domain discovery and seed URL gathering."""
    
    def __init__(self, engine: str = "duckduckgo", rate_limit: float = 2.0):
        self.engine = engine.lower()
        self.rate_limit = rate_limit
        self.session = get_session()
        self._last_search = 0
    
    def _wait_rate_limit(self):
        """Respect rate limit between searches."""
        now = time.time()
        elapsed = now - self._last_search
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self._last_search = time.time()
    
    def search(self, query: str, num_results: int = 10) -> List[str]:
        """
        Perform a web search and return result URLs.
        
        Args:
            query: Search query string
            num_results: Maximum number of results to return
            
        Returns:
            List of result URLs
        """
        self._wait_rate_limit()
        
        if self.engine == "duckduckgo":
            return self._search_duckduckgo(query, num_results)
        else:
            logger.warning(f"Unknown search engine: {self.engine}, falling back to DuckDuckGo")
            return self._search_duckduckgo(query, num_results)
    
    def _search_duckduckgo(self, query: str, num_results: int) -> List[str]:
        """Search using DuckDuckGo HTML."""
        urls = []
        
        # DuckDuckGo HTML search URL
        search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        
        try:
            response = self.session.get(
                search_url,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Accept': 'text/html,application/xhtml+xml',
                }
            )
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'lxml')
            
            # Find result links
            for result in soup.select('a.result__a'):
                href = result.get('href', '')
                
                # DuckDuckGo wraps URLs, extract actual URL
                if 'uddg=' in href:
                    parsed = urlparse(href)
                    params = parse_qs(parsed.query)
                    if 'uddg' in params:
                        href = params['uddg'][0]
                
                if href.startswith(('http://', 'https://')):
                    urls.append(href)
                    if len(urls) >= num_results:
                        break
            
            logger.debug(f"DuckDuckGo search for '{query}' returned {len(urls)} results")
            
        except Exception as e:
            logger.error(f"DuckDuckGo search failed for '{query}': {e}")
        
        return urls
    
    def discover_domain(self, company_name: str) -> Optional[str]:
        """
        Discover the official domain for a company.
        
        Args:
            company_name: Name of the company
            
        Returns:
            The discovered domain or None
        """
        logger.info(f"Discovering domain for: {company_name}")
        
        # Try different search queries
        queries = [
            f'"{company_name}" official website',
            f'"{company_name}" careers',
            f'{company_name} company homepage',
        ]
        
        domain_votes: dict = {}
        
        for query in queries:
            results = self.search(query, num_results=5)
            
            for i, url in enumerate(results):
                domain = get_registrable_domain(url)
                
                # Skip excluded domains
                if is_excluded_domain(domain):
                    continue
                
                # Skip if domain doesn't seem related to company name
                company_words = set(company_name.lower().split())
                domain_base = domain.split('.')[0].lower()
                
                # Give higher weight to results that match company name
                weight = 5 - i  # Higher weight for top results
                if any(word in domain_base for word in company_words if len(word) > 2):
                    weight += 5  # Bonus for name match
                
                domain_votes[domain] = domain_votes.get(domain, 0) + weight
        
        if not domain_votes:
            logger.warning(f"Could not discover domain for: {company_name}")
            return None
        
        # Pick domain with highest votes
        best_domain = max(domain_votes, key=domain_votes.get)
        confidence = domain_votes[best_domain]
        
        logger.info(f"Discovered domain for {company_name}: {best_domain} (confidence: {confidence})")
        
        if confidence < 5:
            logger.warning(f"Low confidence domain discovery for {company_name}: {best_domain}")
        
        return best_domain
    
    def get_seed_urls(self, company_name: str, domain: str, max_urls: int = 20) -> List[str]:
        """
        Get seed URLs for crawling a company's domain.
        
        Args:
            company_name: Name of the company
            domain: The company's domain
            max_urls: Maximum number of seed URLs
            
        Returns:
            List of seed URLs
        """
        seed_urls: Set[str] = set()
        
        # Add standard career/contact pages
        standard_paths = [
            '/careers', '/jobs', '/about', '/contact',
            '/students', '/university', '/campus',
            '/join', '/join-us', '/work-with-us',
            '/team', '/about-us', '/company',
            '/early-careers', '/internships', '/graduates',
        ]
        
        for scheme in ['https']:  # Prefer HTTPS
            for path in standard_paths:
                seed_urls.add(f"{scheme}://{domain}{path}")
                seed_urls.add(f"{scheme}://www.{domain}{path}")
        
        # Add root
        seed_urls.add(f"https://{domain}")
        seed_urls.add(f"https://www.{domain}")
        
        # Search for additional recruiting-related pages
        search_queries = [
            f'site:{domain} recruiting email',
            f'site:{domain} "university recruiting"',
            f'site:{domain} "early careers"',
            f'site:{domain} careers "@"',
            f'site:{domain} campus recruiting',
            f'site:{domain} talent acquisition',
        ]
        
        for query in search_queries:
            results = self.search(query, num_results=5)
            for url in results:
                # Only keep URLs from the target domain
                url_domain = get_registrable_domain(url)
                if url_domain.lower() == domain.lower():
                    normalized = normalize_url(url)
                    if normalized:
                        seed_urls.add(normalized)
            
            if len(seed_urls) >= max_urls:
                break
        
        # Limit and return
        seed_list = list(seed_urls)[:max_urls]
        logger.info(f"Generated {len(seed_list)} seed URLs for {domain}")
        
        return seed_list

