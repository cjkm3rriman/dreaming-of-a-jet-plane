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

from app.free_pool import TARGET_DBFS, _normalize_loudness, _trim_silence
from app.tts_providers import TTS_PROVIDERS

MANIFEST = REPO / "audio_build" / "static_audio.json"
SFX_DIR = REPO / "assets" / "sfx"
OUT_DIR = REPO / "audio_build" / "out"

# voice folder -> TTS provider (the app's registry maps the other way)
VOICES = {defn["voice_folder"]: name for name, defn in TTS_PROVIDERS.items()}


async def render_entry(name: str, entry: dict, provider: str) -> AudioSegment:
    """Compose one manifest entry's timeline for one TTS provider."""
    from app.main import convert_text_to_speech

    combined = AudioSegment.empty()
    for step in entry["timeline"]:
        if "silence_ms" in step:
            segment = AudioSegment.silent(duration=step["silence_ms"])
        elif "sfx" in step:
            segment = AudioSegment.from_file(SFX_DIR / step["sfx"])
        elif "tts" in step:
            audio, error, used, ext, _mime = await convert_text_to_speech(step["tts"], provider)
            if error or not audio:
                raise RuntimeError(f"{name}: TTS failed for {provider}: {error}")
            fmt = "ogg" if ext == "opus" else ext
            segment = _trim_silence(AudioSegment.from_file(io.BytesIO(audio), format=fmt))
            # speech is normalized before mixing so SFX gain_db values in the
            # manifest are relative to a known voice level
            segment = _normalize_loudness(segment)
        else:
            raise ValueError(f"{name}: unknown step {step}")

        if "gain_db" in step:
            segment = segment.apply_gain(step["gain_db"])
        if "fade_out_ms" in step:
            segment = segment.fade_out(step["fade_out_ms"])
        combined += segment

    bed = entry.get("bed")
    if bed:
        bed_audio = AudioSegment.from_file(SFX_DIR / bed["sfx"]).apply_gain(bed.get("gain_db", -18))
        while len(bed_audio) < len(combined):
            bed_audio += bed_audio
        combined = bed_audio[: len(combined)].overlay(combined)
        if bed.get("fade_out_ms"):
            combined = combined.fade_out(bed["fade_out_ms"])

    return _normalize_loudness(combined)


def export(audio: AudioSegment, out_base: Path) -> list[Path]:
    """Export mp3 + opus with the app's own parameters; return written paths."""
    out_base.parent.mkdir(parents=True, exist_ok=True)
    written = []
    for ext in ("opus", "mp3"):
        export_format = "ogg" if ext == "opus" else ext
        export_params = ["-acodec", "libopus"] if ext == "opus" else []
        path = out_base.with_suffix(f".{ext}")
        audio.export(path, format=export_format, parameters=export_params)
        written.append(path)
    return written


async def upload(paths: list[Path], voice: str) -> None:
    from app.s3_cache import s3_cache

    for path in paths:
        key = f"{voice}/{path.name}"
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
    args = parser.parse_args()

    manifest = json.loads(MANIFEST.read_text())["entries"]
    entries = args.entry or sorted(manifest)
    voices = args.voice or sorted(VOICES)

    for entry_name in entries:
        if entry_name not in manifest:
            raise SystemExit(f"unknown entry '{entry_name}'; manifest has: {sorted(manifest)}")
        for voice in voices:
            provider = VOICES[voice]
            audio = await render_entry(entry_name, manifest[entry_name], provider)
            paths = export(audio, OUT_DIR / voice / entry_name)
            print(f"{entry_name} [{voice}/{provider}]: {audio.duration_seconds:.2f}s "
                  f"{audio.dBFS:.1f} dBFS (target {TARGET_DBFS}) -> "
                  + ", ".join(str(p.relative_to(REPO)) for p in paths))
            if args.upload:
                await upload(paths, voice)


if __name__ == "__main__":
    asyncio.run(main())
