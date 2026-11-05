"""
db_updates.py — Database schema additions for social media posting

Run once to add the new tables:
    python db_updates.py
"""

import sqlite3
from pathlib import Path

DB_PATH = Path("output/pipeline.db")


def update_schema():
    """Add platform_posts table to track uploads to each social network."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check if table already exists
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='platform_posts'"
    )
    if cursor.fetchone():
        print("[✓] platform_posts table already exists")
        conn.close()
        return

    # Create platform_posts table
    cursor.execute("""
        CREATE TABLE platform_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            post_id TEXT,
            url TEXT,
            error_message TEXT,
            posted_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (job_id) REFERENCES jobs(id)
        )
    """)
    
    # Create index for fast lookups
    cursor.execute("""
        CREATE INDEX idx_platform_posts_job_platform 
        ON platform_posts(job_id, platform)
    """)
    
    conn.commit()
    conn.close()
    print("[✓] platform_posts table created")


if __name__ == "__main__":
    update_schema()
