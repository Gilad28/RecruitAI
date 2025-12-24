"""
Email scoring and labeling for recruiting relevance.
"""

import re
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)

# Strong positive keywords for email local-part
EMAIL_POSITIVE_KEYWORDS = {
    'recruit', 'recruiting', 'recruiter', 'recruitment',
    'talent', 'talentacquisition', 'ta',
    'campus', 'university', 'univ', 'college',
    'earlycareers', 'early-careers', 'earlycareer',
    'intern', 'interns', 'internship', 'internships',
    'students', 'student', 'newgrad', 'newgrads',
    'graduates', 'graduate', 'grads',
    'hiring', 'hr', 'humanresources',
    'staffing', 'careers', 'career',
    'jobs', 'employment', 'people', 'peopleops',
}

# Positive keywords for context
CONTEXT_POSITIVE_KEYWORDS = {
    'recruit', 'recruiting', 'recruiter', 'recruitment',
    'apply', 'application', 'applications',
    'careers', 'career', 'jobs', 'job', 'position', 'positions',
    'intern', 'internship', 'internships',
    'university', 'campus', 'college', 'student', 'students',
    'talent', 'hiring', 'hire', 'join', 'opportunity', 'opportunities',
    'hiring manager', 'people team', 'hr team',
    'early career', 'new grad', 'graduate',
}

# Positive keywords for URL
URL_POSITIVE_KEYWORDS = {
    'careers', 'career', 'jobs', 'job',
    'join', 'join-us', 'work-with-us',
    'students', 'student', 'intern', 'internship',
    'early', 'graduate', 'campus', 'university',
    'talent', 'hiring', 'opportunities', 'team',
}

# Negative keywords
NEGATIVE_KEYWORDS = {
    'support', 'help', 'helpdesk',
    'privacy', 'legal', 'compliance',
    'press', 'media', 'pr', 'communications',
    'security', 'abuse', 'spam', 'phishing',
    'billing', 'payment', 'invoice', 'accounts',
    'sales', 'marketing', 'advertising',
    'noreply', 'no-reply', 'donotreply', 'do-not-reply',
    'mailer', 'daemon', 'postmaster', 'webmaster',
    'unsubscribe', 'newsletter', 'notification', 'notifications',
    'feedback', 'survey',
}

# Functional emails to score lower (but not discard)
FUNCTIONAL_EMAILS = {
    'info', 'contact', 'hello', 'general', 'admin',
}


class EmailScorer:
    """Score and label emails for recruiting relevance."""
    
    def __init__(self):
        # Score parameters
        self.email_keyword_weight = 6
        self.context_keyword_weight = 3
        self.url_keyword_weight = 2
        self.negative_email_weight = -6
        self.negative_context_weight = -3
        self.functional_email_weight = -2
        
        # Score thresholds for labeling
        self.recruiting_threshold = 7
        self.careers_threshold = 4
        
        # Score range for confidence calculation
        self.min_score = -10
        self.max_score = 15
    
    def _get_local_part(self, email: str) -> str:
        """Extract local part of email (before @)."""
        return email.split('@')[0].lower()
    
    def _normalize_text(self, text: str) -> str:
        """Normalize text for keyword matching."""
        return text.lower()
    
    def _contains_keywords(self, text: str, keywords: set) -> List[str]:
        """Find all matching keywords in text."""
        text = self._normalize_text(text)
        found = []
        for keyword in keywords:
            if keyword in text:
                found.append(keyword)
        return found
    
    def score_email(self, email: str, context: str, source_url: str) -> Tuple[float, str, str]:
        """
        Score an email for recruiting relevance.
        
        Args:
            email: Email address
            context: Surrounding text context
            source_url: URL where email was found
            
        Returns:
            Tuple of (score, label, notes)
        """
        score = 0.0
        notes = []
        
        local_part = self._get_local_part(email)
        context_lower = self._normalize_text(context)
        url_lower = self._normalize_text(source_url)
        
        # Check email local-part for positive keywords
        email_positives = self._contains_keywords(local_part, EMAIL_POSITIVE_KEYWORDS)
        if email_positives:
            score += self.email_keyword_weight * len(email_positives)
            notes.append(f"email keywords: {', '.join(email_positives)}")
        
        # Check context for positive keywords
        context_positives = self._contains_keywords(context_lower, CONTEXT_POSITIVE_KEYWORDS)
        if context_positives:
            # Cap context bonus to avoid over-weighting
            score += min(self.context_keyword_weight * len(context_positives), 9)
            notes.append(f"context keywords: {', '.join(context_positives[:5])}")
        
        # Check URL for positive keywords
        url_positives = self._contains_keywords(url_lower, URL_POSITIVE_KEYWORDS)
        if url_positives:
            score += self.url_keyword_weight * len(url_positives)
            notes.append(f"url keywords: {', '.join(url_positives)}")
        
        # Check for negative keywords in email
        email_negatives = self._contains_keywords(local_part, NEGATIVE_KEYWORDS)
        if email_negatives:
            score += self.negative_email_weight * len(email_negatives)
            notes.append(f"negative email: {', '.join(email_negatives)}")
        
        # Check for negative keywords in context
        context_negatives = self._contains_keywords(context_lower, NEGATIVE_KEYWORDS)
        if context_negatives:
            # Cap negative context impact
            score += max(self.negative_context_weight * len(context_negatives), -9)
            notes.append(f"negative context: {', '.join(context_negatives[:3])}")
        
        # Check for functional emails
        if local_part in FUNCTIONAL_EMAILS:
            score += self.functional_email_weight
            notes.append(f"functional email: {local_part}")
        
        # Determine label
        if score >= self.recruiting_threshold:
            label = 'recruiting'
        elif score >= self.careers_threshold:
            label = 'careers'
        else:
            label = 'unknown'
        
        notes_str = '; '.join(notes) if notes else ''
        
        return score, label, notes_str
    
    def calculate_confidence(self, score: float, source_url: str) -> float:
        """
        Calculate confidence score (0-1) for an email.
        
        Args:
            score: Raw score from score_email
            source_url: URL where email was found
            
        Returns:
            Confidence score between 0 and 1
        """
        # Normalize score to 0-1 range
        clamped = max(self.min_score, min(self.max_score, score))
        normalized = (clamped - self.min_score) / (self.max_score - self.min_score)
        
        # Boost if from careers-related URL
        url_lower = source_url.lower()
        url_boost = 0.1 if any(kw in url_lower for kw in ['careers', 'jobs', 'join', 'talent']) else 0
        
        confidence = min(1.0, normalized + url_boost)
        
        return round(confidence, 3)
    
    def rank_company_emails(
        self,
        emails: List[dict],
        max_backups: int = 3,
        backup_threshold_pct: float = 0.8
    ) -> Tuple[dict, List[dict], float, str]:
        """
        Rank emails for a company and select best + backups.
        
        Args:
            emails: List of email dicts with 'email', 'score', 'source_url', etc.
            max_backups: Maximum number of backup emails
            backup_threshold_pct: Include backups if score >= best * this
            
        Returns:
            Tuple of (best_email, backup_emails, confidence, notes)
        """
        if not emails:
            return None, [], 0.0, "No emails found"
        
        # Sort by score descending
        sorted_emails = sorted(emails, key=lambda x: x.get('score', 0), reverse=True)
        
        best = sorted_emails[0]
        best_score = best.get('score', 0)
        
        # Calculate confidence
        confidence = self.calculate_confidence(best_score, best.get('source_url', ''))
        
        # Select backups
        backups = []
        threshold = best_score * backup_threshold_pct
        
        for email in sorted_emails[1:]:
            email_score = email.get('score', 0)
            if email_score >= threshold or email_score >= self.careers_threshold:
                backups.append(email)
                if len(backups) >= max_backups:
                    break
        
        # Build notes
        notes_parts = [f"Best score: {best_score:.1f}"]
        if backups:
            notes_parts.append(f"{len(backups)} backups")
        if best.get('label') == 'recruiting':
            notes_parts.append("recruiting label")
        
        notes = "; ".join(notes_parts)
        
        return best, backups, confidence, notes

