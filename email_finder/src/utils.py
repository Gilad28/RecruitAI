"""
Utility functions for the Email Finder.
Domain handling, URL normalization, robots.txt parsing, rate limiting.
"""

import re
import time
import logging
from urllib.parse import urlparse, urljoin
from urllib.robotparser import RobotFileParser
from typing import Optional, Set, Dict
from functools import lru_cache

import tldextract
import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Default User-Agent
USER_AGENT = "RecruitEmailFinder/1.0 (+https://github.com/recruit-email-finder; respects-robots.txt)"

# Request timeouts
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 20

# Social/news/wiki sites to exclude when discovering domains
EXCLUDED_DOMAINS = {
    'linkedin.com', 'facebook.com', 'twitter.com', 'x.com', 'instagram.com',
    'youtube.com', 'tiktok.com', 'pinterest.com', 'reddit.com', 'medium.com',
    'wikipedia.org', 'wikimedia.org', 'github.com', 'gitlab.com', 'bitbucket.org',
    'glassdoor.com', 'indeed.com', 'ziprecruiter.com', 'monster.com', 'careerbuilder.com',
    'crunchbase.com', 'bloomberg.com', 'reuters.com', 'forbes.com', 'businessinsider.com',
    'techcrunch.com', 'venturebeat.com', 'wired.com', 'theverge.com', 'cnn.com',
    'bbc.com', 'nytimes.com', 'wsj.com', 'ft.com', 'washingtonpost.com',
    'yelp.com', 'trustpilot.com', 'g2.com', 'capterra.com',
    'amazon.com', 'apple.com', 'google.com', 'bing.com', 'yahoo.com',
    'cloudflare.com', 'godaddy.com', 'squarespace.com', 'wix.com', 'wordpress.com',
}

# Paths that are likely to contain recruiting information
PRIORITY_PATH_KEYWORDS = {
    'careers', 'career', 'jobs', 'job', 'join', 'talent', 'students', 'student',
    'intern', 'internship', 'early-careers', 'earlycareers', 'university',
    'campus', 'contact', 'about', 'team', 'people', 'hiring', 'work-with-us',
    'opportunities', 'openings', 'apply', 'recruit', 'recruiting', 'newgrad',
    'graduates', 'employment'
}


class RateLimiter:
    """Rate limiter per domain."""
    
    def __init__(self, default_delay: float = 1.0):
        self.default_delay = default_delay
        self._last_request: Dict[str, float] = {}
    
    def wait(self, domain: str):
        """Wait if necessary to respect rate limit for domain."""
        now = time.time()
        last = self._last_request.get(domain, 0)
        elapsed = now - last
        
        if elapsed < self.default_delay:
            sleep_time = self.default_delay - elapsed
            logger.debug(f"Rate limiting: sleeping {sleep_time:.2f}s for {domain}")
            time.sleep(sleep_time)
        
        self._last_request[domain] = time.time()


class RobotsChecker:
    """Robots.txt checker with caching."""
    
    def __init__(self, user_agent: str = USER_AGENT):
        self.user_agent = user_agent
        self._parsers: Dict[str, RobotFileParser] = {}
        self._failed_domains: Set[str] = set()
    
    def can_fetch(self, url: str) -> bool:
        """Check if URL can be fetched according to robots.txt."""
        parsed = urlparse(url)
        domain = f"{parsed.scheme}://{parsed.netloc}"
        
        if domain in self._failed_domains:
            # Couldn't fetch robots.txt, allow by default
            return True
        
        if domain not in self._parsers:
            self._load_robots(domain)
        
        if domain in self._failed_domains:
            return True
        
        parser = self._parsers.get(domain)
        if parser:
            return parser.can_fetch(self.user_agent, url)
        return True
    
    def _load_robots(self, domain: str):
        """Load and parse robots.txt for domain."""
        robots_url = f"{domain}/robots.txt"
        parser = RobotFileParser()
        parser.set_url(robots_url)
        
        try:
            # Manually fetch to handle errors better
            response = requests.get(
                robots_url,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                headers={'User-Agent': self.user_agent}
            )
            if response.status_code == 200:
                parser.parse(response.text.splitlines())
                self._parsers[domain] = parser
            else:
                # No robots.txt or error - allow all
                self._failed_domains.add(domain)
        except Exception as e:
            logger.debug(f"Could not fetch robots.txt for {domain}: {e}")
            self._failed_domains.add(domain)


def get_registrable_domain(url_or_domain: str) -> str:
    """
    Extract the registrable domain from a URL or domain string.
    e.g., 'jobs.company.com' -> 'company.com'
         'https://www.company.com/path' -> 'company.com'
    """
    # Handle URLs
    if '://' in url_or_domain:
        parsed = urlparse(url_or_domain)
        domain = parsed.netloc
    else:
        domain = url_or_domain
    
    # Remove port if present
    if ':' in domain:
        domain = domain.split(':')[0]
    
    extracted = tldextract.extract(domain)
    if extracted.domain and extracted.suffix:
        return f"{extracted.domain}.{extracted.suffix}"
    return domain


def get_full_domain(url: str) -> str:
    """Extract full domain (including subdomain) from URL."""
    parsed = urlparse(url)
    domain = parsed.netloc
    # Remove port if present
    if ':' in domain:
        domain = domain.split(':')[0]
    return domain.lower()


def is_same_registrable_domain(url: str, target_domain: str) -> bool:
    """Check if URL belongs to the same registrable domain."""
    url_domain = get_registrable_domain(url)
    target_reg = get_registrable_domain(target_domain)
    return url_domain.lower() == target_reg.lower()


def normalize_url(url: str, base_url: Optional[str] = None) -> Optional[str]:
    """
    Normalize a URL, optionally resolving against a base URL.
    Returns None if URL is invalid or should be skipped.
    """
    if not url:
        return None
    
    url = url.strip()
    
    # Skip non-HTTP URLs
    if url.startswith(('javascript:', 'mailto:', 'tel:', 'ftp:', '#', 'data:')):
        return None
    
    # Resolve relative URLs
    if base_url and not url.startswith(('http://', 'https://')):
        url = urljoin(base_url, url)
    
    # Ensure http/https
    if not url.startswith(('http://', 'https://')):
        return None
    
    # Parse and reconstruct to normalize
    parsed = urlparse(url)
    
    # Remove fragment
    normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    
    # Keep query string if present (but not fragments)
    if parsed.query:
        normalized += f"?{parsed.query}"
    
    # Remove trailing slash for consistency (except for root)
    if normalized.endswith('/') and parsed.path != '/':
        normalized = normalized.rstrip('/')
    
    return normalized


def is_html_url(url: str) -> bool:
    """Check if URL likely points to an HTML page."""
    parsed = urlparse(url)
    path = parsed.path.lower()
    
    # Skip known non-HTML extensions
    non_html_extensions = {
        '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
        '.zip', '.rar', '.gz', '.tar', '.7z',
        '.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.ico',
        '.mp3', '.mp4', '.avi', '.mov', '.wmv', '.flv',
        '.css', '.js', '.json', '.xml', '.rss', '.atom',
        '.woff', '.woff2', '.ttf', '.eot',
        '.exe', '.dmg', '.msi', '.apk', '.ipa'
    }
    
    for ext in non_html_extensions:
        if path.endswith(ext):
            return False
    
    return True


def url_has_priority_keywords(url: str) -> bool:
    """Check if URL path contains priority keywords."""
    parsed = urlparse(url)
    path = parsed.path.lower()
    return any(kw in path for kw in PRIORITY_PATH_KEYWORDS)


def is_excluded_domain(domain: str) -> bool:
    """Check if domain is a known social/news/wiki site to exclude."""
    reg_domain = get_registrable_domain(domain)
    return reg_domain.lower() in EXCLUDED_DOMAINS


def get_session(user_agent: str = USER_AGENT, max_retries: int = 2) -> requests.Session:
    """Create a configured requests session."""
    session = requests.Session()
    session.headers.update({
        'User-Agent': user_agent,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'DNT': '1',
        'Connection': 'keep-alive',
    })
    
    # Configure retries
    from urllib3.util.retry import Retry
    from requests.adapters import HTTPAdapter
    
    retry_strategy = Retry(
        total=max_retries,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET"],
        backoff_factor=1
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    return session


def clean_text(text: str) -> str:
    """Clean text by removing extra whitespace."""
    return ' '.join(text.split())


def extract_context(text: str, match_start: int, match_end: int, window: int = 150) -> str:
    """Extract context around a match in text."""
    start = max(0, match_start - window)
    end = min(len(text), match_end + window)
    context = text[start:end]
    
    # Clean up
    context = clean_text(context)
    
    # Add ellipsis if truncated
    if start > 0:
        context = "..." + context
    if end < len(text):
        context = context + "..."
    
    return context

