"""
processor_longform.py — Process Reddit posts for long-form YouTube videos.

Splits posts into 5-7 named chapters so the pipeline can generate
YouTube timestamp descriptions and visual chapter markers.
"""

import os
import json
from dotenv import load_dotenv
from anthropic import Anthropic
from llm import ask, SONNET

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY not set in .env")

client = Anthropic()

CLOSER = "Thank you for watching. Be sure to subscribe for more of the best Reddit threads."


def strip_emojis(text: str) -> str:
    import re
    text = re.sub(u'[\U00010000-\U0010ffff]', '', text)
    text = re.sub(u'[\U0001F000-\U0001FFFF]', '', text)
    text = re.sub(u'[\u2600-\u27BF]', '', text)
    text = re.sub(r'\s*[:;=8]-?[)(DdPpOoXx/\\|]+', '', text)
    text = re.sub(r'\s*[)(DdPpOoXx/\\|]+-?[:;=8]', '', text)
    text = re.sub(r'  +', ' ', text)
    return text.strip()


SYSTEM_PROMPT = """You are a Reddit story narrator preparing posts for long-form YouTube videos.

Your job is to:
1. Read the post title naturally as the opening
2. Read the post body word-for-word — do NOT summarize or rewrite
3. Split the content into 5-7 named chapters that match the natural story arc

Chapter names should fit the story — use these as a guide but adapt:
- "Intro" (always first, covers the title)
- "Background" (who the people are, context)
- "The Situation" (what happened)
- "The Confrontation" (key moment or conflict)
- "The Fallout" (reactions, consequences)
- "My Side" (OP's justification or feelings)
- "Verdict" (final thoughts, update, or resolution)

Not every post needs all 7 — use 5 if the story is simpler. Never force chapters that don't fit.

The pipeline builds the script itself (title followed by the exact body), so do NOT
repeat the story text — return only the chapter markers and tags.

Format your response as JSON:
{
  "chapters": [
    {"name": "Intro", "first_words": "exact first 4-5 words of this chapter's content"},
    {"name": "Background", "first_words": "exact first 4-5 words of this chapter's content"},
    {"name": "The Situation", "first_words": "exact first 4-5 words"},
    {"name": "The Confrontation", "first_words": "exact first 4-5 words"},
    {"name": "The Fallout", "first_words": "exact first 4-5 words"}
  ],
  "tags": ["tag1", "tag2"]
}

Rules:
- The script is the title followed by the exact post body
- The "first_words" field must match the EXACT words at the start of each chapter in the script
  so the pipeline can find the chapter boundary by text matching
- The "Intro" chapter's first_words are the first words of the title
- first_words should be unique enough to locate unambiguously in the script
"""


def process_batch(posts: list[dict]) -> list[dict]:
    results = []

    for i, post in enumerate(posts, 1):
        print(f"\n  [{i}/{len(posts)}] Processing: {post.get('title', 'Unknown')[:60]}...")

        post_body = post.get('selftext') or post.get('body') or post.get('text') or ''
        # Truncate to same word limit as scraper — guarantees no mid-sentence cutoff
        MAX_WORDS = 3000
        post_body_words = post_body.split()
        if len(post_body_words) > MAX_WORDS:
            post_body = " ".join(post_body_words[:MAX_WORDS])
            print(f"    [!] Body trimmed to {MAX_WORDS} words")

        user_prompt = f"""Split this Reddit post into chapters for a long-form video.

SUBREDDIT: {post.get('subreddit', 'unknown')}
TITLE: {post.get('title', 'No title')}
BODY: {post_body}
SCORE: {post.get('score', 0)}
COMMENTS: {post.get('num_comments', 0)}

IMPORTANT:
- Return only the chapters and tags JSON — do not repeat the story
- The first_words for each chapter must be the exact words that appear at that point in the title + body"""

        try:
            response_text = ask(client, SONNET, user_prompt, max_tokens=2000, system=SYSTEM_PROMPT)

            try:
                start = response_text.find('{')
                end   = response_text.rfind('}') + 1
                if start != -1 and end > start:
                    result = json.loads(response_text[start:end])
                else:
                    raise ValueError("No JSON found")
            except (json.JSONDecodeError, ValueError):
                print(f"    [!] JSON parse failed, using fallback")
                result = {
                    "hook":     post.get('title', '')[:100],
                    "title":    post.get('title', ''),
                    "script":   post.get('title', '') + " " + post_body,
                    "chapters": [{"name": "Intro", "first_words": post.get('title', '')[:30]}],
                    "tags":     ["reddit"]
                }

            result.setdefault("hook",     post.get('title', '')[:100])
            result.setdefault("title",    post.get('title', ''))
            result["script"] = post.get('title', '') + " " + post_body
            result.setdefault("chapters", [])
            result.setdefault("tags",     [])

            script_words = len(result["script"].split())
            print(f"    [✓] Script: {script_words} words, {len(result['chapters'])} chapters")
            for ch in result["chapters"]:
                print(f"         • {ch['name']}: \"{ch['first_words']}\"")

            final_result = {
                "hook":            result.get("hook", ""),
                "title":           result.get("title", post.get('title', '')),
                "script":          strip_emojis(result.get("script", "")),
                "chapters":        result.get("chapters", []),
                "tags":            result.get("tags", []),
                "subreddit":       post.get('subreddit', ''),
                "reddit_post_id":  post.get('reddit_post_id', ''),
                "score":           post.get('score', 0),
                "num_comments":    post.get('num_comments', 0),
                "url":             post.get('url', ''),
            }
            final_result["hook"] = strip_emojis(final_result["hook"])
            # Append branded closer
            final_result["script"] = final_result["script"].rstrip() + " " + CLOSER

            results.append(final_result)

        except Exception as e:
            print(f"    [!] Failed: {e}")
            continue

    return results


def resolve_chapter_timestamps(chapters: list[dict], script: str,
                                word_timestamps: list[dict]) -> list[dict]:
    """
    Match each chapter's first_words against the script to find which
    word index it starts at, then look up that word's timestamp.

    Returns chapters with a 'start_seconds' field added.
    """
    import re
    script_words = script.split()

    resolved = []
    for ch in chapters:
        first_words = ch.get("first_words", "").strip()
        if not first_words:
            resolved.append({**ch, "start_seconds": 0})
            continue

        # Normalise both sides for matching
        needle = re.sub(r"[^\w\s]", "", first_words.lower()).split()
        if not needle:
            resolved.append({**ch, "start_seconds": 0})
            continue

        # Slide a window of len(needle) words across the script
        found_at = None
        for idx in range(len(script_words) - len(needle) + 1):
            window = [re.sub(r"[^\w]", "", w.lower())
                      for w in script_words[idx: idx + len(needle)]]
            if window == needle:
                found_at = idx
                break

        if found_at is not None and found_at < len(word_timestamps):
            start_s = word_timestamps[found_at]["start"]
        else:
            # Fallback: evenly space unresolved chapters
            start_s = 0
            print(f"  [!] Could not locate chapter '{ch['name']}' — defaulting to 0s")

        resolved.append({**ch, "start_seconds": round(start_s)})

    return resolved


if __name__ == "__main__":
    test_post = {
        "subreddit": "AmItheAsshole",
        "title": "AITA for refusing to pay for my sister's wedding after she uninvited my husband?",
        "selftext": (
            "My sister Sarah is getting married in June. I was originally asked to help fund "
            "part of the wedding because she and her fiance are struggling financially. I agreed "
            "to contribute two thousand dollars. Last month she told me that my husband Jake is "
            "no longer invited because her fiance does not get along with him. They had a falling "
            "out two years ago over a business deal that went bad. I told her that if Jake is not "
            "invited then I will not be attending either and I am withdrawing my financial contribution. "
            "She called me selfish and said I was ruining her wedding. My parents are siding with her "
            "and saying I should just come alone and still pay because it is her special day. "
            "Jake said he does not want to cause drama and told me I should go without him and keep "
            "the peace. But I feel like attending without him and still funding the wedding would be "
            "condoning the way she treated him. She has not apologized and neither has her fiance. "
            "My maid of honor duties have also been revoked which honestly just confirmed to me that "
            "this was never really about me being there for her. Am I the asshole for pulling my "
            "financial support and refusing to attend?"
        ),
        "reddit_post_id": "test123",
        "score": 8500,
        "num_comments": 1200,
        "url": "https://reddit.com/r/AmItheAsshole/test123",
    }

    results = process_batch([test_post])
    for r in results:
        print(f"\nTitle: {r['title']}")
        print(f"Chapters: {len(r['chapters'])}")
        for ch in r['chapters']:
            print(f"  {ch['name']}: \"{ch['first_words']}\"")
