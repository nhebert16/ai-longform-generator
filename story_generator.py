"""
story_generator.py — Generates original Reddit-style long-form drama stories
when the scraper cannot find suitable posts.

Uses Claude Sonnet for higher quality writing.
Stories are modelled on viral Reddit drama threads with:
- Specific ages/genders in (29F) format
- Measured first-person voice that turns sharp
- One significant reactive update where things spiral out of OP's control
- Unresolved ending that invites comment
- ~1800-2200 words total
"""

import json
import random
from anthropic import Anthropic
from dotenv import load_dotenv
from llm import ask, SONNET
import os

load_dotenv()
client = Anthropic()

SYSTEM_PROMPT = """You are a creative writer who specialises in original Reddit-style drama stories for YouTube narration videos.

Write stories that feel authentic to Reddit — specific, grounded, emotionally real. The narrator should sound like a real person, not a storyteller.

Story criteria:
- Narrator: female, late 20s to early 30s, in a relationship or recently married
- Antagonist: mother-in-law, sister, narcissistic partner, or controlling family member
- Tone: calm and measured at first, becomes sharp and decisive
- Structure: Setup (background + pattern of behavior) → Escalating incident → OP takes action → Fallout begins
- UPDATE section: triggered by something external going wrong — antagonist finds the post, shows up somewhere, destroys something, contacts people they shouldn't, or does something unhinged. OP did NOT plan for this. They are reactive, not triumphant.
- Ending: unresolved. OP is not sure if they did the right thing. Ends on a quiet human detail, not a lesson.
- Age/gender tags: always include (29F), (31M), (58F) etc. for all named people on first mention
- Length: 1800-2200 words total including the UPDATE — this is non-negotiable, the video must be 8-10 minutes long at 220 words per minute
- Names: use common American names (e.g. Ashley, Tyler, Brittany, Derek, Kayla, Jason, Megan, Brandon). Avoid British, European, or obviously foreign names unless the story specifically calls for it.
- No emojis. No lists. No moral lessons. No "I guess I learned that..."
- The UPDATE should be ONE significant reactive event, not a summary of multiple things

Themes to rotate between (pick one per story, vary across runs):
1. Mother-in-law financial/property manipulation exposed at a family event
2. Narcissistic partner's double life discovered and confronted publicly  
3. Sister/sibling betrayal over inheritance or family resources
4. Toxic workplace dynamic where OP finally stops absorbing it
5. Controlling parent interfering in adult child's marriage
6. Friend who has been lying about OP to mutual friends exposed

Format your response as JSON:
{
  "title": "AITA for [specific action]?",  (MUST be under 100 characters — YouTube title limit)
  "body": "Full story text including UPDATE section. Use \\n\\n between paragraphs. The UPDATE heading should appear as: UPDATE:",
  "tags": ["aita", "familydrama", "redditstories"]
}"""

# Theme seeds — each maps to the most fitting subreddit
THEMES = [
    ("mother-in-law financial manipulation exposed at family event",                                        "AmItheAsshole"),
    ("narcissistic partner double life discovered and confronted",                                          "relationship_advice"),
    ("sister betrayal over inheritance or family money",                                                    "AITAH"),
    ("controlling parent interfering in adult child's marriage",                                            "JUSTNOFAMILY"),
    ("friend who has been lying about OP to mutual friends",                                                "TrueOffMyChest"),
    ("toxic family member exposed at a milestone celebration",                                              "AmItheAsshole"),
    ("husband's family excluded OP from major financial decision affecting their home",                     "AITAH"),
    ("coworker took credit for OP's work for months and OP exposed them in front of management",           "TrueOffMyChest"),
    ("sister-in-law announced pregnancy at OP's wedding reception to steal attention",                      "AmItheAsshole"),
    ("OP discovered partner had a secret child they never disclosed before marriage",                       "relationship_advice"),
    ("narcissistic mother sold OP's childhood belongings without permission while OP was abroad",           "JUSTNOFAMILY"),
    ("OP's best friend of ten years was secretly dating their ex the entire time",                         "TrueOffMyChest"),
    ("father-in-law forged OP's signature on a document and OP only found out years later",                "AITAH"),
    ("OP's partner invited his ex to move into their home while OP was in hospital",                       "relationship_advice"),
    ("OP discovered their entire friend group had a separate group chat excluding only them",               "TrueOffMyChest"),
    ("OP's mother-in-law had been telling the grandchildren lies about OP for years",                      "JUSTNOFAMILY"),
    ("OP found messages proving their partner had been financially supporting an ex in secret",             "relationship_advice"),
    ("OP's sister stole her wedding venue deposit by pretending to be her on the phone",                   "AITAH"),
    ("OP was written out of a parent's will after a sibling fed the parent deliberate lies",               "AmItheAsshole"),
    ("partner's family staged an intervention to pressure OP into quitting their career",                  "AITAH"),
    ("OP found out their landlord had been entering their apartment without notice for months",             "TrueOffMyChest"),
    ("OP's mother gave away a family heirloom promised to OP to a sibling who asked first",                "JUSTNOFAMILY"),
    ("OP discovered their partner had been sending money to his family without telling them draining savings", "relationship_advice"),
    ("OP's coworker had been impersonating them over email to clients to make them look incompetent",      "TrueOffMyChest"),
]


def generate_story() -> dict | None:
    """
    Generate an original Reddit-style story using Claude Sonnet.
    Returns a post dict compatible with processor_longform.process_batch().
    """
    theme, subreddit = random.choice(THEMES)
    print(f"  [StoryGen] Generating story — theme: {theme} | subreddit: r/{subreddit}")

    try:
        text = ask(
            client, SONNET,
            f"Write a story on this theme: {theme}. Make it feel completely original and specific. Do not recycle names or situations from previous stories.",
            max_tokens=4000,
            system=SYSTEM_PROMPT,
        )
        start = text.find('{')
        end   = text.rfind('}') + 1
        if start == -1 or end <= start:
            print("  [!] StoryGen: no JSON in response")
            return None

        data = json.loads(text[start:end])
        title = data.get("title", "").strip()
        body  = data.get("body", "").strip()

        if not title or not body:
            print("  [!] StoryGen: empty title or body")
            return None

        # Enforce YouTube 100 character title limit
        if len(title) > 100:
            print(f"  [!] StoryGen: title too long ({len(title)} chars) — trimming to 100")
            # Trim at last word boundary before 100 chars
            title = title[:100].rsplit(' ', 1)[0]
            if not title.endswith('?'):
                title = title.rstrip('.,') + '?'
            print("  [StoryGen] Trimmed title: " + title)

        word_count = len(body.split())
        print(f"  [StoryGen] Generated: {word_count} words — \"{title[:70]}\"")

        return {
            "reddit_post_id":   f"generated_{hash(title) & 0xFFFFFF:06x}",
            "subreddit":        subreddit,
            "title":            title,
            "body":             body,
            "selftext":         body,
            "score":            0,
            "upvote_ratio":     0,
            "engagement_score": 0,
            "word_count":       word_count,
            "top_comment":      None,
            "url":              "",
            "format":           "generated",
            "tags":             data.get("tags", ["aita", "redditstories"]),
        }

    except Exception as e:
        print(f"  [!] StoryGen failed: {e}")
        return None
