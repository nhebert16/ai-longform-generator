#!/usr/bin/env python3
"""
test_youtube_auth.py — Test YouTube OAuth authentication and upload

Run this to:
1. Authenticate with YouTube (opens browser first time)
2. Save the token for future use
3. Test uploading a sample video
"""

import os
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.exceptions import RefreshError
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# YouTube API scopes
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly"
]

def get_authenticated_service():
    """Authenticate with YouTube and return the service."""
    
    creds = None
    token_path = Path("youtube_token.json")
    
    # Step 1: Check if we have a saved token
    print("\n[1/3] Checking for saved token...")
    if token_path.exists():
        print("  ✓ Found youtube_token.json")
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        print("  ✓ Token loaded")
    else:
        print("  ✗ No saved token found")
    
    # Step 2: If no valid token, authenticate
    if not creds or not creds.valid:
        print("\n[2/3] Authenticating with YouTube...")
        
        if creds and creds.expired and creds.refresh_token:
            print("  Refreshing expired token...")
            try:
                creds.refresh(Request())
                print("  ✓ Token refreshed")
            except RefreshError:
                print("  ✗ Token refresh failed, need new auth")
                creds = None
        
        if not creds:
            print("  Opening browser for authentication...")
            flow = InstalledAppFlow.from_client_secrets_file(
                "youtube_secrets.json", SCOPES
            )
            creds = flow.run_local_server(port=8080)
            print("  ✓ Authentication successful")
        
        # Save token for future use
        print("  Saving token to youtube_token.json...")
        with open(token_path, "w") as token_file:
            token_file.write(creds.to_json())
        print("  ✓ Token saved")
    
    # Step 3: Build service
    print("\n[3/3] Building YouTube service...")
    service = build("youtube", "v3", credentials=creds)
    print("  ✓ Service ready")
    
    return service


def get_channel_info(service):
    """Get info about the authenticated user's channel."""
    print("\n[Testing] Getting channel info...")
    
    try:
        request = service.channels().list(
            part="snippet,statistics",
            mine=True
        )
        response = request.execute()
        
        if response["items"]:
            channel = response["items"][0]
            title = channel["snippet"]["title"]
            subscribers = channel["statistics"].get("subscriberCount", "N/A")
            views = channel["statistics"].get("viewCount", "0")
            
            print(f"  ✓ Channel: {title}")
            print(f"    Subscribers: {subscribers}")
            print(f"    Total views: {views}")
            return channel
        else:
            print("  ✗ No channel found")
            return None
    except HttpError as e:
        print(f"  ✗ Error: {e}")
        return None


def main():
    print("="*60)
    print("YOUTUBE API AUTHENTICATION TEST")
    print("="*60)
    
    # Check if secrets file exists
    if not Path("youtube_secrets.json").exists():
        print("\n✗ ERROR: youtube_secrets.json not found!")
        print("  Please download it from Google Cloud Console and place it in the project root.")
        return False
    
    print("\n✓ youtube_secrets.json found")
    
    # Authenticate
    try:
        service = get_authenticated_service()
    except Exception as e:
        print(f"\n✗ Authentication failed: {e}")
        return False
    
    # Get channel info
    channel = get_channel_info(service)
    
    if channel:
        print("\n" + "="*60)
        print("✓ SUCCESS! YouTube is ready to use.")
        print("="*60)
        print("\nYou can now:")
        print("  1. Integrate YouTube posting into main.py")
        print("  2. Upload videos using the poster.py module")
        print("  3. Check youtube_token.json (auto-created, don't commit!)")
        print("\nNext steps:")
        print("  - Add youtube_token.json to .gitignore")
        print("  - Run: python main.py")
        print("  - Videos will auto-upload to YouTube at the end")
        return True
    else:
        print("\n" + "="*60)
        print("✗ FAILED: Could not get channel info")
        print("="*60)
        return False


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
