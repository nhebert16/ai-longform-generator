"""
db_posting_helpers.py — Add these functions to your existing db.py

Copy the log_platform_post() function into your db.py file.
"""

import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path("output/pipeline.db")


def log_platform_post(job_id: int, platform: str, status: str, 
                      post_id: str = None, url: str = None, error: str = None):
    """
    Log a platform posting attempt.
    
    Args:
        job_id: Video job ID
        platform: "tiktok", "instagram", or "youtube"
        status: "success", "pending", "error"
        post_id: Platform-specific post/video ID
        url: Direct link to the post
        error: Error message (if status is "error")
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        posted_at = datetime.now().isoformat() if status == "success" else None
        
        cursor.execute("""
            INSERT INTO platform_posts
            (job_id, platform, status, post_id, url, error_message, posted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (job_id, platform, status, post_id, url, error, posted_at))
        
        conn.commit()
        conn.close()
        
        status_icon = "✓" if status == "success" else "✗"
        print(f"  [{status_icon}] Logged {platform} post for job {job_id}")
        
    except Exception as e:
        print(f"  [!] Failed to log platform post: {e}")


def get_platform_status(job_id: int) -> dict:
    """Get posting status across all platforms for a video."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT platform, status, post_id, url, error_message
            FROM platform_posts
            WHERE job_id = ?
            ORDER BY created_at DESC
        """, (job_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        result = {}
        for platform, status, post_id, url, error in rows:
            result[platform] = {
                "status": status,
                "post_id": post_id,
                "url": url,
                "error": error
            }
        
        return result
    except Exception as e:
        print(f"[!] Failed to get platform status: {e}")
        return {}


if __name__ == "__main__":
    # Example usage
    log_platform_post(1, "tiktok", "success", "abc123", "https://tiktok.com/video/abc123")
    log_platform_post(1, "instagram", "error", error="Upload timeout")
    
    status = get_platform_status(1)
    print(status)
