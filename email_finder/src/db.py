"""
Database operations for the Email Finder.
SQLite database with tables: companies, sources, emails, results.
"""

import sqlite3
from datetime import datetime
from typing import Optional, List, Tuple, Any
from contextlib import contextmanager


class EmailFinderDB:
    """SQLite database manager for email finder."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()
    
    @contextmanager
    def _get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def _init_db(self):
        """Initialize database tables."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Companies table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS companies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_name TEXT NOT NULL,
                    domain TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            
            # Sources table (crawled pages)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_id INTEGER NOT NULL,
                    url TEXT NOT NULL,
                    final_url TEXT,
                    status_code INTEGER,
                    fetched_at TEXT,
                    html_path TEXT,
                    FOREIGN KEY (company_id) REFERENCES companies(id)
                )
            """)
            
            # Emails table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS emails (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_id INTEGER NOT NULL,
                    email TEXT NOT NULL,
                    score REAL DEFAULT 0,
                    label TEXT DEFAULT 'unknown',
                    source_url TEXT,
                    context TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (company_id) REFERENCES companies(id)
                )
            """)
            
            # Results table (best emails per company)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_id INTEGER NOT NULL,
                    best_email_id INTEGER,
                    backup_email_ids TEXT,
                    confidence REAL DEFAULT 0,
                    notes TEXT,
                    FOREIGN KEY (company_id) REFERENCES companies(id),
                    FOREIGN KEY (best_email_id) REFERENCES emails(id)
                )
            """)
            
            # Create indexes for better query performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sources_company ON sources(company_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_emails_company ON emails(company_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_emails_email ON emails(email)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_results_company ON results(company_id)")
    
    def add_company(self, company_name: str, domain: Optional[str] = None) -> int:
        """Add a new company and return its ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO companies (company_name, domain, created_at) VALUES (?, ?, ?)",
                (company_name, domain, datetime.utcnow().isoformat())
            )
            return cursor.lastrowid
    
    def update_company_domain(self, company_id: int, domain: str):
        """Update a company's domain."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE companies SET domain = ? WHERE id = ?",
                (domain, company_id)
            )
    
    def get_company(self, company_id: int) -> Optional[sqlite3.Row]:
        """Get a company by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM companies WHERE id = ?", (company_id,))
            return cursor.fetchone()
    
    def add_source(self, company_id: int, url: str, final_url: Optional[str] = None,
                   status_code: Optional[int] = None, html_path: Optional[str] = None) -> int:
        """Add a crawled source page."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO sources (company_id, url, final_url, status_code, fetched_at, html_path)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (company_id, url, final_url, status_code, datetime.utcnow().isoformat(), html_path)
            )
            return cursor.lastrowid
    
    def url_exists(self, company_id: int, url: str) -> bool:
        """Check if a URL has already been crawled for a company."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM sources WHERE company_id = ? AND url = ?",
                (company_id, url)
            )
            return cursor.fetchone() is not None
    
    def add_email(self, company_id: int, email: str, score: float = 0,
                  label: str = 'unknown', source_url: Optional[str] = None,
                  context: Optional[str] = None) -> int:
        """Add a found email."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO emails (company_id, email, score, label, source_url, context, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (company_id, email.lower(), score, label, source_url, context, datetime.utcnow().isoformat())
            )
            return cursor.lastrowid
    
    def email_exists(self, company_id: int, email: str) -> bool:
        """Check if an email already exists for a company (case-insensitive)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM emails WHERE company_id = ? AND LOWER(email) = LOWER(?)",
                (company_id, email)
            )
            return cursor.fetchone() is not None
    
    def get_company_emails(self, company_id: int) -> List[sqlite3.Row]:
        """Get all emails for a company, ordered by score descending."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM emails WHERE company_id = ? ORDER BY score DESC",
                (company_id,)
            )
            return cursor.fetchall()
    
    def update_email_score(self, email_id: int, score: float, label: str):
        """Update an email's score and label."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE emails SET score = ?, label = ? WHERE id = ?",
                (score, label, email_id)
            )
    
    def add_result(self, company_id: int, best_email_id: Optional[int],
                   backup_email_ids: str = '', confidence: float = 0,
                   notes: str = '') -> int:
        """Add a result entry for a company."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO results (company_id, best_email_id, backup_email_ids, confidence, notes)
                   VALUES (?, ?, ?, ?, ?)""",
                (company_id, best_email_id, backup_email_ids, confidence, notes)
            )
            return cursor.lastrowid
    
    def get_email_by_id(self, email_id: int) -> Optional[sqlite3.Row]:
        """Get an email by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM emails WHERE id = ?", (email_id,))
            return cursor.fetchone()
    
    def get_all_results(self) -> List[Tuple[Any, ...]]:
        """Get all results with company and email details for export."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    c.company_name,
                    c.domain,
                    e.email as best_email,
                    e.score as best_score,
                    e.label as best_label,
                    e.source_url as best_source_url,
                    e.context as best_context,
                    r.backup_email_ids,
                    r.confidence,
                    r.notes
                FROM results r
                JOIN companies c ON r.company_id = c.id
                LEFT JOIN emails e ON r.best_email_id = e.id
                ORDER BY c.company_name
            """)
            return cursor.fetchall()
    
    def get_backup_emails(self, email_ids_str: str) -> List[str]:
        """Get backup email addresses from comma-separated IDs."""
        if not email_ids_str:
            return []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            email_ids = [int(x.strip()) for x in email_ids_str.split(',') if x.strip()]
            if not email_ids:
                return []
            placeholders = ','.join('?' * len(email_ids))
            cursor.execute(f"SELECT email FROM emails WHERE id IN ({placeholders})", email_ids)
            return [row['email'] for row in cursor.fetchall()]

