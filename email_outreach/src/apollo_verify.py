"""
Apollo.io API integration for email verification.
"""

import os
import logging
from typing import Optional, Dict, List, Tuple
import requests
from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

logger = logging.getLogger(__name__)

APOLLO_API_KEY = os.getenv('APOLLO_API_KEY')
APOLLO_API_URL = 'https://api.apollo.io/v1/mixed_people/search'


class ApolloVerifier:
    """Verify emails using Apollo.io API."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or APOLLO_API_KEY
        if not self.api_key:
            raise ValueError("APOLLO_API_KEY not set")
        self.headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key
        }
    
    def search_person(
        self,
        name: Optional[str] = None,
        email: Optional[str] = None,
        organization_names: Optional[List[str]] = None
    ) -> Tuple[bool, Optional[Dict], str]:
        """
        Search for a person in Apollo.io.
        
        Args:
            name: Person's name (e.g., "Andrea Vogel")
            email: Email address to verify
            organization_names: List of organization names to search in
            
        Returns:
            Tuple of (found, person_data, message)
        """
        if not name and not email:
            return False, None, "Need name or email to search"
        
        payload = {
            "api_key": self.api_key,
        }
        
        if name:
            payload["q"] = name
        
        if email:
            payload["email"] = email
        
        if organization_names:
            payload["organization_names"] = organization_names
        
        try:
            response = requests.post(
                APOLLO_API_URL,
                json=payload,
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            
            data = response.json()
            people = data.get('people', [])
            
            if people:
                # Check if email matches if provided
                if email:
                    for person in people:
                        # Apollo.io may return emails in 'email' or 'emails' field
                        person_emails = []
                        if 'emails' in person and isinstance(person['emails'], list):
                            person_emails = [e.get('email', '') if isinstance(e, dict) else str(e) for e in person['emails'] if e]
                        elif 'email' in person:
                            email_val = person['email']
                            if isinstance(email_val, list):
                                person_emails = [e.get('email', '') if isinstance(e, dict) else str(e) for e in email_val if e]
                            elif email_val:
                                person_emails = [str(email_val)]
                        
                        # Also check direct email field (string)
                        if 'email' in person and isinstance(person['email'], str):
                            person_emails.append(person['email'])
                        
                        # Normalize and check
                        person_emails = [e.lower().strip() for e in person_emails if e]
                        
                        # Check if email matches
                        if email.lower() in person_emails:
                            return True, person, f"Found in Apollo.io: {person.get('name', 'Unknown')}"
                    
                    # Person found but email doesn't match
                    return False, people[0], f"Person found but email doesn't match"
                
                # Name search only
                return True, people[0], f"Found in Apollo.io: {people[0].get('name', 'Unknown')}"
            else:
                return False, None, "Not found in Apollo.io"
                
        except requests.exceptions.HTTPError as e:
            # Common when API key/plan/payload isn't accepted; don't spam stderr for each email.
            return False, None, f"Apollo HTTP error: {e}"
        except requests.exceptions.RequestException as e:
            logger.debug(f"Apollo.io API error: {e}")
            return False, None, f"Apollo request error: {str(e)}"
        except Exception as e:
            logger.debug(f"Unexpected error in Apollo.io search: {e}")
            return False, None, f"Error: {str(e)}"
    
    def verify_email(
        self,
        email: str,
        person_name: Optional[str] = None,
        company_name: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Verify if an email belongs to a real person using Apollo.io.
        
        Args:
            email: Email address to verify
            person_name: Optional person name for better matching
            company_name: Optional company name for better matching
            
        Returns:
            Tuple of (is_valid, reason)
        """
        organization_names = [company_name] if company_name else None
        
        found, person_data, message = self.search_person(
            name=person_name,
            email=email,
            organization_names=organization_names
        )
        
        if found and person_data:
            # Additional check: verify email matches
            person_emails = []
            # Apollo.io may return emails in 'email' or 'emails' field
            if 'emails' in person_data and isinstance(person_data['emails'], list):
                person_emails = [e.get('email', '') if isinstance(e, dict) else str(e) for e in person_data['emails'] if e]
            elif 'email' in person_data:
                email_val = person_data['email']
                if isinstance(email_val, list):
                    person_emails = [e.get('email', '') if isinstance(e, dict) else str(e) for e in email_val if e]
                elif email_val:
                    person_emails = [str(email_val)]
            
            # Also check direct email field (string)
            if 'email' in person_data and isinstance(person_data['email'], str):
                person_emails.append(person_data['email'])
            
            # Normalize
            person_emails = [e.lower().strip() for e in person_emails if e]
            
            if email.lower() in person_emails:
                return True, f"Verified in Apollo.io: {message}"
            elif person_emails:
                # Person found but different email
                return False, f"Person found but email mismatch (found: {person_emails[0]})"
            else:
                # Person found but no email in Apollo
                return True, f"Person found in Apollo.io (no email listed)"
        
        return False, message
