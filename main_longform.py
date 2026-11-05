"""
main_longform.py — Orchestrator for the long-form Reddit → Video → YouTube pipeline

Run manually:    python main.py
Run on schedule: python main.py --schedule   (runs twice daily at 4pm + 7pm)
"""

import argparse
import traceback
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler

from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
OUTPUT_DIR   = Path(__import__("os").getenv("OUTPUT_DIR", "output"))
PLAYLIST_ID  = __import__("os").getenv("YOUTUBE_LONGFORM_PLAYLIST_ID", "")

from db import init_db, create_video_job, update_job, log_platform_post
from scraper_longform import scrape_posts
from processor_longform import process_batch, resolve_chapter_timestamps
from tts import generate_audio, save_timestamps
from video_builder_longform import build_video
from poster import post_to_youtube
from thumbnail import generate_thumbnail_longform
from ai_thumbnail import generate_ai_thumbnail
from anthropic import Anthropic as _Anthropic
from llm import ask, HAIKU
_teaser_client = _Anthropic()



def run_pipeline():
    print("\n" + "=" * 60)
    print(f"  Pipeline started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # ── Stage 1: Scrape Reddit ─────────────────────────────────
    print("\n[Stage 1] Scraping Reddit...")
    raw_posts = scrape_posts()
    if not raw_posts:
        print("[!] No new posts found. Exiting.")
        return

    # ── Stage 2: Process with Claude ───────────────────────────
    print("\n[Stage 2] Processing with Claude...")
    processed_posts = process_batch(raw_posts)
    if not processed_posts:
        print("[!] No posts passed processing. Exiting.")
        return

    # ── Stages 3–5 per post ────────────────────────────────────
    for post in processed_posts:
        post_id = post["reddit_post_id"]
        print(f"\n{'─' * 50}")
        print(f"Processing post: {post_id}")

        job_id = create_video_job(post_id)
        update_job(job_id, script=post["script"], hook=post["title"],
                   top_comment=post.get("top_comment"), status="scripted")

        # ── Stage 3: TTS + Whisper alignment ──────────────────
        print(f"\n[Stage 3] Generating TTS for job {job_id}...")
        # Closer already appended by processor_longform
        tts_result = generate_audio(post["script"], job_id)

        if not tts_result:
            update_job(job_id, status="failed", error_message="TTS generation failed")
            print(f"[!] TTS failed for job {job_id}. Skipping.")
            continue

        save_timestamps(tts_result["word_timestamps"], job_id)

        # Resolve chapter timestamps using Whisper word alignment
        chapters = post.get("chapters", [])
        if chapters:
            chapters = resolve_chapter_timestamps(
                chapters,
                post["script"],
                tts_result["word_timestamps"]
            )
            print(f"  [Pipeline] Resolved {len(chapters)} chapter timestamps")
        update_job(job_id, audio_path=tts_result["audio_path"], status="tts_done")

        # ── Stage 4: Build Video ───────────────────────────────
        # Notes:
        #   - music      → auto-resolved from assets/music/ by video_builder
        #   - outro      → auto-loaded from assets/outro/outro_animated_final.mp4
        #   - intro card → rendered by post_card.py using hook + subreddit
        #   - post_cards → None (intro post card handles title display)
        print(f"\n[Stage 4] Building video for job {job_id}...")
        try:
            video_path = build_video(
                job_id=job_id,
                audio_path=tts_result["audio_path"],
                word_timestamps=tts_result["word_timestamps"],
                hook=post["title"],
                post_cards=None,
                top_comment=post.get("top_comment"),
                comment_bait=post.get("comment_bait"),
                subreddit=post.get("subreddit", ""),
                upvotes=str(post.get("score", "")),
                reddit_url=post.get("url", ""),
                chapters=chapters,
            )
        except Exception as e:
            update_job(job_id, status="failed", error_message=str(e))
            print(f"[!] Video build failed for job {job_id}: {e}")
            traceback.print_exc()
            continue

        if not video_path:
            update_job(job_id, status="failed", error_message="video_builder returned None")
            continue

        update_job(job_id, video_path=video_path, status="rendered")
        print(f"\n[✓] Job {job_id} complete — video: {video_path}")

        # AI-illustrated thumbnail, falling back to the branded Pillow one
        thumbnail_path = generate_ai_thumbnail(post["title"], post["script"], job_id)
        try:
            thumbnail_path = thumbnail_path or generate_thumbnail_longform(
                title=post["title"],
                subreddit=post.get("subreddit", "AmItheAsshole"),
                job_id=job_id,
                upvotes=f"{post.get('score', 0):,}" if post.get("score") else "",
            )
        except Exception as e:
            print(f"  [!] Thumbnail generation failed: {e}")
            thumbnail_path = None

        # ── Stage 5: Post to YouTube ───────────────────────────
        print(f"\n[Stage 5] Posting to YouTube...")
        try:
            # Build subreddit-specific hashtags
            sub = post.get("subreddit", "").lower()
            if "aita" in sub or "amithea" in sub:
                niche_tags = "#AITA #AmITheAsshole #RedditStories"
            elif "tifu" in sub:
                niche_tags = "#TIFU #RedditStories #Storytime"
            elif "relationship" in sub:
                niche_tags = "#RelationshipAdvice #RedditStories #Storytime"
            elif "confession" in sub or "offmychest" in sub or "trueoffmychest" in sub:
                niche_tags = "#Confessions #OffMyChest #RedditStories"
            else:
                niche_tags = "#RedditStories #Storytime #Confessions"

            # Generate natural description (2-3 sentences, no AI structure)
            desc_body = ""
            try:
                desc_body = ask(_teaser_client, HAIKU, (
                    f"Write 2 to 3 short sentences for a YouTube video description based on this Reddit story title. "
                    f"Sound like a real person wrote it, not a bot. No dashes, no colons, no bullet points, no em dashes. "
                    f"No phrases like 'In this video' or 'Join us'. Don't reveal the outcome. "
                    f"End with a casual question that invites people to comment, like something you'd actually type. "
                    f"No hashtags, no quotes.\n\nTitle: {post['title']}"
                ), max_tokens=120).strip().strip('"')
            except Exception as _e:
                print(f"  [!] Description generation failed: {_e}")

            # Build chapter timestamps for YouTube description
            chapter_lines = []
            for ch in chapters:
                t  = ch.get("start_seconds", 0)
                mm, ss = divmod(int(t), 60)
                chapter_lines.append(f"{mm:02d}:{ss:02d} {ch['name']}")
            chapter_block = "\n".join(chapter_lines)

            description = (
                f"{desc_body}\n\n"
                f"{chapter_block}\n\n"
                f"{niche_tags} #Reddit #Storytime #Viral"
            )

            yt_result = post_to_youtube(
                video_path=str(video_path),
                title=post["title"][:100],
                description=description[:5000],
                tags=["reddit", "stories", "aita", "viral", "storytime", "redditstories", "longform"],
                privacy_status="private",
                thumbnail_path=thumbnail_path,
                playlist_id=PLAYLIST_ID or None,
            )
            
            # Log result
            if yt_result["status"] == "success":
                log_platform_post(job_id, "youtube", "success", yt_result.get("video_id"), 
                                yt_result.get("url"))
                print(f"    ✓ YouTube: {yt_result['url']}")
                update_job(job_id, status="posted")
            else:
                log_platform_post(job_id, "youtube", "failed", error_message=yt_result.get("error"))
                print(f"    ✗ YouTube: {yt_result['error']}")
                update_job(job_id, status="failed", error_message=yt_result.get("error"))
        except Exception as e:
            log_platform_post(job_id, "youtube", "failed", error_message=str(e))
            print(f"    ✗ YouTube posting failed: {e}")
            traceback.print_exc()

    print("\n" + "=" * 60)
    print(f"  Pipeline finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Reddit → Long-form Video pipeline")
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="Run on a schedule (4pm + 7pm daily) instead of once",
    )
    args = parser.parse_args()

    init_db()

    if args.schedule:
        scheduler = BlockingScheduler()
        scheduler.add_job(run_pipeline, "cron", hour="14", minute=0)
        print("[Scheduler] Long-form pipeline scheduled for 2:00 PM daily.")
        print("[Scheduler] Press Ctrl+C to stop.")
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            print("[Scheduler] Stopped.")
    else:
        run_pipeline()


if __name__ == "__main__":
    main()
