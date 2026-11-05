"""
ai_thumbnail.py — AI-illustrated YouTube thumbnails for longform videos.

Pipeline:
  1. Claude reads the story and plans the thumbnail (headline + scene) as JSON
  2. OpenAI GPT Image renders a dramatic illustrated scene with the headline
  3. Claude (vision) checks the headline is spelled correctly — retry if not
  4. Cropped/resized to 1280x720 JPEG

Style reference (optional): drop a thumbnail you like at
  assets/thumbnail_style_ref.png  — every image will match its art style.

Returns the JPEG path, or None on failure so callers can fall back to
thumbnail.generate_thumbnail_longform().

Test:  python ai_thumbnail.py            (latest 3 stories in the DB)
       python ai_thumbnail.py 12 13      (specific job ids)
"""

import base64
import io
import json
import os
import sys
from pathlib import Path

from anthropic import Anthropic
from openai import OpenAI
from PIL import Image
from dotenv import load_dotenv
from llm import ask, SONNET

load_dotenv()

OUTPUT_DIR   = Path(os.getenv("OUTPUT_DIR", "output"))
IMAGE_MODEL  = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2")
IMAGE_QUALITY = os.getenv("OPENAI_IMAGE_QUALITY", "high")   # low / medium / high
STYLE_REF    = Path("assets/thumbnail_style_ref.png")
MAX_ATTEMPTS = 3
IMAGE_SIZE   = "1536x864"   # native 16:9 — no cropping needed

THUMB_W, THUMB_H = 1280, 720

claude = Anthropic()
openai_client = OpenAI()


# ── Stage 1: Plan ─────────────────────────────────────────────

PLAN_PROMPT = """You design viral YouTube thumbnails for a dramatic storytime channel.
Read this story and plan ONE thumbnail. Return ONLY valid JSON, no other text.

{{
  "headline": ["2-4 short ALL CAPS lines, 2-5 words total per line, max ~10 words overall"],
  "highlight_line": <index of the line with the most shocking word, shown in red>,
  "foreground": "main character: appearance, outfit, strong visible emotion (crying, shocked, furious), pose",
  "background": "antagonist looming behind: appearance, outfit, expression, pose",
  "extra": "optional third person or empty string (e.g. child clutching a teddy bear)",
  "setting": "specific dramatic location and time of day that fits the story",
  "props": "1-2 story props that hint at the plot (phone with texts, wedding ring, keys, photo)",
  "symbol": "one bold icon that sums up the conflict (cracked red heart, broken ring, lock, warning sign)"
}}

Headline rules:
- Do NOT repeat the video title. Tease the twist and create curiosity.
- Punchy, emotional, readable at small size. Example: ["HE CAME", "BACK FOR", "CUSTODY,", "NOT THE CHILD."]
- No profanity. No "AITA".
- Characters must be fictional adults (children only if the story has one); never real or famous people.

TITLE: {title}

STORY:
{story}
"""


def _parse_json(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}") + 1
    return json.loads(text[start:end])


def plan_thumbnail(title: str, story: str) -> dict:
    plan = _parse_json(ask(claude, SONNET, PLAN_PROMPT.format(title=title, story=story[:6000]), max_tokens=1000))
    plan["headline"] = [line.upper().strip() for line in plan["headline"]][:4]
    return plan


# ── Stage 2: Render ───────────────────────────────────────────

LINE_COLORS = ["bright white", "metallic gold", "bright white", "bright white"]


def build_image_prompt(plan: dict) -> str:
    lines = plan["headline"]
    hl = plan.get("highlight_line", len(lines) - 1)
    text_spec = []
    for i, line in enumerate(lines):
        color = "blood red" if i == hl else LINE_COLORS[i % len(LINE_COLORS)]
        text_spec.append(f'line {i + 1} in {color}: "{line}"')

    extra = f" Also in the scene: {plan['extra']}." if plan.get("extra") else ""
    style = ("Match the art style, lighting, color grading and text treatment of the reference image, "
             "but with completely new characters and scene. " if STYLE_REF.exists() else "")

    return (
        f"{style}Wide 16:9 YouTube thumbnail. Dramatic semi-realistic digital painting in a glossy "
        f"3D-animated drama style, cinematic rim lighting, warm highlights, saturated reds and golds, "
        f"very high contrast, emotional and eye-catching even at small size.\n"
        f"RIGHT HALF of the image: in the foreground, {plan['foreground']}. "
        f"Looming behind them, {plan['background']}.{extra}\n"
        f"Setting: {plan['setting']}. Props: {plan['props']}.\n"
        f"Near the headline: {plan['symbol']}, glossy with a splatter effect.\n"
        f"LEFT HALF of the image: a huge stacked headline in a heavy condensed all-caps display font, "
        f"each line with a thick black outline and strong drop shadow, slightly tilted, filling the left side: "
        f"{'; '.join(text_spec)}.\n"
        f"The text must be spelled EXACTLY as written, with no extra words anywhere in the image. "
        f"No watermarks, captions, brand names or app logos. Keep all text and faces away from the top and bottom edges."
    )


def render_image(prompt: str) -> Image.Image:
    if STYLE_REF.exists():
        with open(STYLE_REF, "rb") as ref:
            result = openai_client.images.edit(
                model=IMAGE_MODEL, image=[ref], prompt=prompt,
                size=IMAGE_SIZE, quality=IMAGE_QUALITY,
            )
    else:
        result = openai_client.images.generate(
            model=IMAGE_MODEL, prompt=prompt,
            size=IMAGE_SIZE, quality=IMAGE_QUALITY,
        )
    return Image.open(io.BytesIO(base64.b64decode(result.data[0].b64_json))).convert("RGB")


def to_youtube_size(img: Image.Image) -> Image.Image:
    """Center-crop to 16:9 if needed, then resize to 1280x720."""
    w, h = img.size
    target_h = int(w * 9 / 16)
    top = (h - target_h) // 2
    return img.crop((0, top, w, top + target_h)).resize((THUMB_W, THUMB_H), Image.LANCZOS)


# ── Stage 3: Verify ───────────────────────────────────────────

def verify_text(img: Image.Image, headline: list[str]) -> tuple[bool, str]:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    expected = " / ".join(headline)
    content = [
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                     "data": base64.b64encode(buf.getvalue()).decode()}},
        {"type": "text", "text": (
            f'This thumbnail should show exactly this headline (lines separated by " / "): {expected}\n'
            "Check every word letter by letter. Ignore line breaks and punctuation differences. "
            "Also fail it if any headline letter touches or is cut off by an image edge, or if there is garbled/misspelled "
            "text anywhere or a second caption competing with the headline. Small readable text on props (phone or bank "
            "screens, documents, signs) is fine — do not fail for that. "
            'Return ONLY JSON: {"ok": true/false, "seen": "text you read", "problem": "short reason or empty"}'
        )},
    ]
    result = _parse_json(ask(claude, SONNET, content, max_tokens=300))
    return bool(result.get("ok")), result.get("problem") or result.get("seen", "")


# ── Main entry ────────────────────────────────────────────────

def generate_ai_thumbnail(title: str, story: str, job_id: int) -> str | None:
    """Generate a 1280x720 AI thumbnail. Returns JPEG path or None on failure."""
    thumbs_dir = OUTPUT_DIR / "thumbnails"
    thumbs_dir.mkdir(parents=True, exist_ok=True)
    output_path = thumbs_dir / f"job_{job_id}_ai_thumb.jpg"

    try:
        print("  [AI Thumbnail] Planning with Claude...")
        plan = plan_thumbnail(title, story)
        print(f"  [AI Thumbnail] Headline: {' / '.join(plan['headline'])}")
        prompt = build_image_prompt(plan)

        best = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            print(f"  [AI Thumbnail] Rendering with {IMAGE_MODEL} (attempt {attempt}/{MAX_ATTEMPTS})...")
            img = to_youtube_size(render_image(prompt))
            best = img
            ok, note = verify_text(img, plan["headline"])
            if ok:
                print("  [AI Thumbnail] ✓ Headline verified")
                break
            print(f"  [AI Thumbnail] ✗ Text check failed: {note}")
        else:
            print("  [AI Thumbnail] [!] No attempt passed the text check — falling back")
            best.save(thumbs_dir / f"job_{job_id}_ai_thumb_rejected.jpg", "JPEG", quality=90)
            return None

        best.save(output_path, "JPEG", quality=90)
        (thumbs_dir / f"job_{job_id}_ai_thumb_plan.json").write_text(json.dumps(plan, indent=2))
        print(f"  [AI Thumbnail] Saved: {output_path}")
        return str(output_path)

    except Exception as e:
        print(f"  [AI Thumbnail] [!] Failed: {type(e).__name__}: {e}")
        return None


if __name__ == "__main__":
    import sqlite3
    conn = sqlite3.connect("reddit_videos.db")
    if len(sys.argv) > 1:
        ids = [int(a) for a in sys.argv[1:]]
        rows = [conn.execute("SELECT id, hook, script FROM video_jobs WHERE id = ?", (i,)).fetchone() for i in ids]
    else:
        rows = conn.execute("SELECT id, hook, script FROM video_jobs WHERE script IS NOT NULL "
                            "ORDER BY id DESC LIMIT 3").fetchall()
    for row in filter(None, rows):
        job_id, hook, script = row
        print(f"\n=== Job {job_id}: {hook}")
        generate_ai_thumbnail(hook, script, job_id)
