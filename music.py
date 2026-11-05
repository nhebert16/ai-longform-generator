"""
music.py — Mixes background music under the narration at low volume.

Two options:
  1. Use your own music file — drop any MP3/WAV into assets/music/
     and set BACKGROUND_MUSIC_PATH in your .env
  2. Auto-generate a simple ambient drone — no file needed, uses numpy

The generated ambient track is a layered low drone — subtle enough to not
distract from the narration but fills the silence and adds production value.

Music volume is set to 12% of the narration volume by default — just enough
to feel present without competing with the voice.
"""

import os
import wave
import numpy as np
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

MUSIC_PATH = os.getenv("BACKGROUND_MUSIC_PATH", "")  # Optional: path to your own music file
MUSIC_VOLUME = float(os.getenv("MUSIC_VOLUME", "0.12"))  # 12% volume
SAMPLE_RATE = 44100

GENERATED_MUSIC_PATH = Path("assets/music/ambient_drone.wav")


def _sine(freq: float, duration: float, amp: float) -> np.ndarray:
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
    return amp * np.sin(2 * np.pi * freq * t)


def _triangle_wave(freq: float, duration: float, amp: float) -> np.ndarray:
    """Triangle wave — softer than square, slightly richer than sine."""
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
    return amp * (2 / np.pi) * np.arcsin(np.sin(2 * np.pi * freq * t))


def generate_ambient_track(duration_seconds: float) -> str:
    """
    Generates a subtle ambient drone track of the given duration.
    Layered sine waves at low frequencies — calm, slightly tense feel.
    Cached per duration (rounded to nearest 10s).

    Returns path to the generated WAV file.
    """
    Path("assets/music").mkdir(parents=True, exist_ok=True)

    # Round duration up to nearest 10s for reusability
    rounded_duration = max(30, int(np.ceil(duration_seconds / 10) * 10))
    cache_path = Path(f"assets/music/drone_{rounded_duration}s.wav")

    if cache_path.exists():
        return str(cache_path)

    print(f"  [Music] Generating {rounded_duration}s ambient track...")

    dur = float(rounded_duration)

    # Layer 1: Deep root drone (A1 = 55Hz) — felt more than heard
    layer1 = _sine(55.0, dur, amp=0.25)

    # Layer 2: Fifth above (E2 = 82.4Hz)
    layer2 = _sine(82.41, dur, amp=0.15)

    # Layer 3: Slow modulated mid tone (A2 = 110Hz with subtle tremolo)
    t = np.linspace(0, dur, int(SAMPLE_RATE * dur), endpoint=False)
    tremolo = 1.0 + 0.08 * np.sin(2 * np.pi * 0.3 * t)  # 0.3Hz tremolo
    layer3 = _sine(110.0, dur, amp=0.12) * tremolo

    # Layer 4: Very soft high shimmer (A4 = 440Hz at barely audible level)
    layer4 = _sine(440.0, dur, amp=0.02)

    # Combine layers
    combined = layer1 + layer2 + layer3 + layer4

    # Apply gentle fade in/out (2 seconds each)
    fade_samples = int(2.0 * SAMPLE_RATE)
    fade_in = np.linspace(0, 1, fade_samples)
    fade_out = np.linspace(1, 0, fade_samples)
    combined[:fade_samples] *= fade_in
    combined[-fade_samples:] *= fade_out

    # Normalize to full WAV level — volume is applied by video_builder
    max_val = np.max(np.abs(combined))
    if max_val > 0:
        combined = combined / max_val * 0.9

    pcm = (combined * 32767).astype(np.int16)

    with wave.open(str(cache_path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm.tobytes())

    print(f"  [Music] Ambient track saved: {cache_path}")
    return str(cache_path)


def get_music_path(duration_seconds: float) -> str:
    """
    Returns the path to background music.
    Priority:
      1. BACKGROUND_MUSIC_PATH in .env
      2. Any MP3/WAV/M4A in assets/music/ (skips generated drone files)
      3. Auto-generated ambient drone
    """
    # 1. Explicit .env override
    if MUSIC_PATH and Path(MUSIC_PATH).exists():
        print(f"  [Music] Using .env path: {MUSIC_PATH}")
        return MUSIC_PATH

    # 2. Scan assets/music/ — list everything to help debug
    music_dir = Path("assets/music")
    if music_dir.exists():
        all_files = list(music_dir.iterdir())
        audio_exts = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".MP3", ".WAV", ".M4A"}
        candidates = [
            f for f in all_files
            if f.suffix.lower() in {e.lower() for e in audio_exts}
            and "drone_" not in f.name
            and "ambient_drone" not in f.name
        ]
        if candidates:
            chosen = sorted(candidates)[0]
            print(f"  [Music] Found: {chosen}")
            return str(chosen)
        else:
            print(f"  [Music] assets/music/ exists but no user tracks found.")
            print(f"  [Music] Files in folder: {[f.name for f in all_files]}")
    else:
        print(f"  [Music] assets/music/ folder not found")

    # 3. Fallback: generate drone
    print("  [Music] Falling back to generated ambient drone")
    return generate_ambient_track(duration_seconds)


if __name__ == "__main__":
    path = get_music_path(120)
    print(f"\nBackground music ready: {path}")
    print("You can open this WAV in any media player to preview it.")
    print("\nTo use your own music instead, add this to your .env:")
    print("  BACKGROUND_MUSIC_PATH=assets/music/your_track.mp3")
