"""
Email extraction from HTML with de-obfuscation support.
Enhanced to find personal recruiter emails and extract recruiter names.
"""

import re
import html
import logging
from typing import List, Tuple, Set, Optional, Dict
from urllib.parse import unquote

from bs4 import BeautifulSoup

from .utils import get_registrable_domain, extract_context

logger = logging.getLogger(__name__)

# Email regex pattern - more strict
EMAIL_PATTERN = re.compile(
    r'\b([a-zA-Z][a-zA-Z0-9._%+-]{2,})@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b',
    re.IGNORECASE
)

# Pattern for personal email local parts (firstname.lastname, etc.)
PERSONAL_EMAIL_PATTERNS = [
    re.compile(r'^[a-z]{2,}[._-][a-z]{2,}$', re.I),      # john.smith, john_smith, john-smith
    re.compile(r'^[a-z][._-][a-z]{2,}$', re.I),          # j.smith, j_smith
    re.compile(r'^[a-z]{2,}[._-][a-z]$', re.I),          # john.s
    re.compile(r'^[a-z]{2,}[._-][a-z]{2,}[._-][a-z]+$', re.I),  # john.middle.smith
]

# Invalid/garbage local parts to filter out
INVALID_LOCAL_PARTS = {
    # Common words that get parsed as emails
    'is', 'at', 'page', 'www', 'http', 'https', 'com', 'org', 'net',
    'the', 'a', 'an', 'or', 'and', 'to', 'of', 'in', 'on', 'for', 'be',
    'domain', 'email', 'mail', 'address', 'example', 'test', 'site',
    'null', 'undefined', 'none', 'na', 'our', 'your', 'their', 'its',
    # Too short
    'i', 'me', 'we', 'us', 'it', 'he', 'she', 'no', 'yes', 'ok',
    # More garbage
    'internal', 'external', 'successful', 'most', 'all', 'new', 'old',
    'first', 'last', 'next', 'prev', 'previous', 'current', 'other',
    'official', 'only', 'please', 'note', 'from', 'any', 'about',
    'user', 'ops', 'communications', 'internal.c', 'internal.communications',
}

# Functional/generic email prefixes to deprioritize (not personal)
FUNCTIONAL_EMAIL_PREFIXES = {
    # Support/help
    'support', 'help', 'helpdesk', 'assistance', 'customerservice', 'cs',
    # Generic contact
    'info', 'contact', 'hello', 'hi', 'general', 'inquiries', 'inquiry',
    # Legal/compliance
    'privacy', 'legal', 'compliance', 'gdpr', 'dmca', 'copyright',
    # Security
    'security', 'abuse', 'spam', 'phishing', 'fraud',
    # Press/PR
    'press', 'media', 'pr', 'communications', 'comms', 'news',
    # Sales/marketing
    'sales', 'marketing', 'advertising', 'ads', 'partnerships', 'partners',
    # Finance
    'billing', 'payment', 'payments', 'invoice', 'invoices', 'accounts', 'finance', 'accounting',
    # Technical
    'admin', 'webmaster', 'postmaster', 'hostmaster', 'root', 'sysadmin',
    # Automated
    'noreply', 'no-reply', 'donotreply', 'do-not-reply', 'mailer', 'daemon', 'bounce',
    'notifications', 'notification', 'alerts', 'alert', 'updates', 'newsletter',
    'unsubscribe', 'subscribe', 'feedback', 'survey',
    # Generic HR (not personal)
    'jobs', 'careers', 'applications', 'apply', 'resume', 'resumes', 'cv',
    # Accommodations
    'accommodations', 'accessibility',
    # Teams
    'team', 'teams', 'office', 'reception',
    # Investor
    'investor', 'investors', 'ir',
    # Executive
    'exec', 'executive', 'ceo', 'cfo', 'cto', 'coo',
}

# Keywords that indicate a recruiting-related PERSONAL email
RECRUITER_NAME_CONTEXTS = [
    'recruiter', 'recruiting', 'talent', 'talent acquisition',
    'university recruiting', 'campus recruiting', 'technical recruiter',
    'sourcer', 'hiring', 'people team', 'people ops', 'hr manager',
]

# Common recruiter/HR titles - ONLY used in LinkedIn search, not for website extraction
# Website extraction is too unreliable for finding personal names
RECRUITER_TITLES = {
    'recruiter', 'university recruiter', 'campus recruiter', 'technical recruiter',
    'senior recruiter', 'lead recruiter', 'staff recruiter',
    'recruiting manager', 'hiring manager',
    'talent partner', 'sourcer', 'talent sourcer',
}

# Words that are NOT valid first/last names
INVALID_NAME_WORDS = {
    # Job functions/departments
    'internal', 'external', 'communications', 'operations', 'ops',
    'successful', 'stripes', 'user', 'most', 'all', 'new', 'best',
    'team', 'group', 'department', 'division', 'unit',
    'services', 'solutions', 'systems', 'support', 'help',
    'hr', 'it', 'legal', 'finance', 'marketing', 'sales', 'engineering',
    'product', 'design', 'data', 'analytics', 'security', 'compliance',
    # Common generic words
    'the', 'and', 'for', 'our', 'your', 'their', 'this', 'that',
    'apply', 'contact', 'join', 'work', 'careers', 'jobs',
    'global', 'local', 'regional', 'national', 'international',
    'senior', 'junior', 'lead', 'head', 'chief', 'director', 'manager',
    'vp', 'vice', 'president', 'executive', 'officer',
    # Stripe-specific false positives
    'stripes', 'stripe',
}

# Name pattern for extracting recruiter names
NAME_PATTERN = re.compile(
    r'\b([A-Z][a-z]{1,15})\s+([A-Z][a-z]{1,15})\b'
)

# Common email patterns to try when we have a name
EMAIL_PATTERNS_FROM_NAME = [
    '{first}.{last}',      # john.smith
    '{first}_{last}',      # john_smith
    '{first}{last}',       # johnsmith
    '{f}{last}',           # jsmith
    '{first}.{l}',         # john.s
    '{first}-{last}',      # john-smith
    '{f}.{last}',          # j.smith
    '{last}.{first}',      # smith.john
]


class EmailExtractor:
    """Extract emails from HTML content with de-obfuscation."""
    
    def __init__(self, target_domain: str):
        self.target_domain = get_registrable_domain(target_domain).lower()
        self.found_recruiter_names: List[Dict] = []
    
    def _is_valid_local_part(self, local_part: str) -> bool:
        """Check if local part is valid (not garbage)."""
        lp = local_part.lower().strip()
        
        # Too short - personal emails should be at least 4 chars
        if len(lp) < 4:
            return False
        
        # Too long
        if len(lp) > 64:
            return False
        
        # Known garbage words
        if lp in INVALID_LOCAL_PARTS:
            return False
        
        # Check parts separated by dots
        parts = lp.replace('_', '.').replace('-', '.').split('.')
        for part in parts:
            if part in INVALID_LOCAL_PARTS:
                return False
            if part in INVALID_NAME_WORDS:
                return False
        
        # Contains 'www' or looks like URL fragment
        if 'www' in lp or 'http' in lp:
            return False
        
        # Starts or ends with special chars
        if lp[0] in '._-' or lp[-1] in '._-':
            return False
        
        # Multiple consecutive special chars
        if '..' in lp or '__' in lp or '--' in lp:
            return False
        
        # Must start with a letter
        if not lp[0].isalpha():
            return False
        
        return True
    
    def _is_personal_email(self, local_part: str) -> bool:
        """Check if email looks like a personal email (firstname.lastname pattern)."""
        lp = local_part.lower()
        
        # Check against personal patterns
        for pattern in PERSONAL_EMAIL_PATTERNS:
            if pattern.match(lp):
                return True
        
        return False
    
    def _is_functional_email(self, local_part: str) -> bool:
        """Check if email is a functional/generic email."""
        lp = local_part.lower()
        
        # Check exact match
        if lp in FUNCTIONAL_EMAIL_PREFIXES:
            return True
        
        # Check if starts with functional prefix
        for prefix in FUNCTIONAL_EMAIL_PREFIXES:
            if lp.startswith(prefix):
                return True
        
        return False
    
    def _deobfuscate(self, text: str) -> str:
        """Remove common email obfuscation techniques."""
        text = html.unescape(text)
        
        try:
            text = unquote(text)
        except Exception:
            pass
        
        # Common obfuscation replacements
        replacements = [
            (r'\s*\[\s*at\s*\]\s*', '@'),
            (r'\s*\(\s*at\s*\)\s*', '@'),
            (r'\s*\{\s*at\s*\}\s*', '@'),
            (r'\s*\[\s*dot\s*\]\s*', '.'),
            (r'\s*\(\s*dot\s*\)\s*', '.'),
            (r'\s*\{\s*dot\s*\}\s*', '.'),
            (r'\s*&#64;\s*', '@'),
            (r'\s*&#x40;\s*', '@'),
            (r'\s*&#46;\s*', '.'),
        ]
        
        for pattern, repl in replacements:
            text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
        
        return text
    
    def _extract_mailto_emails(self, soup: BeautifulSoup) -> List[Tuple[str, str, bool]]:
        """Extract emails from mailto: links. Returns (email, context, is_mailto)."""
        emails = []
        
        for a_tag in soup.find_all('a', href=True):
            href = a_tag.get('href', '')
            
            if href.lower().startswith('mailto:'):
                email_part = href[7:]
                if '?' in email_part:
                    email_part = email_part.split('?')[0]
                
                email_part = self._deobfuscate(email_part).strip()
                
                context = ''
                parent = a_tag.parent
                if parent:
                    context = parent.get_text(separator=' ', strip=True)[:300]
                if not context:
                    context = a_tag.get_text(strip=True)
                
                match = EMAIL_PATTERN.search(email_part)
                if match:
                    emails.append((match.group(0), context, True))
        
        return emails
    
    def _extract_recruiter_names(self, soup: BeautifulSoup) -> List[Dict]:
        """
        Extract recruiter/HR names from the page.
        NOTE: Website extraction is unreliable. This is disabled by default.
        Use LinkedIn search via Brave API for better results.
        """
        # DISABLED: Website extraction of names is too unreliable
        # Companies rarely list recruiter names in a parseable format
        return []
        
        return recruiters
    
    def _generate_email_guesses(self, first_name: str, last_name: str, domain: str) -> List[str]:
        """Generate likely email addresses from a name."""
        first = first_name.lower()
        last = last_name.lower()
        f = first[0]
        l = last[0]
        
        guesses = []
        for pattern in EMAIL_PATTERNS_FROM_NAME:
            email = pattern.format(first=first, last=last, f=f, l=l)
            guesses.append(f"{email}@{domain}")
        
        return guesses
    
    def _is_valid_email_domain(self, email: str) -> bool:
        """Check if email belongs to target domain."""
        if '@' not in email:
            return False
        
        email_domain = email.split('@')[1].lower()
        email_reg = get_registrable_domain(email_domain)
        
        return email_reg.lower() == self.target_domain.lower()
    
    def extract_emails(self, html_content: str, source_url: str) -> List[dict]:
        """Extract all emails from HTML content."""
        seen_emails: Set[str] = set()
        results = []
        
        try:
            soup = BeautifulSoup(html_content, 'lxml')
            
            # Extract recruiter names for potential email guessing
            recruiter_names = self._extract_recruiter_names(soup)
            self.found_recruiter_names.extend(recruiter_names)
            
            # Log found recruiters
            for r in recruiter_names:
                logger.info(f"Found recruiter: {r['full_name']} ({r['title']})")
            
            # Extract emails from mailto links (more reliable)
            mailto_emails = self._extract_mailto_emails(soup)
            
            # Process found emails
            for email, context, is_mailto in mailto_emails:
                email = email.lower().strip()
                
                if email in seen_emails:
                    continue
                
                if not self._is_valid_email_domain(email):
                    continue
                
                local_part = email.split('@')[0]
                
                # Filter out garbage
                if not self._is_valid_local_part(local_part):
                    logger.debug(f"Skipping invalid email: {email}")
                    continue
                
                is_personal = self._is_personal_email(local_part)
                is_functional = self._is_functional_email(local_part)
                
                seen_emails.add(email)
                results.append({
                    'email': email,
                    'context': context[:500],
                    'source_url': source_url,
                    'is_personal': is_personal,
                    'is_functional': is_functional,
                    'is_mailto': is_mailto,
                })
            
            # Generate email guesses from found recruiter names
            for recruiter in recruiter_names:
                guesses = self._generate_email_guesses(
                    recruiter['first_name'],
                    recruiter['last_name'],
                    self.target_domain
                )
                
                for email in guesses:
                    if email not in seen_emails:
                        seen_emails.add(email)
                        results.append({
                            'email': email,
                            'context': f"Generated from recruiter name: {recruiter['full_name']} ({recruiter['title']})",
                            'source_url': source_url,
                            'is_personal': True,
                            'is_functional': False,
                            'is_mailto': False,
                            'is_generated': True,
                            'recruiter_name': recruiter['full_name'],
                        })
            
            if results:
                logger.info(f"Extracted {len(results)} emails from {source_url}")
            
        except Exception as e:
            logger.error(f"Error extracting emails from {source_url}: {e}")
        
        return results
    
    def get_found_recruiters(self) -> List[Dict]:
        """Return all recruiter names found during extraction."""
        return self.found_recruiter_names
