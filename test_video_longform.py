"""
test_video_longform.py — Test the long-form video pipeline.
Fetches a real Reddit post by URL, runs it through processor_longform
for chapter splitting, then builds a 1920x1080 video with timestamps.
"""

import os
import re
import shutil
import requests
from db import init_db
from tts import generate_audio, save_timestamps
from video_builder_longform import build_video
from processor_longform import process_batch, resolve_chapter_timestamps, CLOSER
from scraper_longform import scrape_posts
from story_generator import generate_story

init_db()

# ── Config ────────────────────────────────────────────────────────
JOB_ID    = 98
MAX_WORDS = 3000

# ── Clear caches ──────────────────────────────────────────────────
for path in [
    f"assets/cards/card_{JOB_ID}.png",
    f"output/audio/job_{JOB_ID}.mp3",
    f"output/timestamps/job_{JOB_ID}.json",
]:
    if os.path.exists(path):
        os.remove(path)
        print(f"  [Test] Cleared: {path}")

frames_dir = f"assets/cards/frames_{JOB_ID}"
if os.path.exists(frames_dir):
    shutil.rmtree(frames_dir)
    print(f"  [Test] Cleared: {frames_dir}")


# ── Hardcoded 50-word test script ────────────────────────────────
print("\n[Test] Using hardcoded 50-word test script...")
REDDIT_POST_URL = "[TEST]"
title  = "AITA for telling my mother-in-law exactly what I think of her after four years of silence?"
body   = (
    "I have been married for four years. My mother-in-law has spent every one of those years "
    "making small cutting remarks about my cooking, my clothes, and my family. Last Sunday at "
    "dinner she made a comment about my mother. I put down my fork and told her clearly that "
    "her behavior had been unacceptable for years and that I would not be returning to her home."
)
score  = 0
ratio  = 0
sub    = "r/AmItheAsshole"
source = "TEST"

print(f"  [✓] Source   : {source}")
print(f"  [✓] Subreddit: {sub}")
print(f"  [✓] Title    : {title[:80]}")
print(f"  [✓] Body     : {len(body.split())} words")


# ── Process through Claude for chapters ──────────────────────────
print("\n[Test] Processing with Claude for chapters...")
raw_post = {
    "title":          title,
    "selftext":       body,
    "subreddit":      sub,
    "reddit_post_id": "test_98",
    "score":          score,
    "num_comments":   0,
    "url":            REDDIT_POST_URL,
    "format":         "standard",  # test script
}
processed = process_batch([raw_post])
if not processed:
    print("  [!] Processing failed.")
    exit(1)

result   = processed[0]
HOOK     = result["title"]
SCRIPT   = result["script"]   # title + body + closer, from processor
chapters = result.get("chapters", [])

print(f"  [✓] Script : {len(SCRIPT.split())} words")
print(f"  [✓] Chapters: {len(chapters)}")
for ch in chapters:
    print(f"       • {ch['name']}: \"{ch['first_words']}\"")


# ── Generate audio + Whisper timestamps ──────────────────────────
print("\n[Test] Generating audio...")
tts_result = generate_audio(SCRIPT, job_id=JOB_ID)
if not tts_result:
    print("  [!] TTS failed.")
    exit(1)

save_timestamps(tts_result["word_timestamps"], job_id=JOB_ID)
print(f"  [✓] {len(tts_result['word_timestamps'])} word timestamps")


# ── Resolve chapter timestamps ────────────────────────────────────
print("\n[Test] Resolving chapter timestamps...")
chapters = resolve_chapter_timestamps(chapters, SCRIPT, tts_result["word_timestamps"])
for ch in chapters:
    t = ch.get("start_seconds", 0)
    mm, ss = divmod(int(t), 60)
    print(f"  {mm:02d}:{ss:02d} {ch['name']}")


# ── Build video ───────────────────────────────────────────────────
print("\n[Test] Building video...")
result = build_video(
    job_id=JOB_ID,
    audio_path=tts_result["audio_path"],
    word_timestamps=tts_result["word_timestamps"],
    hook=HOOK,
    post_cards=None,
    subreddit=sub,
    upvotes=f"{score:,}",
    reddit_url=REDDIT_POST_URL,
    chapters=chapters,
)

# ── Print YouTube description preview ────────────────────────────
print("\n── YouTube Description Preview ──────────────────────────")
chapter_lines = []
for ch in chapters:
    t = ch.get("start_seconds", 0)
    mm, ss = divmod(int(t), 60)
    chapter_lines.append(f"{mm:02d}:{ss:02d} {ch['name']}")

subreddit_lower = sub.lower()
if "aita" in subreddit_lower:
    niche_tags = "#AITA #AmITheAsshole #RedditStories"
elif "relationship" in subreddit_lower:
    niche_tags = "#RelationshipAdvice #RedditStories #Storytime"
else:
    niche_tags = "#RedditStories #Storytime #Confessions"

source_line = f"Story from: {REDDIT_POST_URL}" if REDDIT_POST_URL != "[GENERATED STORY]" else "Original story inspired by real Reddit posts."
description = (
    "\n".join(chapter_lines) + "\n\n"
    "Was she wrong? Drop your verdict in the comments below.\n\n"
    f"{source_line}\n\n"
    f"{niche_tags} #Reddit #Storytime #Viral"
)
print(description)
print("─────────────────────────────────────────────────────────")
print("\nResult:", result)
