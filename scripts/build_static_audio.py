"""Render static audio deliverables from the manifest (DOJP-35).

Replaces the iMovie workflow: each manifest entry is a timeline of SFX,
TTS, and silence steps, composed with pydub, mastered to the same
TARGET_DBFS as generated plane audio (no volume jump between a static
intro and plane 1), and exported with the same libopus parameters the app
itself uses.

Usage (needs TTS keys in the env, so run through Railway):
    railway run uv run python scripts/build_static_audio.py --entry scanning-again
    railway run uv run python scripts/build_static_audio.py --entry scanning-again --voice ronald
    ... --upload   # PUT the rendered files to {voice_folder}/{name}.{ext} in S3

Outputs land in audio_build/out/{voice}/{name}.{opus,mp3} for audition;
nothing touches S3 without --upload.
"""

import argparse
import asyncio
import io
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pydub import AudioSegment

from app.free_pool import TARGET_DBFS, _normalize_loudness, _trim_silence, export_audio_segment
from app.tts_providers import TTS_PROVIDERS

# Statics render with a code-pinned Inworld model, independent of the
# INWORLD_MODEL_ID env var that steers dynamic plane audio. Deliberate split
# (Callum, 2026-10-02): dynamic tracks chase latency/cost (tts-2-flash
# planned), statics render once and keep the normal model. Change it here,
# not in Railway.
STATIC_INWORLD_MODEL = "inworld-tts-2"

# Voice steering ("prompting") is inline [instruction tags] prepended to the
# text - supported ONLY by non-flash tts-2. Flash ignores the tags and older
# models speak the brackets aloud, so a prompt is attached strictly when the
# rendering model is in this set and dropped (with a warning) otherwise.
PROMPT_CAPABLE_MODELS = {"inworld-tts-2"}

# Non-verbals ([chuckle], [sigh], ...) are one-shot sounds written INLINE in
# the script text where the moment happens. Wider support than steering:
# both tts-2 models render them; anything else would speak the brackets, so
# the renderer strips every [tag] from the text for non-capable models.
NONVERBAL_CAPABLE_MODELS = {"inworld-tts-2", "inworld-tts-2-flash"}

# Statics render ElevenLabs speech (Hamish + the robot) on eleven_v4, pinned
# in code like the Inworld model. v4 (and v3) support audio tags, but with a
# DIFFERENT vocabulary from Inworld's ([laughs] vs [laugh]) - canonical tags
# in the manifest are Inworld-style and translated per provider below.
STATIC_ELEVENLABS_MODEL = "eleven_v4"
ELEVENLABS_TAG_MODELS = {"eleven_v4", "eleven_v3"}
INWORLD_TO_ELEVENLABS_TAGS = {
    "chuckle": "laughs", "laugh": "laughs", "sigh": "sighs",
    "clear throat": "clears throat", "breathe": "exhales", "gasp": "gasps",
}

MANIFEST = REPO / "audio_build" / "static_audio.json"
SFX_DIR = REPO / "assets" / "sfx"
OUT_DIR = REPO / "audio_build" / "out"

# voice folder -> TTS provider (the app's registry maps the other way)
VOICES = {defn["voice_folder"]: name for name, defn in TTS_PROVIDERS.items()}


async def _robot_tts(text: str, manifest: dict) -> AudioSegment:
    """The scanner-robot voice: a fixed ElevenLabs voice, independent of which
    narrator voice is being rendered. Mirrors app/tts_providers/elevenlabs.py's
    request shape with the robot's voice_id from the manifest."""
    import os
    import httpx

    voice_id = manifest["robot_voice_id"]
    api_key = os.environ["ELEVENLABS_TEXT_TO_VOICE_API_KEY"]
    url = (f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
           f"?output_format=opus_48000_64")
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(url, headers={"xi-api-key": api_key},
                              json={"text": text, "model_id": STATIC_ELEVENLABS_MODEL})
    if r.status_code != 200:
        raise RuntimeError(f"robot_tts failed: ElevenLabs {r.status_code}: {r.text[:200]}")
    return AudioSegment.from_file(io.BytesIO(r.content), format="ogg")


def _change_speed(segment: AudioSegment, speed: float) -> AudioSegment:
    """Pitch-preserving tempo change via ffmpeg atempo (pydub's speedup
    chops frames and audibly stutters on speech)."""
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        src, dst = f"{td}/in.wav", f"{td}/out.wav"
        segment.export(src, format="wav")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", src,
                        "-filter:a", f"atempo={speed}", dst], check=True)
        return AudioSegment.from_file(dst)


async def render_entry(name: str, entry: dict, provider: str, manifest: dict, voice: str) -> AudioSegment:
    """Compose one manifest entry's timeline for one TTS provider."""
    from app.main import convert_text_to_speech

    combined = AudioSegment.empty()
    for step in entry["timeline"]:
        if "silence_ms" in step:
            segment = AudioSegment.silent(duration=step["silence_ms"])
        elif "sfx" in step:
            segment = AudioSegment.from_file(SFX_DIR / step["sfx"])
            if "trim_ms" in step:
                segment = segment[: step["trim_ms"]]
        elif "robot_tts" in step:
            segment = _normalize_loudness(_trim_silence(await _robot_tts(step["robot_tts"], manifest)))
        elif "tts" in step:
            import re
            text = step["tts"]
            if "{narrator}" in text:
                # The narrator NAME is bound to the voice (Hamish = ElevenLabs,
                # Hugo = Inworld) - a script can never say the wrong name
                narrators = manifest.get("narrators", {})
                if voice not in narrators:
                    raise RuntimeError(f"{name}: no narrator name mapped for voice '{voice}'")
                text = text.replace("{narrator}", narrators[voice])
            if provider == "inworld" and STATIC_INWORLD_MODEL in NONVERBAL_CAPABLE_MODELS:
                pass  # canonical tags are Inworld-style already
            elif provider == "elevenlabs" and STATIC_ELEVENLABS_MODEL in ELEVENLABS_TAG_MODELS:
                def _translate(match):
                    tag = match.group(1).strip().lower()
                    return f"[{INWORLD_TO_ELEVENLABS_TAGS[tag]}]" if tag in INWORLD_TO_ELEVENLABS_TAGS else ""
                text = re.sub(r"\[([^\]]*)\]", _translate, text)
                text = re.sub(r"  +", " ", text).strip()
            else:
                stripped = re.sub(r"\s*\[[^\]]*\]", "", text)
                if stripped != text:
                    print(f"  note: stripping inline non-verbal tags for {provider} (would be spoken aloud)")
                    text = re.sub(r"  +", " ", stripped).strip()
            if "prompt" in step:
                if provider == "inworld" and STATIC_INWORLD_MODEL in PROMPT_CAPABLE_MODELS:
                    text = f"{step['prompt']} {text}"
                else:
                    print(f"  note: dropping steering prompt for {provider}/"
                          f"{STATIC_INWORLD_MODEL} (tags are tts-2 non-flash only)")
            audio, error, used, ext, _mime = await convert_text_to_speech(text, provider)
            if error or not audio:
                raise RuntimeError(f"{name}: TTS failed for {provider}: {error}")
            fmt = "ogg" if ext == "opus" else ext
            segment = _trim_silence(AudioSegment.from_file(io.BytesIO(audio), format=fmt))
            # speech is normalized before mixing so SFX gain_db values in the
            # manifest are relative to a known voice level
            segment = _normalize_loudness(segment)
        else:
            raise ValueError(f"{name}: unknown step {step}")

        if "speed" in step:
            segment = _change_speed(segment, step["speed"])
        if "gain_db" in step:
            segment = segment.apply_gain(step["gain_db"])
        if "fade_out_ms" in step:
            segment = segment.fade_out(step["fade_out_ms"])
        for over in step.get("overlay", []):
            over_seg = AudioSegment.from_file(SFX_DIR / over["sfx"])
            if "gain_db" in over:
                over_seg = over_seg.apply_gain(over["gain_db"])
            segment = segment.overlay(over_seg, position=over["at_ms"])

        if "overlap_ms" in step and len(combined) > 0:
            # crosslap: this step starts overlap_ms before the previous audio
            # ends (e.g. the narrator entering under the airport call's tail)
            pos = max(0, len(combined) - step["overlap_ms"])
            total = max(len(combined), pos + len(segment))
            base = combined + AudioSegment.silent(duration=total - len(combined))
            combined = base.overlay(segment, position=pos)
        else:
            combined += segment

    bed = entry.get("bed")
    if bed:
        bed_audio = AudioSegment.from_file(SFX_DIR / bed["sfx"]).apply_gain(bed.get("gain_db", -18))
        if bed.get("fade_in_ms"):
            bed_audio = bed_audio.fade_in(bed["fade_in_ms"])
        # start_ms delays the bed's entry; fades apply to the BED ONLY, so
        # the voice and any closing sting stay at full level
        bed_audio = AudioSegment.silent(duration=bed.get("start_ms", 0)) + bed_audio
        while len(bed_audio) < len(combined):
            bed_audio += bed_audio
        # end_before_ms stops the bed early so the clip's tail (a closing
        # sting, final words) plays clean of it
        bed_end = max(0, len(combined) - bed.get("end_before_ms", 0))
        bed_audio = bed_audio[:bed_end]
        if bed.get("fade_out_ms"):
            bed_audio = bed_audio.fade_out(bed["fade_out_ms"])
        # overlay returns audio the length of its BASE - the full mix must be
        # the base, or a bed ending early truncates the clip's tail (this cut
        # off the closing deep-scan before the fix)
        combined = combined.overlay(bed_audio)

    return _normalize_loudness(combined)


def export(audio: AudioSegment, out_base: Path) -> list[Path]:
    """Export mp3 + opus through the app's own exporter; return written paths.

    free_pool.export_audio_segment is the single export point DOJP-56
    introduced - it forces stereo, which the new Yoto players require. Going
    through it keeps statics byte-compatible with dynamic tracks by
    construction, including any future export changes.
    """
    out_base.parent.mkdir(parents=True, exist_ok=True)
    written = []
    for ext in ("opus", "mp3"):
        path = out_base.with_suffix(f".{ext}")
        path.write_bytes(export_audio_segment(audio, ext))
        written.append(path)
    return written


async def upload(paths: list[Path], voice: str, entry: dict) -> None:
    from app.s3_cache import s3_cache

    for path in paths:
        # free-tier deliverables are voice-independent single files under
        # their own prefix; everything else goes to the voice folder
        prefix = entry.get("upload_prefix", voice)
        name = entry.get("s3_name", path.stem) + path.suffix
        key = f"{prefix}/{name}"
        ok = await s3_cache.set(key, path.read_bytes())
        print(f"  {'uploaded' if ok else 'UPLOAD FAILED'}: {key}")
        if not ok:
            raise SystemExit(1)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entry", action="append", help="entry name(s); default: all")
    parser.add_argument("--voice", action="append", choices=sorted(VOICES),
                        help="voice folder(s); default: all")
    parser.add_argument("--upload", action="store_true",
                        help="PUT rendered files to S3 voice folders")
    parser.add_argument("--upload-only", action="store_true",
                        help="upload the EXISTING files in audio_build/out/ without re-rendering - "
                             "the only way to ship the exact take that was auditioned, since TTS "
                             "reads differ on every render")
    args = parser.parse_args()

    import os
    import app.tts_providers.inworld as inworld
    import app.tts_providers.elevenlabs as elevenlabs
    live_model = os.getenv("INWORLD_MODEL_ID", "(unset; code default)")
    inworld.INWORLD_MODEL_ID = STATIC_INWORLD_MODEL
    marker = "same as" if live_model == STATIC_INWORLD_MODEL else "differs from"
    print(f"static Inworld model: {STATIC_INWORLD_MODEL} (code-pinned) - "
          f"{marker} live INWORLD_MODEL_ID={live_model} (dynamic tracks)")
    live_el = os.getenv("ELEVENLABS_MODEL_ID", "(unset; code default eleven_turbo_v2)")
    elevenlabs.ELEVENLABS_MODEL_ID = STATIC_ELEVENLABS_MODEL
    print(f"static ElevenLabs model: {STATIC_ELEVENLABS_MODEL} (code-pinned, narrator+robot) - "
          f"live ELEVENLABS_MODEL_ID={live_el} (dynamic tracks)")

    manifest_doc = json.loads(MANIFEST.read_text())
    manifest = manifest_doc["entries"]
    entries = args.entry or sorted(manifest)
    voices = args.voice or sorted(VOICES)

    for entry_name in entries:
        if entry_name not in manifest:
            raise SystemExit(f"unknown entry '{entry_name}'; manifest has: {sorted(manifest)}")
        for voice in voices:
            provider = VOICES[voice]
            if args.upload_only:
                paths = [OUT_DIR / voice / f"{entry_name}.{ext}" for ext in ("opus", "mp3")]
                missing = [p for p in paths if not p.exists()]
                if missing:
                    raise SystemExit(f"{entry_name} [{voice}]: no existing render to upload ({missing[0]})")
                print(f"{entry_name} [{voice}]: uploading existing render")
                await upload(paths, voice, manifest[entry_name])
                continue
            audio = await render_entry(entry_name, manifest[entry_name], provider, manifest_doc, voice)
            paths = export(audio, OUT_DIR / voice / entry_name)
            print(f"{entry_name} [{voice}/{provider}]: {audio.duration_seconds:.2f}s "
                  f"{audio.dBFS:.1f} dBFS (target {TARGET_DBFS}) -> "
                  + ", ".join(str(p.relative_to(REPO)) for p in paths))
            if args.upload:
                await upload(paths, voice, manifest[entry_name])


if __name__ == "__main__":
    asyncio.run(main())
