"""
tts.py — Text-to-speech using Microsoft Edge TTS + Whisper alignment.

Pipeline:
  1. Generate audio with edge-tts (fast, free, high quality)
  2. Run Whisper on the generated audio to get exact per-word timestamps
  3. Fallback to syllable-weighted estimation if Whisper isn't installed

To enable perfect sync:
  pip install openai-whisper

Whisper model sizes (set WHISPER_MODEL in .env):
  tiny   — fastest (~5s extra), less accurate
  base   — good balance (~10-15s extra)  ← default
  small  — most accurate (~25s extra)
"""

import asyncio
import json
import re
from pathlib import Path
from dotenv import load_dotenv
import os
import edge_tts
from mutagen.mp3 import MP3

load_dotenv()

OUTPUT_DIR    = Path(os.getenv("OUTPUT_DIR",      "output"))
TTS_VOICE     = os.getenv("EDGE_TTS_VOICE",       "en-US-GuyNeural")
TTS_RATE      = os.getenv("EDGE_TTS_RATE",        "+30%")
WHISPER_MODEL = os.getenv("WHISPER_MODEL",        "base")

_whisper_model_cache = None


# ── Whisper ────────────────────────────────────────────────────────

def _load_whisper():
    global _whisper_model_cache
    if _whisper_model_cache is not None:
        return _whisper_model_cache
    try:
        import whisper
        print(f"  [TTS] Loading Whisper '{WHISPER_MODEL}' model (first run only)...")
        _whisper_model_cache = whisper.load_model(WHISPER_MODEL)
        print(f"  [TTS] Whisper ready")
        return _whisper_model_cache
    except ImportError:
        print("  [!] Whisper not installed — run: pip install openai-whisper")
        return None
    except Exception as e:
        print(f"  [!] Whisper load error: {e}")
        return None


def _whisper_align(audio_path: str) -> list[dict]:
    """
    Transcribe audio with Whisper and extract real per-word timestamps.
    Returns [] if Whisper is unavailable or fails.
    """
    model = _load_whisper()
    if not model:
        return []
    try:
        import whisper
        print(f"  [TTS] Aligning with Whisper...")
        result = model.transcribe(
            audio_path,
            word_timestamps=True,
            language="en",
            fp16=False,
            verbose=False,
        )
        word_events = []
        for segment in result.get("segments", []):
            for w in segment.get("words", []):
                word = w.get("word", "").strip()
                if word:
                    word_events.append({
                        "word":  word,
                        "start": round(float(w["start"]), 3),
                        "end":   round(float(w["end"]),   3),
                    })
        print(f"  [TTS] Whisper aligned {len(word_events)} words ✓")
        return word_events
    except Exception as e:
        print(f"  [!] Whisper alignment failed: {e}")
        return []


# ── Edge TTS ───────────────────────────────────────────────────────

def _preprocess_script(script: str) -> str:
    """Expand abbreviations and slang before passing to TTS."""
    # Strip age/gender tags like (36F), (24M), (18f) and bare 34F, 24M
    script = re.sub(r'\(\d{1,3}[MmFf]\)', '', script)
    script = re.sub(r'\b\d{1,3}[MF]\b', '', script)
    script = re.sub(r'  +', ' ', script).strip()

    replacements = [
        # AITA verdicts
        (r'\bAITA\b',    'Am I the asshole'),
        (r'\bAITAH\b',   'Am I the asshole'),
        (r'\bWIBTA\b',   'Would I be the asshole'),
        (r'\bWYBTA\b',   'Would you be the asshole'),
        (r'\bNTA\b',     'Not the asshole'),
        (r'\bYTA\b',     'You are the asshole'),
        (r'\bESH\b',     'Everyone sucks here'),
        (r'\bNAH\b',     'No assholes here'),
        (r'\bINFO\b',    'I need more information'),
        # Family
        (r'\bSIL\b',     'sister in law'),
        (r'\bBIL\b',     'brother in law'),
        (r'\bMIL\b',     'mother in law'),
        (r'\bFIL\b',     'father in law'),
        (r'\bDH\b',      'dear husband'),
        (r'\bDW\b',      'dear wife'),
        (r'\bDS\b',      'dear son'),
        (r'\bDD\b',      'dear daughter'),
        (r'\bDP\b',      'dear partner'),
        # Relationship status
        (r'\bSTBXH\b',   'soon to be ex husband'),
        (r'\bSTBXW\b',   'soon to be ex wife'),
        (r'\bSTBX\b',    'soon to be ex'),
        (r'\bXH\b',      'ex husband'),
        (r'\bXW\b',      'ex wife'),
        (r'\bBF\b',      'boyfriend'),
        (r'\bGF\b',      'girlfriend'),
        (r'\bFH\b',      'future husband'),
        (r'\bFW\b',      'future wife'),
        (r'\bSO\b',      'significant other'),
        (r'\bLDR\b',     'long distance relationship'),
        (r'\bNC\b',      'no contact'),
        (r'\bLC\b',      'low contact'),
        (r'\bVLC\b',     'very low contact'),
        (r'\bJNMIL\b',   'just no mother in law'),
        (r'\bSAHM\b',   'stay at home mom'),
        (r'\bSAHD\b',   'stay at home dad'),
        # Common Reddit
        (r'\bOP\b',      'original poster'),
        (r'\bOOTL\b',    'out of the loop'),
        (r'\bIMO\b',     'in my opinion'),
        (r'\bIMHO\b',    'in my honest opinion'),
        (r'\bIIRC\b',    'if I recall correctly'),
        (r'\bTBH\b',     'to be honest'),
        (r'\bTBF\b',     'to be fair'),
        (r'\bNGL\b',     'not gonna lie'),
        (r'\bIRL\b',     'in real life'),
        (r'\bETA\b',     'edited to add'),
        (r'\bTIFU\b',    'today I messed up'),
        (r'\bFWIW\b',    'for what it is worth'),
        (r'\bIANAL\b',   'I am not a lawyer'),
        
    ]
    for pattern, replacement in replacements:
        script = re.sub(pattern, replacement, script)  # case-sensitive — Reddit acronyms only

    # Internet / text lingo — case-insensitive so Idk, idk, IDK all match
    lingo = [
        (r'\bIDK\b',   "I don't know"),
        (r'\bIDC\b',   "I don't care"),
        (r'\bIDE\b',   "I don't even"),
        (r'\bOMG\b',   'oh my god'),
        (r'\bOMFG\b',  'oh my freaking god'),
        (r'\bWTF\b',   'what the heck'),
        (r'\bWTH\b',   'what the heck'),
        (r'\bLOL\b',   'laughing out loud'),
        (r'\bLMAO\b',  'laughing my ass off'),
        (r'\bROFL\b',  'rolling on the floor laughing'),
        (r'\bNVM\b',   'never mind'),
        (r'\bOFC\b',   'of course'),
        (r'\bOBV\b',   'obviously'),
        (r'\bIKR\b',   'i know right'),
        (r'\bSMH\b',   'shaking my head'),
        (r'\bSMFH\b',  'shaking my freaking head'),
        (r'\bFML\b',   'my life is a mess'),
        (r'\bBRB\b',   'be right back'),
        (r'\bTMI\b',   'too much information'),
        (r'\bFYI\b',   'for your information'),
        (r'\bNGL\b',   'not gonna lie'),
        (r'\bTBH\b',   'to be honest'),
        (r'\bIMO\b',   'in my opinion'),
        (r'\bYK\b',    'you know'),
        (r'\bIK\b',    'i know'),
        (r'\betc\.\b',  'etcetera'),
        (r'\betc\b',    'etcetera'),
    ]
    for pattern, replacement in lingo:
        script = re.sub(pattern, replacement, script, flags=re.IGNORECASE)

    return script


async def _generate_audio(script: str, audio_path: str):
    """Generate audio only — timestamps come from Whisper."""
    communicate = edge_tts.Communicate(script, TTS_VOICE, rate=TTS_RATE)
    audio_chunks = []
    async for event in communicate.stream():
        if event["type"] == "audio":
            audio_chunks.append(event["data"])
    with open(audio_path, "wb") as f:
        for chunk in audio_chunks:
            f.write(chunk)


def _estimate_word_timestamps(script: str, total_duration: float) -> list[dict]:
    """
    Syllable-weighted timestamp estimation.
    Used as fallback when Whisper is not installed.
    """
    words = _tokenize(script)
    if not words:
        return []

    lead_in         = total_duration * 0.02
    usable_duration = total_duration * 0.96

    def count_syllables(word):
        word = word.lower().strip("'")
        if len(word) <= 2:
            return 1
        vowels = len(re.findall(r'[aeiouy]+', word))
        if word.endswith('e') and len(word) > 2:
            vowels = max(1, vowels - 1)
        return max(1, vowels)

    weights = []
    for word in words:
        syl   = count_syllables(word)
        pause = 0.4 if word.endswith(',') else (0.8 if word.endswith(('.','!','?')) else 0.0)
        weights.append(syl + pause)

    total_weight = sum(weights)
    timestamps   = []
    cursor       = lead_in
    for word, weight in zip(words, weights):
        dur = (weight / total_weight) * usable_duration
        timestamps.append({
            "word":  word,
            "start": round(cursor, 3),
            "end":   round(cursor + dur, 3),
        })
        cursor += dur
    return timestamps


def _tokenize(script: str) -> list[str]:
    raw_words = script.split()
    clean = []
    for w in raw_words:
        stripped = re.sub(r"^[^\w']+|[^\w']+$", "", w)
        if stripped:
            clean.append(stripped)
    return clean


def _get_duration(audio_path: str) -> float | None:
    try:
        return MP3(audio_path).info.length
    except Exception as e:
        print(f"  [!] Could not read audio duration: {e}")
        return None


# ── Public API ─────────────────────────────────────────────────────

def generate_audio(script: str, job_id: int) -> dict | None:
    """
    Generate TTS audio and return path + per-word timestamps.
    Uses Whisper for perfect sync if installed, otherwise estimates.
    """
    audio_dir = OUTPUT_DIR / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    audio_path = audio_dir / f"job_{job_id}.mp3"

    print(f"  [TTS] Generating audio ({len(script.split())} words) — voice: {TTS_VOICE}")

    script = _preprocess_script(script)

    try:
        asyncio.run(_generate_audio(script, str(audio_path)))
    except Exception as e:
        print(f"  [!] Edge TTS error: {e}")
        import traceback; traceback.print_exc()
        return None

    duration_seconds = _get_duration(str(audio_path))
    if not duration_seconds:
        return None

    print(f"  [✓] Audio: {audio_path} ({duration_seconds:.1f}s)")

    # Whisper for accurate per-word timestamps, fall back to estimation
    word_timestamps = _whisper_align(str(audio_path))
    if not word_timestamps:
        print("  [TTS] Using syllable-weighted estimation (install Whisper for perfect sync)")
        word_timestamps = _estimate_word_timestamps(script, duration_seconds)

    return {
        "audio_path":       str(audio_path),
        "duration_seconds": duration_seconds,
        "word_timestamps":  word_timestamps,
    }


def save_timestamps(word_timestamps: list[dict], job_id: int) -> str:
    ts_dir = OUTPUT_DIR / "timestamps"
    ts_dir.mkdir(parents=True, exist_ok=True)
    ts_path = ts_dir / f"job_{job_id}.json"
    with open(ts_path, "w") as f:
        json.dump(word_timestamps, f, indent=2)
    return str(ts_path)


if __name__ == "__main__":
    test_script = (
        "Here's a wild story from Reddit. A woman went to her sister's wedding "
        "and what happened next shocked everyone in the room."
    )
    result = generate_audio(test_script, job_id=0)
    if result:
        ts_path = save_timestamps(result["word_timestamps"], job_id=0)
        print(f"\nTimestamps: {ts_path}")
        for w in result["word_timestamps"][:8]:
            print(f"  {w['word']:20s}  {w['start']:.3f}s → {w['end']:.3f}s")
