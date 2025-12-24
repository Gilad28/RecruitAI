"""
BFS crawler for company domains.
Respects robots.txt, rate limits, and stays within company domains.
"""

import logging
from collections import deque
from typing import List, Set, Optional, Tuple, Callable
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from .utils import (
    normalize_url, is_same_registrable_domain, is_html_url,
    url_has_priority_keywords, get_session, RateLimiter, RobotsChecker,
    USER_AGENT, CONNECT_TIMEOUT, READ_TIMEOUT, get_full_domain
)
from .db import EmailFinderDB

logger = logging.getLogger(__name__)


class DomainCrawler:
    """BFS crawler that stays within a company's domain."""
    
    def __init__(
        self,
        target_domain: str,
        db: EmailFinderDB,
        company_id: int,
        rate_limit: float = 1.0,
        max_pages: int = 25,
        use_playwright: bool = False,
        verbose: bool = False
    ):
        self.target_domain = target_domain
        self.db = db
        self.company_id = company_id
        self.max_pages = max_pages
        self.use_playwright = use_playwright
        self.verbose = verbose
        
        self.rate_limiter = RateLimiter(rate_limit)
        self.robots_checker = RobotsChecker()
        self.session = get_session()
        
        self.visited_urls: Set[str] = set()
        self.pages_crawled = 0
        
        # Playwright browser (lazy init)
        self._playwright = None
        self._browser = None
        self._page = None
    
    def _init_playwright(self):
        """Initialize Playwright browser if needed."""
        if self._browser is not None:
            return
        
        try:
            from playwright.sync_api import sync_playwright
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=True)
            self._page = self._browser.new_page()
            self._page.set_extra_http_headers({'User-Agent': USER_AGENT})
            logger.info("Playwright browser initialized")
        except ImportError:
            logger.warning("Playwright not installed, falling back to requests")
            self.use_playwright = False
        except Exception as e:
            logger.error(f"Failed to initialize Playwright: {e}")
            self.use_playwright = False
    
    def _cleanup_playwright(self):
        """Clean up Playwright resources."""
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
    
    def _fetch_page(self, url: str) -> Tuple[Optional[str], Optional[str], int]:
        """
        Fetch a page and return (html_content, final_url, status_code).
        """
        try:
            if self.use_playwright:
                return self._fetch_with_playwright(url)
            else:
                return self._fetch_with_requests(url)
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None, url, 0
    
    def _fetch_with_requests(self, url: str) -> Tuple[Optional[str], str, int]:
        """Fetch page using requests."""
        try:
            response = self.session.get(
                url,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                allow_redirects=True
            )
            
            # Check content type
            content_type = response.headers.get('Content-Type', '')
            if 'text/html' not in content_type and 'application/xhtml' not in content_type:
                logger.debug(f"Skipping non-HTML content at {url}: {content_type}")
                return None, response.url, response.status_code
            
            return response.text, response.url, response.status_code
            
        except requests.Timeout:
            logger.warning(f"Timeout fetching {url}")
            return None, url, 408
        except requests.RequestException as e:
            logger.warning(f"Request error for {url}: {e}")
            return None, url, 0
    
    def _fetch_with_playwright(self, url: str) -> Tuple[Optional[str], str, int]:
        """Fetch page using Playwright for JS rendering."""
        self._init_playwright()
        
        if not self._page:
            return self._fetch_with_requests(url)
        
        try:
            response = self._page.goto(url, wait_until='networkidle', timeout=30000)
            if response:
                return self._page.content(), self._page.url, response.status
            return None, url, 0
        except Exception as e:
            logger.warning(f"Playwright error for {url}: {e}")
            return None, url, 0
    
    def _extract_links(self, html: str, base_url: str) -> List[str]:
        """Extract and filter links from HTML."""
        links = []
        
        try:
            soup = BeautifulSoup(html, 'lxml')
            
            for a_tag in soup.find_all('a', href=True):
                href = a_tag['href']
                normalized = normalize_url(href, base_url)
                
                if not normalized:
                    continue
                
                # Skip already visited
                if normalized in self.visited_urls:
                    continue
                
                # Only same registrable domain
                if not is_same_registrable_domain(normalized, self.target_domain):
                    continue
                
                # Only HTML pages
                if not is_html_url(normalized):
                    continue
                
                links.append(normalized)
            
        except Exception as e:
            logger.error(f"Error extracting links from {base_url}: {e}")
        
        return links
    
    def _prioritize_links(self, links: List[str]) -> List[str]:
        """Sort links by priority (career-related first)."""
        priority = []
        normal = []
        
        for link in links:
            if url_has_priority_keywords(link):
                priority.append(link)
            else:
                normal.append(link)
        
        return priority + normal
    
    def crawl(
        self,
        seed_urls: List[str],
        page_callback: Optional[Callable[[str, str, str], None]] = None
    ) -> int:
        """
        Perform BFS crawl starting from seed URLs.
        
        Args:
            seed_urls: Initial URLs to start crawling from
            page_callback: Optional callback(url, final_url, html) for each page
            
        Returns:
            Number of pages crawled
        """
        logger.info(f"Starting crawl of {self.target_domain} with {len(seed_urls)} seed URLs")
        
        # Initialize queue with seed URLs
        queue = deque()
        
        for url in seed_urls:
            normalized = normalize_url(url)
            if normalized and normalized not in self.visited_urls:
                if is_same_registrable_domain(normalized, self.target_domain):
                    queue.append(normalized)
                    self.visited_urls.add(normalized)
        
        try:
            while queue and self.pages_crawled < self.max_pages:
                url = queue.popleft()
                
                # Check robots.txt
                if not self.robots_checker.can_fetch(url):
                    logger.debug(f"Blocked by robots.txt: {url}")
                    continue
                
                # Check if already in DB
                if self.db.url_exists(self.company_id, url):
                    logger.debug(f"Already crawled: {url}")
                    continue
                
                # Rate limit
                domain = get_full_domain(url)
                self.rate_limiter.wait(domain)
                
                # Fetch page
                if self.verbose:
                    logger.info(f"Crawling [{self.pages_crawled + 1}/{self.max_pages}]: {url}")
                
                html, final_url, status_code = self._fetch_page(url)
                
                # Store in DB
                self.db.add_source(
                    company_id=self.company_id,
                    url=url,
                    final_url=final_url,
                    status_code=status_code
                )
                
                self.pages_crawled += 1
                
                if html:
                    # Callback for processing
                    if page_callback:
                        page_callback(url, final_url or url, html)
                    
                    # Extract and queue new links
                    new_links = self._extract_links(html, final_url or url)
                    new_links = self._prioritize_links(new_links)
                    
                    for link in new_links:
                        if link not in self.visited_urls:
                            self.visited_urls.add(link)
                            queue.append(link)
                else:
                    if self.verbose:
                        logger.warning(f"No content from {url} (status: {status_code})")
            
            logger.info(f"Crawl complete for {self.target_domain}: {self.pages_crawled} pages")
            
        finally:
            self._cleanup_playwright()
        
        return self.pages_crawled

