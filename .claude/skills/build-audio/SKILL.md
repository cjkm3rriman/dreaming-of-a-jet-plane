---
name: build-audio
description: Render a static audio deliverable from the manifest (DOJP-35) — edit the script/timeline, render per voice, send for audition, upload to S3 only on explicit approval. Use when the user wants to create, re-record, tweak, or re-master a static clip (scanning, scanning-again, overandout, free intros) or change its script text.
---

# Build static audio

The static clips are built from `audio_build/static_audio.json` (one entry per
deliverable: a timeline of `sfx` / `tts` / `robot_tts` / `silence_ms` steps,
optional looped `bed`) by `scripts/build_static_audio.py`. This replaces the
old iMovie workflow. SFX sources live in `assets/sfx/`.

Two kinds of speech: `tts` renders in the entry's **narrator** voice (one per
voice folder), while `robot_tts` always renders in the **scanner-robot**
ElevenLabs voice. **The narrator's NAME is bound to the voice** - scripts use
the `{narrator}` token and the manifest's `narrators` map (Hugo = Inworld/
`ronald`, Hamish = ElevenLabs/`edward`), so a render can never say the wrong
character's name; an unmapped voice fails loudly rather than guessing (`robot_voice_id` in the manifest, currently
`weA4Q36twV5kwSaTEL0Q`) regardless of narrator — the robot is the same
character in every voice cast. The `robot-*.mp3` files in `assets/sfx/` are
recordings of that same voice from the iMovie era; prefer `robot_tts` for
anything new or re-worded.

## Procedure

1. **Edit the manifest** if the request changes a script line, SFX, gain, or
   timing. Script text is kid-facing — follow CLAUDE.md's style guide and the
   house closers ("on to the next one" energy mid-session; "try again in a
   minute or so will you?" only when the session is genuinely over).
2. **Render** (TTS keys come from the Railway env):
   ```bash
   railway run uv run python scripts/build_static_audio.py --entry <name> [--voice <folder>]
   ```
   No `--voice` renders every voice (edward=elevenlabs, ronald=inworld,
   sadachbia=google). Output lands in `audio_build/out/{voice}/{name}.{opus,mp3}`
   — gitignored audition area, S3 untouched.
3. **Verify before presenting**: decode with pydub; assert stereo (2ch — the
   new Yoto players reject mono, DOJP-56), −20 dBFS (±1), and a plausible
   duration vs the current production file
   (`s3://dreaming-of-a-jet-plane/{voice}/{name}.{ext}`).
4. **Audition**: send the rendered file(s) to the user with SendUserFile,
   alongside the current production version for A/B when one exists. State
   the dBFS/duration/channels numbers.
5. **Upload only on explicit approval** — "ok", "sounds good", "ship it"
   after *hearing it*, not before:
   ```bash
   railway run uv run python scripts/build_static_audio.py --entry <name> [--voice <folder>] --upload
   ```
   This overwrites the live `{voice}/{name}.{ext}` objects in S3; players pick
   the new file up on their next fetch (clips are client-cached up to 1h).
   Never pass `--upload` in the same run that first renders a new script.

## Models

The **static** Inworld model is pinned in code (`STATIC_INWORLD_MODEL` in
`scripts/build_static_audio.py`, currently `inworld-tts-2`); the Railway env
var `INWORLD_MODEL_ID` steers **dynamic** plane audio only (tts-2-flash
planned there). The renderer prints both at the start of every run — always
relay that line to the user so drift between the two is visible. They are
expected to differ; a surprise is the static pin silently changing, not the
pair disagreeing.

## Voice steering (prompts)

A `"prompt"` on a `tts` step is an Inworld **inline instruction tag** (e.g.
`[speak as a jolly elderly British gentleman...]`) prepended to the text.
**Only non-flash tts-2 supports it** - flash silently ignores tags and older
models speak the brackets aloud - so the renderer attaches it strictly when
`STATIC_INWORLD_MODEL` is in `PROMPT_CAPABLE_MODELS` and drops it with a
printed note otherwise (including for non-Inworld narrator renders). After
any steered render, spot-check the first seconds (whisper or ears) to confirm
the tag was performed, not spoken.

**Non-verbals** ([chuckle], [sigh], [gasp], [clear throat], ...) are one-shot
sounds written INLINE in the `tts` text exactly where the moment happens.
Wider support than steering: both tts-2 models render them (flash included);
for any other model or provider the renderer strips every [tag] from the text
so brackets are never spoken. Use them sparingly - these clips play every
session, so one well-placed sound beats three.

## Model pins

Both static speech models are code-pinned in `scripts/build_static_audio.py`
and independent of the Railway env vars that steer dynamic tracks:
`STATIC_INWORLD_MODEL` (currently `inworld-tts-2`) and
`STATIC_ELEVENLABS_MODEL` (currently `eleven_v4`, used for Hamish AND the
robot). eleven_v4/v3 support audio tags with a DIFFERENT vocabulary from
Inworld ([laughs] vs [laugh]); canonical manifest tags are Inworld-style and
`INWORLD_TO_ELEVENLABS_TAGS` translates them per render. The renderer prints
all pins vs the live env at the start of every run - relay that line.

## Gotchas

- TTS reads differ per render — re-rendering an approved entry produces a
  *different* performance. Treat uploaded audio as the canonical artifact;
  re-render deliberately, not casually.
- Each voice renders independently; a provider outage (e.g. Google 402
  billing) fails that voice only. Production voice is Inworld/`ronald` —
  prioritize it.
- `gain_db` on SFX steps is relative to normalized voice level (speech is
  normalized to TARGET_DBFS before mixing).
- Entries whose production original predates the pipeline were
  reverse-engineered from amplitude envelopes; if the user says the words
  differ from the original, fix the manifest text — the envelope only reveals
  structure, not words.
