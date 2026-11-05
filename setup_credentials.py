#!/usr/bin/env python3
"""
setup_credentials.py — Interactive credential setup for social media posting

Run with: python setup_credentials.py
"""

import os
from pathlib import Path

def setup_credentials():
    """Interactive setup for social media API credentials."""
    
    env_path = Path(".env")
    
    # Load existing .env if it exists
    env_data = {}
    if env_path.exists():
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and "=" in line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    env_data[key.strip()] = value.strip()
    
    print("\n" + "="*60)
    print("SOCIAL MEDIA POSTING CREDENTIAL SETUP")
    print("="*60)
    
    # TikTok
    print("\n[1/3] TIKTOK")
    print("-" * 40)
    current = env_data.get("TIKTOK_ACCESS_TOKEN", "")
    if current:
        print(f"Current: {current[:20]}...")
        use_current = input("Keep current token? (y/n): ").strip().lower()
        if use_current == "y":
            pass
        else:
            token = input("Enter TikTok Access Token: ").strip()
            if token:
                env_data["TIKTOK_ACCESS_TOKEN"] = token
    else:
        token = input("Enter TikTok Access Token (or press Enter to skip): ").strip()
        if token:
            env_data["TIKTOK_ACCESS_TOKEN"] = token
    
    # Instagram
    print("\n[2/3] INSTAGRAM")
    print("-" * 40)
    current_token = env_data.get("INSTAGRAM_ACCESS_TOKEN", "")
    current_id = env_data.get("INSTAGRAM_BUSINESS_ACCOUNT_ID", "")
    
    if current_token and current_id:
        print(f"Current token: {current_token[:20]}...")
        print(f"Current account ID: {current_id}")
        use_current = input("Keep current credentials? (y/n): ").strip().lower()
        if use_current != "y":
            token = input("Enter Instagram Access Token: ").strip()
            if token:
                env_data["INSTAGRAM_ACCESS_TOKEN"] = token
            acct_id = input("Enter Instagram Business Account ID: ").strip()
            if acct_id:
                env_data["INSTAGRAM_BUSINESS_ACCOUNT_ID"] = acct_id
    else:
        token = input("Enter Instagram Access Token (or press Enter to skip): ").strip()
        if token:
            env_data["INSTAGRAM_ACCESS_TOKEN"] = token
        acct_id = input("Enter Instagram Business Account ID: ").strip()
        if acct_id:
            env_data["INSTAGRAM_BUSINESS_ACCOUNT_ID"] = acct_id
    
    # YouTube
    print("\n[3/3] YOUTUBE")
    print("-" * 40)
    print("YouTube uses OAuth file-based authentication.")
    print("File needed: youtube_secrets.json")
    if Path("youtube_secrets.json").exists():
        print("✓ youtube_secrets.json found in project root")
    else:
        print("✗ youtube_secrets.json NOT found")
        print("  Download from: https://console.cloud.google.com/")
        print("  Save as: youtube_secrets.json in project root")
    
    # Write .env file
    print("\n" + "="*60)
    print("SAVING CREDENTIALS")
    print("="*60)
    
    with open(env_path, "w") as f:
        # Write in order
        if "TIKTOK_ACCESS_TOKEN" in env_data:
            f.write(f"TIKTOK_ACCESS_TOKEN={env_data['TIKTOK_ACCESS_TOKEN']}\n")
        if "INSTAGRAM_ACCESS_TOKEN" in env_data:
            f.write(f"INSTAGRAM_ACCESS_TOKEN={env_data['INSTAGRAM_ACCESS_TOKEN']}\n")
        if "INSTAGRAM_BUSINESS_ACCOUNT_ID" in env_data:
            f.write(f"INSTAGRAM_BUSINESS_ACCOUNT_ID={env_data['INSTAGRAM_BUSINESS_ACCOUNT_ID']}\n")
        
        # Write other existing vars (exclude social creds we just handled)
        for key, value in env_data.items():
            if key not in ["TIKTOK_ACCESS_TOKEN", "INSTAGRAM_ACCESS_TOKEN", "INSTAGRAM_BUSINESS_ACCOUNT_ID"]:
                f.write(f"{key}={value}\n")
    
    print(f"✓ Credentials saved to .env")
    
    # Summary
    print("\n" + "="*60)
    print("SETUP SUMMARY")
    print("="*60)
    if "TIKTOK_ACCESS_TOKEN" in env_data:
        print("✓ TikTok: Configured")
    else:
        print("✗ TikTok: Not configured")
    
    if "INSTAGRAM_ACCESS_TOKEN" in env_data and "INSTAGRAM_BUSINESS_ACCOUNT_ID" in env_data:
        print("✓ Instagram: Configured")
    else:
        print("✗ Instagram: Not configured")
    
    if Path("youtube_secrets.json").exists():
        print("✓ YouTube: Ready (youtube_secrets.json found)")
    else:
        print("✗ YouTube: Not ready (missing youtube_secrets.json)")
    
    print("\n" + "="*60)
    print("NEXT STEPS")
    print("="*60)
    print("1. Test the posting pipeline:")
    print("   python3 -c \"from poster import post_to_all_platforms\"")
    print("\n2. Upload your first video:")
    print("   python main.py")
    print("\n3. Or test posting directly:")
    print("   python3 -c \"from poster import post_to_all_platforms; import json;")
    print("   result = post_to_all_platforms('path/to/video.mp4', 'Test caption', hashtags=['test'])\"")

if __name__ == "__main__":
    setup_credentials()
