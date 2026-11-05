"""
video_builder_longform.py — MoviePy v2, 1920x1080 horizontal long-form

Fixes applied:
- Intro Reddit post card (non-opaque dark card, awards row)
- Music always plays via auto-resolved get_music_path()
- Subtitles moved up to SUB_Y=860 so they never get clipped
- Outro always uses assets/outro/outro_animated_final.mp4
"""

import os
import textwrap
import numpy as np
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

from moviepy import (
    VideoFileClip,
    AudioFileClip,
    ImageClip,
    TextClip,
    CompositeVideoClip,
    ColorClip,
    concatenate_audioclips,
    concatenate_videoclips,
    AudioArrayClip,
    CompositeAudioClip,
)
import moviepy.video.fx as vfx

from music import get_music_path
from post_card import render_post_card
from thumbnail import extract_thumbnail

load_dotenv()

BACKGROUND_PATH  = os.getenv("BACKGROUND_VIDEO_PATH", "assets/background.mp4")
FONT_PATH        = os.getenv("FONT_PATH", "assets/fonts/Montserrat-Bold.ttf")
SUB_FONT_PATH    = "assets/fonts/Bangers-Regular.ttf"
OUTPUT_DIR       = Path(os.getenv("OUTPUT_DIR", "output"))
MUSIC_VOLUME     = float(os.getenv("MUSIC_VOLUME", "0.2"))  # Reduced by 20%
MUSIC_ENABLED    = os.getenv("BACKGROUND_MUSIC_ENABLED", "true").lower() != "false"

# Permanent branded outro
OUTRO_VIDEO_PATH = Path("assets/outro/outro_animated_final.mp4")

WIDTH  = 1920
HEIGHT = 1080
FPS    = 30

VERDICT_DURATION    = 0.0
OUTRO_DURATION      = 14.5   # Longer outro for long-form
INTRO_CARD_DURATION = 4.0   # Slightly longer for 16:9

CARD_MARGIN = 60

# Long-form subtitle style — smaller font, bottom third of screen
SUB_FONT_SIZE    = 82
SUB_COLOR        = "white"
SUB_STROKE_COLOR = "black"
SUB_STROKE_WIDTH = 6
WORDS_PER_SUBTITLE = 3      # 3 words per subtitle for long-form pacing
SUB_Y            = 820      # Bottom third, below card when visible
CARD_W_LF        = 900      # Post card width in 16:9 layout
CARD_X           = 80       # Post card left-aligned with margin


def build_video(job_id: int, audio_path: str, word_timestamps: list[dict],
                hook: str, post_cards: list[dict] = None,
                top_comment: str = None, comment_bait: str = None,
                subreddit: str = "", music_path: str = None,
                outro_card_path: str = None, outro_chime_path: str = None,
                reddit_url: str = "",
                upvotes: str = "", comments: str = "",
                chapters: list[dict] = None) -> str | None:

    video_dir = OUTPUT_DIR / "videos"
    video_dir.mkdir(parents=True, exist_ok=True)
    output_path = video_dir / f"job_{job_id}_lf.mp4"

    try:
        narration = AudioFileClip(audio_path)
        narration_duration = narration.duration
        total_duration = narration_duration + 1.0 + OUTRO_DURATION  # +1s fade

        bg = _build_background(total_duration)
        # Fade bg to black over the 1s before the outro
        try:
            bg = bg.with_effects([vfx.FadeOut(duration=1.0)])
        except Exception as _fe:
            print(f"  [!] BG fadeout failed: {_fe}")

        # Dynamic intro card duration — stays on screen until the title is fully read.
        # We expand abbreviations the same way TTS does so word count matches timestamps.
        import re
        def _expand_for_count(text):
            abbrevs = [
                (r'\bAITA\b', 'Am I the asshole'),
                (r'\bWIBTA\b', 'Would I be the asshole'),
                (r'\bNTA\b', 'Not the asshole'),
                (r'\bYTA\b', 'You are the asshole'),
                (r'\bSIL\b', 'sister in law'),
                (r'\bBIL\b', 'brother in law'),
                (r'\bMIL\b', 'mother in law'),
                (r'\bFIL\b', 'father in law'),
                (r'\bSTBX\b', 'soon to be ex'),
                (r'\bSTBXH\b', 'soon to be ex husband'),
                (r'\bSTBXW\b', 'soon to be ex wife'),
            ]
            for pattern, replacement in abbrevs:
                text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
            return text

        expanded_hook = _expand_for_count(hook.strip())
        hook_words = expanded_hook.lower().split()
        hook_word_count = len(hook_words)

        intro_card_duration = INTRO_CARD_DURATION  # default
        if word_timestamps and hook_word_count > 0:
            hook_clean = [re.sub(r"[^\w]", "", w) for w in hook_words]
            matched = 0
            for i, ts in enumerate(word_timestamps[:hook_word_count + 8]):
                ts_word = re.sub(r"[^\w]", "", ts["word"].lower())
                if matched < len(hook_clean) and ts_word == hook_clean[matched]:
                    matched += 1
                if matched >= len(hook_clean):
                    # Use end time of last title word + buffer — same as shorts
                    title_read_end = word_timestamps[min(i, len(word_timestamps)-1)]["end"] + 0.5
                    intro_card_duration = max(INTRO_CARD_DURATION, title_read_end)
                    break

        print(f"  [VideoBuilder] Intro card: {intro_card_duration:.2f}s ({hook_word_count} title words)")

        # Intro Reddit post card — left-aligned in 16:9 layout
        intro_clips = _build_intro_card(
            job_id=job_id,
            title=hook,
            subreddit=subreddit or "r/AITA",
            upvotes=upvotes,
            comments=comments,
            duration=intro_card_duration,
        )

        # Log chapter timestamps if provided
        if chapters:
            print(f"  [VideoBuilder] {len(chapters)} chapters:")
            for ch in chapters:
                t = ch.get("start_seconds", 0)
                mm, ss = divmod(t, 60)
                print(f"    {mm:02d}:{ss:02d} {ch['name']}")

        # No body cards — intro post card is the only overlay
        card_clips = []

        subtitle_clips = _build_subtitles(word_timestamps, intro_end=intro_card_duration)

        # Fade handled directly on bg clip above via vfx.FadeOut
        FADE_DUR         = 1.0
        fade_black_clips = []

        # Outro starts after the fade
        outro_clips  = []
        outro_audio  = None
        outro_start  = narration_duration + FADE_DUR
        if OUTRO_VIDEO_PATH.exists():
            outro_clips, outro_audio = _build_outro_video(outro_start)
        elif outro_card_path:
            outro_clips = _build_outro(outro_card_path, OUTRO_DURATION, start=outro_start)

        # Audio — music auto-resolves unless BACKGROUND_MUSIC_ENABLED=false
        silence_end = AudioArrayClip(
            np.zeros((max(1, int((FADE_DUR + OUTRO_DURATION) * 44100)), 2)),
            fps=44100
        ).with_duration(FADE_DUR + OUTRO_DURATION)

        full_narration = concatenate_audioclips([narration, silence_end])

        if not music_path and MUSIC_ENABLED:
            music_path = get_music_path(total_duration)
        elif not MUSIC_ENABLED:
            print("  [Music] Disabled (BACKGROUND_MUSIC_ENABLED=false) — narration only")

        final_audio = full_narration
        if music_path:
            music_audio = _build_music_track(music_path, total_duration)
            if music_audio:
                final_audio = CompositeAudioClip([music_audio, full_narration])

        # Mix in outro audio (the static/chime sounds from the outro MP4)
        if outro_audio:
            try:
                final_audio = CompositeAudioClip([final_audio, outro_audio])
            except Exception as e:
                print(f"  [!] Outro audio mix failed: {e}")

        if outro_chime_path:
            try:
                chime = AudioFileClip(outro_chime_path).with_start(outro_start)
                final_audio = CompositeAudioClip([final_audio, chime])
            except Exception as e:
                print(f"  [!] Chime mix failed: {e}")

        all_clips = [bg] + intro_clips + card_clips + subtitle_clips + fade_black_clips + outro_clips
        final = CompositeVideoClip(all_clips, size=(WIDTH, HEIGHT))
        final = final.with_audio(final_audio).with_duration(total_duration)

        # Determine preset from write_videofile args below
        _preset  = "medium"
        _bitrate = "16000k"
        print(f"  [VideoBuilder] Rendering {total_duration:.1f}s at {WIDTH}x{HEIGHT}...")
        print(f"  [VideoBuilder] Quality: preset={_preset}  bitrate={_bitrate}  audio=320k")

        final.write_videofile(
            str(output_path),
            fps=FPS,
            codec="libx264",
            audio_codec="aac",
            audio_bitrate="320k",
            bitrate="16000k",  # 16Mbps — YouTube recommends 15-20Mbps for 1080p60
            threads=4,
            preset="medium",   # better compression quality vs ultrafast
            logger="bar",
        )

        _write_post_log(job_id, str(output_path), reddit_url, hook)
        print(f"  [✓] Video saved: {output_path}")

        # Extract first frame with post card visible as YouTube thumbnail
        extract_thumbnail(str(output_path), job_id, timestamp=1.0)

        return str(output_path)

    except Exception as e:
        print(f"  [!] Video build failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def _write_post_log(job_id: int, video_path: str, reddit_url: str, hook: str):
    log_path = OUTPUT_DIR / "post_log.txt"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] Job {job_id}\n")
        f.write(f"  Video : {video_path}\n")
        f.write(f"  Post  : {reddit_url}\n")
        f.write(f"  Hook  : {hook}\n\n")
    print(f"  [Log] Entry written to {log_path}")


# ── INTRO CARD ────────────────────────────────────────────────────

def _build_intro_card(job_id, title, subreddit, upvotes, comments, duration=None):
    """
    Builds intro card without zoom effect.
    Card is displayed at normal 100% scale for the full intro duration.
    Award bounce animation is baked into the frames from post_card.py.
    duration — if provided, overrides INTRO_CARD_DURATION for single-frame cards.
    """
    card_duration = duration if duration is not None else INTRO_CARD_DURATION
    try:
        result = render_post_card(
            job_id=job_id,
            title=title,
            subreddit=subreddit,
            upvotes=upvotes,
            comments=comments,
            animated=True,
            duration=card_duration,
        )

        # Resolve frames list or single path
        if isinstance(result, list):
            frames = result   # [(path, start, dur), ...]
        else:
            frames = [(result, 0, card_duration)]

        clips = []

        for path, start, dur in frames:
            img = ImageClip(path)
            # Extend each frame by 1 frame (1/30s) to close any compositing gap
            # that causes flickering between adjacent frames
            padded_dur = dur + (1 / 30)
            # Center card in 16:9 frame
            x_pos = (WIDTH - img.w) // 2
            y_pos = (HEIGHT - img.h) // 2
            clips.append(img.with_start(start).with_duration(dur + (1/30))
                            .with_position((x_pos, y_pos)))

        return clips
    except Exception as e:
        print(f"  [!] Intro card failed: {e}")
        import traceback; traceback.print_exc()
        return []
        print(f"  [!] Intro card failed: {e}")
        import traceback; traceback.print_exc()
        return []



# ── OUTRO ─────────────────────────────────────────────────────────

def _build_outro_video(start):
    """Use the permanent pre-rendered branded outro video, scaled to 1920x1080."""
    try:
        clip = VideoFileClip(str(OUTRO_VIDEO_PATH), audio=True)
        # Scale to fill 1920x1080 — crop if aspect ratio differs
        clip_aspect = clip.w / clip.h
        target_aspect = WIDTH / HEIGHT
        if abs(clip_aspect - target_aspect) > 0.01:
            if clip_aspect > target_aspect:
                new_w = int(clip.h * target_aspect)
                x1 = (clip.w - new_w) // 2
                clip = clip.cropped(x1=x1, y1=0, x2=x1+new_w, y2=clip.h)
            else:
                new_h = int(clip.w / target_aspect)
                y1 = (clip.h - new_h) // 2
                clip = clip.cropped(x1=0, y1=y1, x2=clip.w, y2=y1+new_h)
        clip = clip.resized((WIDTH, HEIGHT)).with_start(start).with_position((0, 0))
        print(f"  [Outro] Scaled to {WIDTH}x{HEIGHT}")
        return [clip], clip.audio.with_start(start) if clip.audio else None
    except Exception as e:
        print(f"  [!] Outro video failed: {e}")
        return [], None


def _build_outro(outro_card_path, duration, start):
    """Fallback static image outro if the video file is missing."""
    try:
        fade_duration = 0.6
        steps = 12
        clips = []
        for i in range(steps):
            t = i / steps
            clips.append(ImageClip(outro_card_path)
                         .resized((WIDTH, HEIGHT))
                         .with_start(start + t * fade_duration)
                         .with_duration(fade_duration / steps + 0.01)
                         .with_position((0, 0)).with_opacity(t))
        clips.append(ImageClip(outro_card_path)
                     .resized((WIDTH, HEIGHT))
                     .with_start(start + fade_duration)
                     .with_duration(duration - fade_duration)
                     .with_position((0, 0)))
        return clips
    except Exception as e:
        print(f"  [!] Outro card failed: {e}")
        return []


# ── BACKGROUND ───────────────────────────────────────────────────

def _build_background(duration):
    import random
    bg_video = VideoFileClip(BACKGROUND_PATH, audio=False)

    bg_aspect     = bg_video.w / bg_video.h
    target_aspect = WIDTH / HEIGHT

    if bg_aspect > target_aspect:
        new_w    = int(bg_video.h * target_aspect)
        x1       = (bg_video.w - new_w) // 2
        bg_video = bg_video.cropped(x1=x1, y1=0, x2=x1 + new_w, y2=bg_video.h)
    else:
        new_h    = int(bg_video.w / target_aspect)
        y1       = (bg_video.h - new_h) // 2
        bg_video = bg_video.cropped(x1=0, y1=y1, x2=bg_video.w, y2=y1 + new_h)

    bg_video = bg_video.resized((WIDTH, HEIGHT))

    # Pick a random start point, ensuring enough video remains for full duration
    # Skip first 3s to avoid fade-from-black in most source footage
    BG_SKIP  = 3.0
    max_start = max(BG_SKIP, bg_video.duration - duration)
    if max_start > BG_SKIP:
        bg_start = random.uniform(BG_SKIP, max_start)
        print(f"  [BG] Random start: {bg_start:.1f}s (video: {bg_video.duration:.1f}s, need: {duration:.1f}s)")
    else:
        bg_start = BG_SKIP
        print(f"  [BG] Video too short for random start — looping from {BG_SKIP}s")

    if bg_video.duration - bg_start < duration:
        # Not enough remaining — use what we have then loop from beginning
        part1     = bg_video.subclipped(bg_start)
        remaining = duration - part1.duration
        loops     = int(np.ceil(remaining / bg_video.duration)) + 1
        looped    = concatenate_videoclips([bg_video] * loops).subclipped(0, remaining)
        bg_video  = concatenate_videoclips([part1, looped]).subclipped(0, duration)
    else:
        bg_video = bg_video.subclipped(bg_start, bg_start + duration)

    overlay = (ColorClip(size=(WIDTH, HEIGHT), color=(0, 0, 0))
               .with_opacity(0.45).with_duration(duration))

    return CompositeVideoClip([bg_video, overlay], size=(WIDTH, HEIGHT))


# ── BODY CARDS ───────────────────────────────────────────────────

def _build_card_overlays(post_cards, word_timestamps, narration_duration):
    if not post_cards or not word_timestamps:
        return []

    total_words    = len(word_timestamps)
    num_cards      = len(post_cards)
    clips          = []
    words_per_card = max(1, total_words // num_cards)

    for i, card in enumerate(post_cards):
        start_idx  = min(i * words_per_card, total_words - 1)
        end_idx    = min((i + 1) * words_per_card - 1 if i < num_cards - 1 else total_words - 1,
                         total_words - 1)
        start_time = word_timestamps[start_idx]["start"]
        end_time   = word_timestamps[end_idx]["end"]
        duration   = max(end_time - start_time, 0.5)

        try:
            img_clip = ImageClip(card["image_path"])
            scale    = (WIDTH - CARD_MARGIN * 2) / img_clip.w
            img_clip = img_clip.resized(scale)
            x_pos    = (WIDTH  - img_clip.w) // 2
            y_pos    = (HEIGHT - img_clip.h) // 2
            clips.append(img_clip.with_start(start_time).with_duration(duration)
                         .with_position((x_pos, y_pos)))
        except Exception as e:
            print(f"  [!] Card load failed: {e}")

    return clips


# ── SUBTITLES ────────────────────────────────────────────────────

def _build_subtitles(word_timestamps, intro_end: float = 0.0):
    clips  = []

    # Sentence-aware chunking — never group words across a sentence boundary.
    # Split on sentence-ending punctuation first, then chunk within each sentence.
    import re as _re
    chunks = []
    sentence_buf = []
    for ts in word_timestamps:
        sentence_buf.append(ts)
        # If this word ends a sentence, flush the buffer into chunks
        if _re.search(r'[.!?]$', ts["word"].strip()):
            for i in range(0, len(sentence_buf), WORDS_PER_SUBTITLE):
                chunks.append(sentence_buf[i:i + WORDS_PER_SUBTITLE])
            sentence_buf = []
    # Flush any remaining words
    if sentence_buf:
        for i in range(0, len(sentence_buf), WORDS_PER_SUBTITLE):
            chunks.append(sentence_buf[i:i + WORDS_PER_SUBTITLE])

    for idx, chunk in enumerate(chunks):
        text  = " ".join(w["word"] for w in chunk)
        start = chunk[0]["start"]
        # Whisper: use next word's start as the cut point — perceptually tight.
        # For the last chunk fall back to Whisper's own end time.
        if idx + 1 < len(chunks):
            # Cap at next chunk start but never exceed word's own end + 0.1s buffer
            end = min(chunks[idx + 1][0]["start"], chunk[-1]["end"] + 0.1)
        else:
            end = chunk[-1]["end"]
        duration = max(end - start, 0.05)
        wrapped  = "\n".join(textwrap.wrap(text, width=24))

        # During intro card: show subtitles below the card so title is readable
        if start < intro_end:
            position = ("center", 920)   # below card in 16:9 layout
        else:
            position = ("center", SUB_Y)

        try:
            txt = TextClip(
                text=text,
                font_size=SUB_FONT_SIZE,
                font=SUB_FONT_PATH,
                color=SUB_COLOR,
                stroke_color=SUB_STROKE_COLOR,
                stroke_width=SUB_STROKE_WIDTH,
                method="caption",
                size=(WIDTH - 200, 200),  # centered with margins for 16:9
                text_align="center",
            )
            x_pos = (WIDTH - txt.w) // 2
            y_pos = position[1]
            txt = (txt.with_start(start)
                      .with_duration(duration)
                      .with_position((x_pos, y_pos)))
            clips.append(txt)
        except Exception as e:
            print(f"  [!] Subtitle clip failed: {e}")

    return clips


# ── VERDICT CARD ─────────────────────────────────────────────────

def _build_verdict_card(text, duration, start):
    card_height = 280
    card_bg = (ColorClip(size=(WIDTH, card_height), color=(15, 15, 15))
               .with_opacity(0.92).with_duration(duration))

    wrapped = "\n".join(textwrap.wrap(text, width=34))
    txt = (TextClip(
        text=wrapped,
        font_size=VERDICT_FONT_SIZE,
        font=FONT_PATH,
        color="white",
        method="caption",
        size=(WIDTH - 60, None),
        text_align="center",
    ).with_duration(duration).with_position("center"))

    label = (TextClip(
        text="YOUR VERDICT?",
        font_size=26,
        font=FONT_PATH,
        color="#FF4500",
    ).with_duration(duration).with_position(("center", 18)))

    card = (CompositeVideoClip([card_bg, label, txt], size=(WIDTH, card_height))
            .with_position((0, HEIGHT - card_height))
            .with_start(start))
    return card


# ── MUSIC ────────────────────────────────────────────────────────

def _build_music_track(music_path, total_duration):
    try:
        music = AudioFileClip(music_path)
        try:
            music = music.with_volume_scaled(MUSIC_VOLUME)
        except AttributeError:
            music = music.multiply_volume(MUSIC_VOLUME)
        if music.duration < total_duration:
            # Build looped track with crossfade between iterations
            LOOP_CF = 3.0  # 3s crossfade between loops
            sr_loop = 44100
            samples = music.to_soundarray(fps=sr_loop)
            cf_samp = int(LOOP_CF * sr_loop)
            target_samp = int(total_duration * sr_loop)

            def xfade(a, b, cf):
                fo = np.linspace(1, 0, cf)[:, None] if a.ndim > 1 else np.linspace(1, 0, cf)
                fi = np.linspace(0, 1, cf)[:, None] if b.ndim > 1 else np.linspace(0, 1, cf)
                return np.concatenate([a[:-cf], a[-cf:]*fo + b[:cf]*fi, b[cf:]])

            blended = samples.copy()
            while len(blended) < target_samp + cf_samp:
                blended = xfade(blended, samples, min(cf_samp, len(samples)//2))
            blended = blended[:target_samp]
            from moviepy import AudioArrayClip as _AAC
            music = _AAC(blended.astype(np.float32), fps=sr_loop).with_duration(total_duration)
            print(f"  [Music] Looped with {LOOP_CF}s crossfade to {total_duration:.1f}s")
        else:
            music = music.subclipped(0, total_duration)

        # Manually apply fade using AudioArrayClip
        # Read audio samples, apply linear fade from 100%→10% over last 7s
        try:
            FADE_DURATION = 7.0
            sr = 44100
            samples = music.to_soundarray(fps=sr)  # shape: (n_samples, n_channels)
            n_total = samples.shape[0]
            fade_samples = int(FADE_DURATION * sr)
            fade_start   = n_total - fade_samples

            # Build per-sample multiplier: 1.0 until fade_start, then 1.0→0.10
            multiplier = np.ones(n_total, dtype=np.float32)
            fade_range = np.linspace(1.0, 0.10, fade_samples, dtype=np.float32)
            multiplier[fade_start:] = fade_range

            # Apply to all channels
            if samples.ndim == 2:
                samples = samples * multiplier[:, np.newaxis]
            else:
                samples = samples * multiplier

            from moviepy import AudioArrayClip as AAC
            music = AAC(samples, fps=sr).with_duration(total_duration)
            print(f"  [Music] Fade applied: 100%→10% over last {FADE_DURATION}s")
        except Exception as e:
            print(f"  [Music] Fade failed ({e}), using audio_fadeout fallback")
            try:
                music = music.audio_fadeout(7.0)
            except Exception:
                pass

        print(f"  [Music] Track loaded at volume {MUSIC_VOLUME}: {music_path}")
        return music
    except Exception as e:
        print(f"  [!] Music load failed: {e}")
        return None


def _format_verdict(comment_bait, top_comment):
    if comment_bait and len(comment_bait) > 10:
        return comment_bait
    if top_comment:
        return top_comment[:197] + "..." if len(top_comment) > 200 else top_comment
    return "What do YOU think? Drop your verdict in the comments below"


if __name__ == "__main__":
    print("video_builder.py loaded — call build_video() to render.")
