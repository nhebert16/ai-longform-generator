"""
scraper_longform.py — Pulls top story posts from Reddit for long-form videos.
No API key or PRAW required — uses Reddit's public .json endpoints directly.

Upgrades:
- Multi-time-filter fallback: day → week → month if not enough posts found
- Engagement scoring: ranks by upvote ratio × score, not just raw score
- Deduplication across time filters to avoid re-evaluating the same post
"""

import re
import time
import requests
from db import is_post_processed, mark_post_processed

# ── Subreddits ────────────────────────────────────────────────────
TARGET_SUBREDDITS = [
    "AITAH",
    "TrueOffMyChest",
    "relationship_advice",
    "EntitledParents",
    "pettyrevenge",
    "ProRevenge",
]

# ── Tuning ────────────────────────────────────────────────────────
MIN_SCORE        = 5000    # Higher bar — longer posts should be high quality
MIN_WORDS        = 1750    # Minimum ~8 minutes at ~220 wpm TTS rate
MAX_WORDS        = 2700    # ~12 minutes of narration
POSTS_PER_SUB   = 25      # How many to evaluate per subreddit per time filter
MAX_NEW_POSTS   = 2       # Fewer per run — long-form takes longer to produce
REQUEST_DELAY   = 2       # Seconds between requests (be polite)

# Time filters tried in order — falls through to next if not enough posts found
TIME_FILTERS = ["day", "week", "month", "year"]

# Engagement score weight: higher = prefer posts with better upvote ratio
# Score = raw_score * upvote_ratio^RATIO_WEIGHT
RATIO_WEIGHT = 2.0

HEADERS = {"User-Agent": "RedditVideoBot/1.0 (personal project, read-only)"}


# ── Fetching ──────────────────────────────────────────────────────

def fetch_top_posts(subreddit: str, time_filter: str) -> list[dict]:
    """Fetch raw post data from Reddit's public JSON endpoint."""
    url    = f"https://www.reddit.com/r/{subreddit}/top.json"
    params = {"t": time_filter, "limit": POSTS_PER_SUB}
    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return [child["data"] for child in data["data"]["children"]]
    except Exception as e:
        print(f"  [!] Failed to fetch r/{subreddit} ({time_filter}): {e}")
        return []


def fetch_top_comment(subreddit: str, post_id: str) -> str | None:
    """Fetch the top non-mod comment for a post."""
    url = f"https://www.reddit.com/r/{subreddit}/comments/{post_id}.json"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data     = resp.json()
        comments = data[1]["data"]["children"]
        for child in comments:
            c    = child.get("data", {})
            body = c.get("body", "")
            if (not c.get("distinguished")
                    and 20 < len(body) < 300
                    and body not in ("[deleted]", "[removed]")):
                return body.strip()
    except Exception:
        pass
    return None


# ── Filtering & scoring ───────────────────────────────────────────

def strip_markdown(text: str) -> str:
    text = re.sub(r"\*\*?(.*?)\*\*?", r"\1", text)
    text = re.sub(r"~~(.*?)~~",        r"\1", text)
    text = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", text)
    text = re.sub(r"^#{1,6}\s+",  "", text, flags=re.MULTILINE)
    text = re.sub(r"^>\s+",       "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n",   text)
    return text.strip()


def count_words(text: str) -> int:
    return len(text.split())


def engagement_score(post: dict) -> float:
    """
    Composite score that rewards both popularity and engagement quality.
    upvote_ratio is 0.0–1.0 (Reddit's own metric).
    A post with 5k upvotes and 0.97 ratio beats one with 8k and 0.72.
    """
    raw_score    = post.get("score", 0)
    upvote_ratio = post.get("upvote_ratio", 0.5)
    return raw_score * (upvote_ratio ** RATIO_WEIGHT)


def is_suitable(post: dict) -> tuple[bool, str]:
    """Returns (is_suitable, reason_if_not)."""
    if not post.get("is_self"):
        return False, "not a text post"
    if post.get("over_18"):
        return False, "NSFW"
    if post.get("score", 0) < MIN_SCORE:
        return False, f"score too low ({post.get('score')})"

    body = post.get("selftext", "")
    if not body or body in ("[deleted]", "[removed]"):
        return False, "deleted or empty"

    word_count = count_words(strip_markdown(body))
    if word_count < MIN_WORDS:
        return False, f"too short ({word_count} words)"
    if word_count > MAX_WORDS:
        return False, f"too long ({word_count} words — max {MAX_WORDS})"

    return True, ""


# ── Main ──────────────────────────────────────────────────────────

def scrape_posts() -> list[dict]:
    """
    Main entry point. Returns a list of post dicts ready for processing.

    For each subreddit, tries TIME_FILTERS in order (day → week → month)
    until enough suitable posts are found. Posts are ranked by engagement
    score before being queued.
    """
    queued       = []
    seen_ids     = set()   # dedup across time filters within a run

    for sub_name in TARGET_SUBREDDITS:
        if len(queued) >= MAX_NEW_POSTS:
            break

        print(f"\n[Scraper] Checking r/{sub_name}...")

        # Collect candidates across all time filters
        candidates = []

        for time_filter in TIME_FILTERS:
            print(f"  [→] Fetching top posts ({time_filter})...")
            posts = fetch_top_posts(sub_name, time_filter)
            time.sleep(REQUEST_DELAY)

            new_this_filter = 0
            for post in posts:
                post_id = post.get("id")
                if post_id in seen_ids:
                    continue
                seen_ids.add(post_id)

                if is_post_processed(post_id):
                    continue

                suitable, reason = is_suitable(post)
                if not suitable:
                    continue

                candidates.append(post)
                new_this_filter += 1

            print(f"  [→] {new_this_filter} new candidates from '{time_filter}'")

            # If we have enough candidates, no need to go further back in time
            if len(candidates) >= MAX_NEW_POSTS * 2:
                break

        if not candidates:
            print(f"  [→] No suitable posts found in r/{sub_name}")
            continue

        # Sort candidates by engagement score — best first
        candidates.sort(key=engagement_score, reverse=True)
        print(f"  [→] {len(candidates)} total candidates, sorted by engagement")

        # Queue the top ones
        for post in candidates:
            if len(queued) >= MAX_NEW_POSTS:
                break

            post_id    = post.get("id")
            clean_body = strip_markdown(post["selftext"])
            word_count = count_words(clean_body)
            eng_score  = engagement_score(post)

            post_data = {
                "reddit_post_id":  post_id,
                "subreddit":       sub_name,
                "title":           post["title"],
                "body":            clean_body,
                "score":           post["score"],
                "upvote_ratio":    post.get("upvote_ratio", 0),
                "engagement_score": round(eng_score),
                "word_count":      word_count,
                "top_comment":     None,   # fetch separately if needed
                "url":             f"https://reddit.com{post['permalink']}",
            }

            mark_post_processed(post_id, sub_name, post["title"], post["score"], word_count)
            queued.append(post_data)

            print(f"  [✓] Queued: \"{post['title'][:60]}\"")
            print(f"       {word_count} words | {post['score']} upvotes | "
                  f"{post.get('upvote_ratio',0):.0%} ratio | "
                  f"engagement: {round(eng_score):,}")

        time.sleep(REQUEST_DELAY)

    print(f"\n[Scraper] Done. {len(queued)} new posts queued.")
    return queued


if __name__ == "__main__":
    from db import init_db
    init_db()
    posts = scrape_posts()
    for p in posts:
        print(f"\n--- {p['title']} ---")
        print(f"Score: {p['score']} | Ratio: {p['upvote_ratio']:.0%} | "
              f"Engagement: {p['engagement_score']:,}")
        print(p["body"][:300])
