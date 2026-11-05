"""
db.py — SQLite database manager for tracking processed posts and video jobs
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = "reddit_videos.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_connection()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS processed_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reddit_post_id TEXT UNIQUE NOT NULL,
            subreddit TEXT NOT NULL,
            title TEXT,
            score INTEGER,
            word_count INTEGER,
            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS video_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reddit_post_id TEXT NOT NULL,
            status TEXT DEFAULT 'pending',  -- pending, scripted, tts_done, rendered, posted, failed
            script TEXT,
            hook TEXT,
            top_comment TEXT,
            audio_path TEXT,
            video_path TEXT,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (reddit_post_id) REFERENCES processed_posts(reddit_post_id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS post_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_job_id INTEGER NOT NULL,
            platform TEXT NOT NULL,         -- tiktok, instagram, youtube, facebook
            status TEXT DEFAULT 'pending',  -- pending, posted, failed
            platform_post_id TEXT,
            error_message TEXT,
            posted_at TIMESTAMP,
            FOREIGN KEY (video_job_id) REFERENCES video_jobs(id)
        )
    """)

    conn.commit()
    conn.close()
    print("[DB] Database initialized.")


def is_post_processed(reddit_post_id: str) -> bool:
    conn = get_connection()
    row = conn.execute(
        "SELECT id FROM processed_posts WHERE reddit_post_id = ?",
        (reddit_post_id,)
    ).fetchone()
    conn.close()
    return row is not None


def mark_post_processed(reddit_post_id: str, subreddit: str, title: str, score: int, word_count: int):
    conn = get_connection()
    conn.execute(
        """INSERT OR IGNORE INTO processed_posts
           (reddit_post_id, subreddit, title, score, word_count)
           VALUES (?, ?, ?, ?, ?)""",
        (reddit_post_id, subreddit, title, score, word_count)
    )
    conn.commit()
    conn.close()


def create_video_job(reddit_post_id: str) -> int:
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO video_jobs (reddit_post_id) VALUES (?)",
        (reddit_post_id,)
    )
    job_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return job_id


def update_job(job_id: int, **kwargs):
    """Update any fields on a video_jobs row."""
    kwargs["updated_at"] = datetime.now().isoformat()
    fields = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [job_id]
    conn = get_connection()
    conn.execute(f"UPDATE video_jobs SET {fields} WHERE id = ?", values)
    conn.commit()
    conn.close()


def log_platform_post(video_job_id: int, platform: str, status: str,
                       platform_post_id: str = None, error_message: str = None):
    conn = get_connection()
    conn.execute(
        """INSERT INTO post_log
           (video_job_id, platform, status, platform_post_id, error_message, posted_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (video_job_id, platform, status, platform_post_id, error_message,
         datetime.now().isoformat() if status == "posted" else None)
    )
    conn.commit()
    conn.close()


def get_pending_jobs():
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM video_jobs WHERE status = 'rendered'"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    init_db()
