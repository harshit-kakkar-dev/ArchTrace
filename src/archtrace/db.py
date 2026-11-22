import os
import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = os.getenv("ARCHTRACE_DB_PATH", "archtrace.db")


def get_connection(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    """Initializes all ArchTrace tables if they do not already exist."""
    conn = get_connection(db_path)
    cur = conn.cursor()

    # 1. Cross-platform contributor identity resolution
    cur.execute("""
        CREATE TABLE IF NOT EXISTS contributors (
            canonical_id TEXT PRIMARY KEY,
            display_name TEXT,
            github_handle TEXT,
            discourse_handle TEXT,
            mailing_list_email TEXT,
            confidence REAL
        )
    """)

    # 2. Incremental ingestion state (SHA-256 hash avoids reprocessing unchanged posts)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ingested_posts (
            post_uid TEXT PRIMARY KEY,
            thread_url TEXT,
            author_canonical_id TEXT,
            created_at TEXT,
            content_hash TEXT
        )
    """)

    # 3. Extracted architectural decisions & rejected alternatives
    cur.execute("""
        CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_url TEXT,
            title TEXT,
            final_decision TEXT,
            rationale TEXT,
            rejected_alternatives_json TEXT,
            affected_files_json TEXT,
            affected_symbols_json TEXT,
            participants_json TEXT,
            status TEXT DEFAULT 'ACTIVE',
            updated_at TEXT
        )
    """)

    # 4. File move/rename lineage discovered via `git log --follow`
    cur.execute("""
        CREATE TABLE IF NOT EXISTS file_renames (
            old_path TEXT PRIMARY KEY,
            new_path TEXT,
            detected_at TEXT
        )
    """)

    # 5. Self-improving PR episodic memory (records maintainer overrides/confirmations)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pr_feedback_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            decision_id INTEGER,
            pr_identifier TEXT,
            feedback_type TEXT,
            maintainer_note TEXT,
            created_at TEXT
        )
    """)

    # 6. Warning fingerprint memory for repeat-PR merge gating
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pr_warnings (
            fingerprint TEXT PRIMARY KEY,
            first_pr_number TEXT,
            first_pr_url TEXT,
            decision_title TEXT,
            target_file TEXT,
            status TEXT DEFAULT 'WARNED',
            override_discussion_url TEXT,
            override_by TEXT,
            override_reason TEXT,
            created_at TEXT
        )
    """)

    conn.commit()
    conn.close()
