# SFX sources

Canonical sound-effect masters for the static audio deliverables (`scanning`,
`scanning-again`, `overandout`, the six free-tier `flight-intro-N` files).
Exported from the iMovie projects for DOJP-36 so the manifest-driven build
pipeline (DOJP-35) can rebuild every static file without iMovie.

These are the only copies outside iMovie. Do not re-encode them in place; the
build pipeline should decode each clip to PCM once per render and encode only
the final mix.

## Inventory

All seven clips are MP3. These are the original files as downloaded or
generated, so no lossless masters exist. Each pipeline render decodes lossy
sources and re-encodes the mix once, which is what the current iMovie exports
already do.

| File | Duration | Format | Provenance |
| --- | --- | --- | --- |
| `airport-call.mp3` | 4.8 s | 48 kHz stereo, 256 kbps | Free stock SFX (internet download) |
| `deep-scan.mp3` | 1.1 s | 44.1 kHz mono, 256 kbps | Free stock SFX (internet download) |
| `jazz-lounge-elevator-music.mp3` | 87.8 s | 44.1 kHz stereo, 256 kbps | Free stock SFX (internet download) |
| `radio-frequency.mp3` | 20.0 s | 44.1 kHz stereo, 256 kbps | Free stock SFX (internet download) |
| `robot-activate-scanning-module.mp3` | 2.8 s | 44.1 kHz mono, 128 kbps | ElevenLabs sound generation (paid subscription) |
| `robot-scanning-skies.mp3` | 2.5 s | 44.1 kHz mono, 128 kbps | ElevenLabs sound generation (paid subscription) |
| `robot-scanning-skies-more.mp3` | 3.1 s | 44.1 kHz mono, 166 kbps | ElevenLabs sound generation (paid subscription) |

The `robot-*` clips were generated with ElevenLabs under a paid subscription,
which grants a commercial licence to the output. The other four are free stock
effects downloaded from the internet; the specific sites were not recorded.
Both categories are treated as cleared for repo check-in. If a stock source
turns out to need attribution, add it to this table.

## Current deliverables

Durations of the files served from production on 2026-09-16, for the pipeline
to A/B against. Premium files are from the Inworld (`ronald`) voice folder.

| Deliverable | Premium | Free |
| --- | --- | --- |
| `scanning` | 38.7 s | 27.5 s |
| `scanning-again` | 7.2 s | 8.6 s |
| `overandout` | 22.1 s | 24.0 s |
| `flight-intro-1` to `-6` | n/a | 5.8 s to 7.9 s |

`intro` is not referenced by any playlist and only exists in S3 for the
ElevenLabs (`edward`) voice folder, so it is treated as legacy and is not a
pipeline target.

## Draft timelines

Unconfirmed first pass at which clip appears where, inferred from clip names
and lengths rather than by listening to the mixes. Correct this before it
becomes the DOJP-35 manifest.

- **scanning**: `robot-activate-scanning-module` as the power-up sting, then
  `jazz-lounge-elevator-music` or `radio-frequency` as a low bed under the
  voice, with `deep-scan` and `robot-scanning-skies` as blips while the scan
  "runs". The free version is a shorter cut of the same structure.
- **scanning-again**: `robot-scanning-skies-more` as the sting, `deep-scan`
  as the closing blip. Short enough that there is probably no bed.
- **overandout**: `airport-call` as the PA chime near the start, voice over a
  fading `radio-frequency` bed.
- **flight-intro-N**: a single short sting (`deep-scan` or one of the
  `robot-*` clips) before each voice line.
