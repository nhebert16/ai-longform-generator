"""
poster.py — Automated posting to TikTok, Instagram, and YouTube Shorts

Supports:
- TikTok API (official)
- Instagram Graph API
- YouTube Data API v3

Setup:
1. Get API credentials for each platform
2. Store in .env file:
   TIKTOK_ACCESS_TOKEN=xxx
   TIKTOK_VIDEO_ID=xxx (optional, for testing)
   INSTAGRAM_ACCESS_TOKEN=xxx
   INSTAGRAM_BUSINESS_ACCOUNT_ID=xxx
   YOUTUBE_API_KEY=xxx
   YOUTUBE_CLIENT_ID=xxx
   YOUTUBE_CLIENT_SECRET=xxx
   YOUTUBE_REFRESH_TOKEN=xxx

3. Install dependencies:
   pip install requests google-auth-oauthlib google-auth-httplib2 google-api-python-client
"""

import os
import json
import time
import requests
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# YouTube imports
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.exceptions import RefreshError
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

load_dotenv()

# ── CONSTANTS ──────────────────────────────────────────────────────

TIKTOK_API_BASE = "https://open.tiktokapis.com/v1"
INSTAGRAM_API_BASE = "https://graph.instagram.com/v18.0"
YOUTUBE_API_SCOPE = ["https://www.googleapis.com/auth/youtube.upload",
                     "https://www.googleapis.com/auth/youtube"]

# Platform credentials
TIKTOK_TOKEN = os.getenv("TIKTOK_ACCESS_TOKEN")
INSTAGRAM_TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN")
INSTAGRAM_ACCOUNT_ID = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

UPLOAD_DIR = Path(os.getenv("OUTPUT_DIR", "output")) / "videos"


# ── TIKTOK ─────────────────────────────────────────────────────────

def post_to_tiktok(video_path: str, caption: str, hashtags: List[str] = None) -> Optional[Dict]:
    """
    Post video to TikTok using TikTok API v1.
    
    Requires: TIKTOK_ACCESS_TOKEN in .env
    
    Returns: {
        "platform": "tiktok",
        "status": "success" | "error",
        "post_id": "...",  (if successful)
        "error": "...",     (if failed)
        "url": "https://www.tiktok.com/@username/video/xxx"
    }
    """
    if not TIKTOK_TOKEN:
        return {
            "platform": "tiktok",
            "status": "error",
            "error": "TIKTOK_ACCESS_TOKEN not set in .env"
        }

    try:
        video_path = Path(video_path)
        if not video_path.exists():
            return {
                "platform": "tiktok",
                "status": "error",
                "error": f"Video file not found: {video_path}"
            }

        # Step 1: Initialize upload (get upload URL)
        print("  [TikTok] Initializing upload...")
        init_url = f"{TIKTOK_API_BASE}/post/publish/action/init"
        
        headers = {
            "Authorization": f"Bearer {TIKTOK_TOKEN}",
            "Content-Type": "application/json"
        }
        
        init_data = {
            "source_info": {
                "source": "FILE_UPLOAD",
                "file_name": video_path.name
            }
        }
        
        init_resp = requests.post(init_url, json=init_data, headers=headers, timeout=30)
        if init_resp.status_code != 200:
            error_msg = init_resp.json().get("error", {}).get("message", "Unknown error")
            return {
                "platform": "tiktok",
                "status": "error",
                "error": f"Init failed: {error_msg} ({init_resp.status_code})"
            }
        
        upload_url = init_resp.json()["data"]["upload_url"]
        publish_id = init_resp.json()["data"]["publish_id"]

        # Step 2: Upload video file
        print(f"  [TikTok] Uploading video ({video_path.stat().st_size / 1e6:.1f}MB)...")
        with open(video_path, "rb") as f:
            upload_resp = requests.put(upload_url, data=f, timeout=120)
        
        if upload_resp.status_code not in [200, 201]:
            return {
                "platform": "tiktok",
                "status": "error",
                "error": f"Upload failed: {upload_resp.status_code}"
            }

        # Step 3: Publish video
        print("  [TikTok] Publishing video...")
        publish_url = f"{TIKTOK_API_BASE}/post/publish/action/publish"
        
        tags = " ".join([f"#{tag}" for tag in (hashtags or [])])
        description = f"{caption}\n\n{tags}" if tags else caption
        
        publish_data = {
            "publish_id": publish_id,
            "post_info": {
                "title": caption[:150],  # TikTok title limit
                "description": description[:2200]  # TikTok desc limit
            }
        }
        
        publish_resp = requests.post(publish_url, json=publish_data, headers=headers, timeout=30)
        if publish_resp.status_code != 200:
            error_msg = publish_resp.json().get("error", {}).get("message", "Unknown error")
            return {
                "platform": "tiktok",
                "status": "error",
                "error": f"Publish failed: {error_msg}"
            }
        
        post_data = publish_resp.json()["data"]
        post_id = post_data.get("video_id")
        
        print(f"  [✓] TikTok upload successful! Video ID: {post_id}")
        return {
            "platform": "tiktok",
            "status": "success",
            "post_id": post_id,
            "url": f"https://www.tiktok.com/video/{post_id}",
            "posted_at": datetime.now().isoformat()
        }

    except requests.exceptions.Timeout:
        return {
            "platform": "tiktok",
            "status": "error",
            "error": "Request timeout (video too large or network slow)"
        }
    except Exception as e:
        return {
            "platform": "tiktok",
            "status": "error",
            "error": f"Exception: {str(e)}"
        }


# ── INSTAGRAM ──────────────────────────────────────────────────────

def post_to_instagram(video_path: str, caption: str, hashtags: List[str] = None) -> Optional[Dict]:
    """
    Post Reel to Instagram using Instagram Graph API.
    
    Requires:
    - INSTAGRAM_ACCESS_TOKEN in .env
    - INSTAGRAM_BUSINESS_ACCOUNT_ID in .env
    
    Note: Instagram Reels require business account + proper permissions.
    
    Returns: {
        "platform": "instagram",
        "status": "success" | "error",
        "post_id": "...",  (if successful)
        "error": "...",     (if failed)
        "url": "https://instagram.com/p/xxx"
    }
    """
    if not INSTAGRAM_TOKEN or not INSTAGRAM_ACCOUNT_ID:
        return {
            "platform": "instagram",
            "status": "error",
            "error": "INSTAGRAM_ACCESS_TOKEN or INSTAGRAM_BUSINESS_ACCOUNT_ID not set in .env"
        }

    try:
        video_path = Path(video_path)
        if not video_path.exists():
            return {
                "platform": "instagram",
                "status": "error",
                "error": f"Video file not found: {video_path}"
            }

        # Instagram requires upload to a temporary container first
        print("  [Instagram] Creating media container...")
        
        tags = " ".join([f"#{tag}" for tag in (hashtags or [])])
        description = f"{caption}\n\n{tags}" if tags else caption
        
        # Step 1: Create media container
        container_url = f"{INSTAGRAM_API_BASE}/{INSTAGRAM_ACCOUNT_ID}/media"
        
        with open(video_path, "rb") as f:
            files = {"video_file": f}
            data = {
                "media_type": "REELS",
                "caption": description[:2200],
                "access_token": INSTAGRAM_TOKEN
            }
            
            print(f"  [Instagram] Uploading video ({video_path.stat().st_size / 1e6:.1f}MB)...")
            container_resp = requests.post(container_url, data=data, files=files, timeout=120)
        
        if container_resp.status_code not in [200, 201]:
            error_msg = container_resp.json().get("error", {}).get("message", "Unknown error")
            return {
                "platform": "instagram",
                "status": "error",
                "error": f"Container creation failed: {error_msg} ({container_resp.status_code})"
            }
        
        container_id = container_resp.json()["id"]

        # Step 2: Publish media
        print("  [Instagram] Publishing media...")
        publish_url = f"{INSTAGRAM_API_BASE}/{INSTAGRAM_ACCOUNT_ID}/media_publish"
        
        publish_data = {
            "creation_id": container_id,
            "access_token": INSTAGRAM_TOKEN
        }
        
        publish_resp = requests.post(publish_url, json=publish_data, timeout=30)
        if publish_resp.status_code not in [200, 201]:
            error_msg = publish_resp.json().get("error", {}).get("message", "Unknown error")
            return {
                "platform": "instagram",
                "status": "error",
                "error": f"Publish failed: {error_msg}"
            }
        
        post_id = publish_resp.json()["id"]
        
        print(f"  [✓] Instagram upload successful! Media ID: {post_id}")
        return {
            "platform": "instagram",
            "status": "success",
            "post_id": post_id,
            "url": f"https://instagram.com/p/{post_id}",
            "posted_at": datetime.now().isoformat()
        }

    except requests.exceptions.Timeout:
        return {
            "platform": "instagram",
            "status": "error",
            "error": "Request timeout (video too large or network slow)"
        }
    except Exception as e:
        return {
            "platform": "instagram",
            "status": "error",
            "error": f"Exception: {str(e)}"
        }


# ── YOUTUBE ────────────────────────────────────────────────────────

def _get_youtube_service():
    """Get authenticated YouTube service using OAuth 2.0."""
    creds = None
    token_path = Path("youtube_token.json")

    # Load cached token
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), YOUTUBE_API_SCOPE)

    # If no valid creds, refresh or prompt for auth
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError:
                creds = None

        if not creds:
            # First-time auth: redirect to browser
            flow = InstalledAppFlow.from_client_secrets_file(
                "youtube_secrets.json", YOUTUBE_API_SCOPE
            )
            creds = flow.run_local_server(port=8080)

        # Save token for reuse
        with open(token_path, "w") as token_file:
            token_file.write(creds.to_json())

    return build("youtube", "v3", credentials=creds)


def post_to_youtube(video_path: str, title: str, description: str, 
                    tags: List[str] = None, privacy_status: str = "public",
                    thumbnail_path: str = None,
                    playlist_id: str = None,
                    synthetic_media: bool = False) -> Optional[Dict]:
    """
    Upload video to YouTube.
    
    Requires:
    - youtube_secrets.json (OAuth 2.0 client credentials from Google Console)
    - First run: authenticate via browser → saves youtube_token.json
    
    Args:
        video_path: Path to MP4 video
        title: Video title (max 100 chars)
        description: Video description (max 5000 chars)
        tags: List of tags/keywords
        privacy_status: "public", "private", or "unlisted"
    
    Returns: {
        "platform": "youtube",
        "status": "success" | "error",
        "video_id": "...",  (if successful)
        "error": "...",      (if failed)
        "url": "https://youtube.com/watch?v=xxx"
    }
    """
    if not Path("youtube_secrets.json").exists():
        return {
            "platform": "youtube",
            "status": "error",
            "error": "youtube_secrets.json not found. Set up OAuth credentials in Google Console."
        }

    try:
        video_path = Path(video_path)
        if not video_path.exists():
            return {
                "platform": "youtube",
                "status": "error",
                "error": f"Video file not found: {video_path}"
            }

        service = _get_youtube_service()
        
        # Build metadata
        tags_list = tags or []
        body = {
            "snippet": {
                "categoryId": "24",  # Entertainment
                "title": title[:100],
                "description": description[:5000],
                "tags": tags_list[:50]  # YouTube limit
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False,
                "containsSyntheticMedia": synthetic_media,
            }
        }

        # Upload with resumable media
        if synthetic_media:
            print(f"  [YouTube] Synthetic media disclosure: enabled")
        print(f"  [YouTube] Uploading video ({video_path.stat().st_size / 1e6:.1f}MB)...")
        media = MediaFileUpload(str(video_path), chunksize=256*1024*1024, resumable=True)
        
        request = service.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media
        )

        # Execute with resume capability
        response = None
        while response is None:
            try:
                status, response = request.next_chunk()
                if status:
                    progress = int(status.progress() * 100)
                    print(f"    Upload progress: {progress}%")
            except HttpError as e:
                error_msg = json.loads(e.content).get("error", {}).get("message", str(e))
                return {
                    "platform": "youtube",
                    "status": "error",
                    "error": f"Upload failed: {error_msg}"
                }

        video_id = response["id"]
        print(f"  [✓] YouTube upload successful! Video ID: {video_id}")

        # Upload thumbnail if provided
        if thumbnail_path and Path(thumbnail_path).exists():
            try:
                print(f"  [YouTube] Uploading thumbnail...")
                thumb_media = MediaFileUpload(str(thumbnail_path), mimetype="image/jpeg")
                service.thumbnails().set(
                    videoId=video_id,
                    media_body=thumb_media
                ).execute()
                print(f"  [✓] Thumbnail uploaded")
            except HttpError as e:
                # Non-fatal — video is already up, thumbnail is a bonus
                print(f"  [!] Thumbnail upload failed: {e}")

        # Add to playlist if provided
        if playlist_id:
            try:
                print(f"  [YouTube] Adding to playlist {playlist_id}...")
                service.playlistItems().insert(
                    part="snippet",
                    body={
                        "snippet": {
                            "playlistId": playlist_id,
                            "resourceId": {
                                "kind": "youtube#video",
                                "videoId": video_id,
                            }
                        }
                    }
                ).execute()
                print(f"  [✓] Added to playlist")
            except HttpError as e:
                print(f"  [!] Playlist insert failed: {e}")

        return {
            "platform": "youtube",
            "status": "success",
            "video_id": video_id,
            "url": f"https://youtube.com/watch?v={video_id}",
            "posted_at": datetime.now().isoformat()
        }

    except Exception as e:
        return {
            "platform": "youtube",
            "status": "error",
            "error": f"Exception: {str(e)}"
        }


# ── ORCHESTRATOR ───────────────────────────────────────────────────

def post_to_all_platforms(video_path: str, caption: str, title: str = None,
                          hashtags: List[str] = None,
                          platforms: List[str] = None) -> Dict[str, Dict]:
    """
    Post video to multiple platforms concurrently.
    
    Args:
        video_path: Path to MP4 video
        caption: Post caption/description
        title: (YouTube only) Video title
        hashtags: List of hashtags
        platforms: ["tiktok", "instagram", "youtube"] (default: all)
    
    Returns: {
        "tiktok": { "status": "success", "post_id": "...", ... },
        "instagram": { "status": "success", "post_id": "...", ... },
        "youtube": { "status": "success", "video_id": "...", ... }
    }
    """
    if platforms is None:
        platforms = ["tiktok", "instagram", "youtube"]

    results = {}

    if "tiktok" in platforms:
        print("\n[Posting] TikTok...")
        results["tiktok"] = post_to_tiktok(video_path, caption, hashtags)
        time.sleep(1)  # Rate limit

    if "instagram" in platforms:
        print("\n[Posting] Instagram...")
        results["instagram"] = post_to_instagram(video_path, caption, hashtags)
        time.sleep(1)

    if "youtube" in platforms:
        print("\n[Posting] YouTube...")
        yt_title = title or caption[:100]
        yt_desc = f"{caption}\n\n#Shorts #Reddit"
        results["youtube"] = post_to_youtube(video_path, yt_title, yt_desc, hashtags)
        time.sleep(1)

    return results


def log_posting_results(job_id: int, results: Dict[str, Dict]):
    """Log posting results to database."""
    from db import log_platform_post
    
    for platform, result in results.items():
        status = result.get("status", "error")
        post_id = result.get("post_id") or result.get("video_id")
        url = result.get("url")
        error = result.get("error")
        
        log_platform_post(job_id, platform, status, post_id, url, error)
        
        status_icon = "✓" if status == "success" else "✗"
        print(f"  [{status_icon}] {platform}: {status}")
        if error:
            print(f"      Error: {error}")


if __name__ == "__main__":
    # Quick test
    print("poster.py loaded — call post_to_all_platforms() to post.")
    print("\nSetup required:")
    print("1. TikTok: Set TIKTOK_ACCESS_TOKEN in .env")
    print("2. Instagram: Set INSTAGRAM_ACCESS_TOKEN and INSTAGRAM_BUSINESS_ACCOUNT_ID in .env")
    print("3. YouTube: Download OAuth secrets from Google Console → youtube_secrets.json")
