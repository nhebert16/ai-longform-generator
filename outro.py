"""
outro.py — Generates a branded outro card image and a short chime sound.

The outro plays for ~3 seconds at the end of every video:
  - Branded logo card (channel name + "Follow for more" CTA)
  - A short 2-note chime that plays as it appears

The chime is synthesized using numpy + wave — no audio files needed.
The logo card is rendered with Pillow.

Both are cached in assets/outro/ so they're only generated once.
"""

import os
import wave
import struct
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

FONT_PATH = os.getenv("FONT_PATH", "assets/fonts/Montserrat-Bold.ttf")
CHANNEL_NAME = os.getenv("CHANNEL_NAME", "Reddit Stories")  # Add this to your .env

OUTRO_DIR = Path("assets/outro")
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "output"))

# Outro card dimensions — match video output size
WIDTH = 720
HEIGHT = 1280

# Chime settings
SAMPLE_RATE = 44100
CHIME_DURATION = 2.5        # seconds total
FADE_OUT_DURATION = 0.8     # seconds to fade out at end


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except Exception:
        return ImageFont.load_default()


def generate_outro_card(force: bool = False) -> str:
    """
    Renders the outro logo card as a PNG.
    Pass force=True to regenerate even if the cached file exists.
    Returns the path to the image.
    """
    OUTRO_DIR.mkdir(parents=True, exist_ok=True)
    card_path = OUTRO_DIR / "outro_card.png"

    if card_path.exists() and not force:
        return str(card_path)

    print("  [Outro] Generating outro card...")

    img = Image.new("RGB", (WIDTH, HEIGHT), (10, 10, 10))
    draw = ImageDraw.Draw(img)

    # Deep dark gradient background (top = dark navy, bottom = near-black)
    for y in range(HEIGHT):
        t = y / HEIGHT
        r = int(8 + 6 * t)
        g = int(8 + 4 * t)
        b = int(18 + 10 * t)
        draw.line([(0, y), (WIDTH, y)], fill=(r, g, b))

    cx = WIDTH // 2
    cy = HEIGHT // 2 - 80

    # Glow halo behind logo circle
    for radius in range(200, 130, -5):
        alpha = int(18 * (1 - (radius - 130) / 70))
        glow_color = (255, 69, 0, alpha)
        # Draw as slightly transparent ellipse using a separate RGBA layer
        glow_layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow_layer)
        gd.ellipse([cx - radius, cy - radius, cx + radius, cy + radius],
                   fill=glow_color)
        img_rgba = img.convert("RGBA")
        img_rgba = Image.alpha_composite(img_rgba, glow_layer)
        img = img_rgba.convert("RGB")
        draw = ImageDraw.Draw(img)

    # Main logo circle
    logo_radius = 130
    draw.ellipse(
        [cx - logo_radius, cy - logo_radius, cx + logo_radius, cy + logo_radius],
        fill=(255, 69, 0)
    )
    # Inner white ring
    draw.ellipse(
        [cx - logo_radius + 6, cy - logo_radius + 6,
         cx + logo_radius - 6, cy + logo_radius - 6],
        outline=(255, 255, 255), width=3
    )

    # Bold "R" centered in circle
    font_r = _load_font(148)
    r_bbox = font_r.getbbox("R")
    r_w = r_bbox[2] - r_bbox[0]
    r_h = r_bbox[3] - r_bbox[1]
    draw.text((cx - r_w // 2, cy - r_h // 2 - 8), "R",
              font=font_r, fill=(255, 255, 255))

    # Channel name — large, white, tracked
    font_name = _load_font(68)
    name_bbox = font_name.getbbox(CHANNEL_NAME)
    name_w = name_bbox[2] - name_bbox[0]
    draw.text(((WIDTH - name_w) // 2, cy + 160),
              CHANNEL_NAME, font=font_name, fill=(255, 255, 255))

    # Thin orange accent line under name
    line_y = cy + 248
    draw.rectangle(
        [(cx - 100, line_y), (cx + 100, line_y + 4)],
        fill=(255, 69, 0)
    )

    # CTA subtitle
    font_cta = _load_font(44)
    cta = "Follow for daily stories"
    cta_bbox = font_cta.getbbox(cta)
    cta_w = cta_bbox[2] - cta_bbox[0]
    draw.text(((WIDTH - cta_w) // 2, cy + 274),
              cta, font=font_cta, fill=(180, 180, 180))

    # Platform line at bottom
    font_icons = _load_font(32)
    platforms = "TikTok  •  Instagram  •  YouTube"
    plat_bbox = font_icons.getbbox(platforms)
    plat_w = plat_bbox[2] - plat_bbox[0]
    draw.text(((WIDTH - plat_w) // 2, HEIGHT - 140),
              platforms, font=font_icons, fill=(90, 90, 90))

    img.save(str(card_path), "PNG")
    print(f"  [Outro] Card saved: {card_path}")
    return str(card_path)


def _sine_wave(freq: float, duration: float, amplitude: float = 0.6,
               sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Generate a sine wave at a given frequency."""
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    return amplitude * np.sin(2 * np.pi * freq * t)


def _apply_envelope(samples: np.ndarray, attack: float = 0.01,
                    decay: float = 0.1, sustain: float = 0.7,
                    release: float = 0.3, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Apply an ADSR envelope to shape the sound naturally."""
    n = len(samples)
    attack_n = int(attack * sample_rate)
    decay_n = int(decay * sample_rate)
    release_n = int(release * sample_rate)
    sustain_n = n - attack_n - decay_n - release_n

    envelope = np.concatenate([
        np.linspace(0, 1, attack_n),                    # attack
        np.linspace(1, sustain, decay_n),               # decay
        np.ones(max(sustain_n, 0)) * sustain,           # sustain
        np.linspace(sustain, 0, release_n),             # release
    ])

    envelope = envelope[:n]
    if len(envelope) < n:
        envelope = np.pad(envelope, (0, n - len(envelope)))

    return samples * envelope


def generate_outro_chime() -> str:
    """
    Generates a smooth, soft fade tone — similar to TikTok/Instagram Reels outro.
    A warm low note that fades in gently and decays slowly. No attack transients.
    """
    OUTRO_DIR.mkdir(parents=True, exist_ok=True)
    chime_path = OUTRO_DIR / "outro_chime.wav"

    if chime_path.exists():
        return str(chime_path)

    print("  [Outro] Generating soft fade tone...")

    duration = 3.0
    sr = SAMPLE_RATE
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)

    # Warm tone — low frequency with very soft harmonics
    # Using D3 (146.8Hz) — warm and unobtrusive
    base = 0.4 * np.sin(2 * np.pi * 146.83 * t)
    h2   = 0.08 * np.sin(2 * np.pi * 293.66 * t)
    h3   = 0.02 * np.sin(2 * np.pi * 440.0  * t)
    tone = base + h2 + h3

    # Smooth envelope — very slow fade in, exponential decay
    # No sharp attack at all — this is what makes it soft
    n = len(tone)
    fade_in  = int(0.4 * sr)   # 400ms fade in
    fade_out = int(2.4 * sr)   # 2.4s exponential decay

    env = np.ones(n)
    env[:fade_in] = np.linspace(0.0, 1.0, fade_in) ** 2  # smooth quadratic in
    decay_curve = np.exp(-np.linspace(0, 5, fade_out))     # natural exponential decay
    env[fade_in:fade_in + fade_out] = decay_curve[:n - fade_in]
    env[fade_in + fade_out:] = 0.0

    tone = tone * env

    # Very low volume — whisper level
    tone *= 0.3

    # Final normalize
    peak = np.max(np.abs(tone))
    if peak > 0:
        tone = tone / peak * 0.35

    pcm = (tone * 32767).astype(np.int16)

    with wave.open(str(chime_path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())

    print(f"  [Outro] Soft tone saved: {chime_path}")
    return str(chime_path)


def prepare_outro_assets(force: bool = False) -> dict:
    """
    Ensures both outro assets exist and returns their paths.
    Call this once at startup or before the first video render.
    Pass force=True to delete the cached card and regenerate it fresh
    (use this whenever you update the logo design).
    """
    return {
        "card_path": generate_outro_card(force=force),
        "chime_path": generate_outro_chime(),
    }


if __name__ == "__main__":
    assets = prepare_outro_assets()
    print(f"\nOutro assets ready:")
    print(f"  Card:  {assets['card_path']}")
    print(f"  Chime: {assets['chime_path']}")
    print("\nOpen assets/outro/outro_card.png to preview the logo card.")
