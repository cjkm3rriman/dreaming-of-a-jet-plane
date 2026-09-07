# Architecture

How `dreaming-of-a-jet-plane` turns a button press on a Yoto Player into a spoken
description of a real aircraft overhead.

- [The shape of the system](#the-shape-of-the-system)
- [A full card session](#a-full-card-session)
- [Where the aircraft come from](#where-the-aircraft-come-from)
- [From aircraft to audio](#from-aircraft-to-audio)
- [Provider resolution and fallback](#provider-resolution-and-fallback)
- [Free tier](#free-tier)
- [The cache](#the-cache)
- [Module map](#module-map)
- [Analytics](#analytics)
- [Sharp edges](#sharp-edges)

---

## The shape of the system

One FastAPI process on Railway. It owns no database — every piece of durable
state lives in a single S3 bucket, and everything else is in-process memory that
dies with the container.

```mermaid
graph TB
    subgraph Clients
        Yoto["Yoto Player<br/>(ESP32 HTTP Client)"]
        Web["Browser<br/>(marketing site)"]
    end

    subgraph App["FastAPI on Railway"]
        Routes["main.py<br/>routes + orchestration"]
        Text["flight_text.py<br/>text generation"]
        Select["select_diverse_aircraft<br/>selection rules"]
        Pool["free_pool.py<br/>free tier + audio stitching"]
        Static["JSON databases<br/>airports · airlines · aircraft · cities"]
    end

    subgraph Live["Live aircraft providers"]
        FR24["Flightradar24"]
        Airlabs["Airlabs"]
    end

    subgraph TTS["TTS providers"]
        EL["ElevenLabs<br/>voice: edward"]
        Goog["Google Gemini TTS<br/>voice: sadachbia"]
        IW["Inworld<br/>voice: ronald"]
    end

    S3[("S3 bucket<br/>audio cache · flight cache<br/>free pool · static audio")]
    IPAPI["ipapi.co<br/>IP geolocation"]
    MP["Mixpanel"]
    Sentry["Sentry"]

    Yoto --> Routes
    Web --> Routes
    Routes --> Select --> Text
    Routes --> Pool
    Text --> Static
    Select --> Static
    Routes --> Live
    Routes --> TTS
    Routes <--> S3
    Pool <--> S3
    Routes --> IPAPI
    Routes --> MP
    Routes --> Sentry
```

**Endpoints**, grouped by what they actually do:

| Group | Paths | Behaviour |
|---|---|---|
| Static audio | `/intro`, `/scanning-again`, `/overandout` (+ `.mp3` aliases) | Proxy a pre-recorded file from the voice's S3 folder |
| Scan trigger | `/scanning` | Streams `scanning.mp3` **and** kicks off pre-generation in the background |
| Content | `/plane/1` … `/plane/5` | Serve cached audio, or generate it on the spot |
| Free tier | `/free/scan`, `/free/scanning`, `/free/scanning-again`, `/free/overandout`, `/free/plane/1-3` | Replay audio generated for a paying user, rate-limited |
| Site | `/`, `/robots.txt`, `/sitemap.xml`, `/assets/*` | Marketing page (`website_home.py`) |
| Debug | `/test/live-aircraft`, `/test-gemini-tts` | Provider inspection pages |

Every audio endpoint also has an `@app.options` twin returning permissive CORS
headers.

---

## A full card session

This is the load-bearing idea in the whole codebase: **`/scanning` is not just an
intro clip, it is the warm-up.** While the child listens to ~15 seconds of
"scanning the skies…", the server is fetching flights and generating five MP3s in
parallel. By the time the card advances to `/plane/1`, the audio should already be
sitting in S3.

```mermaid
sequenceDiagram
    participant Y as Yoto Player
    participant A as FastAPI
    participant BG as Background task
    participant P as Aircraft provider
    participant T as TTS provider
    participant S3 as S3

    Y->>A: GET /scanning
    A->>A: Resolve location (IP → lat/lng)
    A->>A: Debounce check (30s per session key)
    A-)BG: create_task(pre_generate_flight_audio)
    A->>S3: GET scanning.mp3
    A-->>Y: stream scanning audio

    Note over BG: runs while the intro plays
    BG->>P: fetch aircraft near lat/lng
    P-->>BG: candidate flights
    BG->>BG: select 5 diverse aircraft
    BG->>S3: cache flight JSON (3 min TTL)
    loop planes 1-5 (concurrent)
        BG->>T: TTS opening + body + fun fact
        T-->>BG: audio segments
        BG->>BG: stitch with pydub
        BG->>S3: PUT plane audio (10 min TTL)
    end
    BG->>S3: copy bodies into free pool + update index

    Y->>A: GET /plane/1
    A->>S3: GET cached plane 1
    S3-->>A: hit
    A-->>Y: stream plane audio

    Y->>A: GET /plane/2 … /plane/5
    A-->>Y: same path

    Y->>A: GET /overandout
    A-->>Y: static sign-off
```

If the cache misses — the child skipped ahead, pre-generation is still running, or
it failed — `/plane/N` does the whole fetch-and-generate chain inline, which is
several seconds slower but produces the same output.

The 30-second debounce in `scanning.py` exists because the Yoto client is prone to
re-requesting; a duplicate request inside the window still gets its audio but
skips the background work and the analytics event.

---

## Where the aircraft come from

`get_nearby_aircraft()` in `main.py` is the single entry point. It walks the
provider list in order and returns from the first one that produces flights.

```mermaid
flowchart TD
    Start["get_nearby_aircraft(lat, lng)"] --> Seq["Resolve provider order"]
    Seq --> Loop{"Next provider?"}
    Loop -->|none left| Fail["Return empty list + joined error string"]
    Loop -->|provider| Conf{"is_configured?"}
    Conf -->|no| Loop
    Conf -->|yes| Cache{"S3 flight cache hit?<br/>key includes provider:name"}
    Cache -->|hit with flights| Ret["Return cached list"]
    Cache -->|hit but empty| Loop
    Cache -->|miss| Fetch["provider.fetch(lat, lng, radius, limit)"]
    Fetch -->|exception| Loop
    Fetch -->|no flights| Empty["Cache empty result<br/>(suppresses rapid retries)"] --> Loop
    Fetch -->|flights| Sort["Sort by distance"]
    Sort --> Diverse["select_diverse_aircraft"]
    Diverse --> Store["Cache JSON (fire and forget)"]
    Store --> Ret
```

Both providers query a bounding box derived from a 100 km radius, then normalise
wildly different payloads into one shared aircraft dict — `flight_number`,
`airline_name`, `origin_city`, `destination_city`, `distance_km`, `eta`,
`is_cargo_operator`, `is_private_operator`, and so on. Enrichment comes from the
bundled JSON databases: IATA → city/country, ICAO → airline name and cargo/private
flags, aircraft ICAO → friendly name, seat count, and phonetic spelling.

The two providers are **not** equivalent in how much cleaning they need:

| | Flightradar24 | Airlabs |
|---|---|---|
| Filter | `categories=P` (passenger) at the API | `status == "en-route"` client-side |
| ETA | Provided by the API | Estimated from distance ÷ cruise speed, plus a landing buffer |
| Position trust | Trusted | Validated against the great-circle route (`is_point_near_route`) — stale positions are common |
| Airline naming | Direct ICAO lookup | Overrides for regional carriers (Endeavor → Delta, Republic flight-number ranges → AA/UA/DL) |
| Retry | None (10s timeout) | 2 attempts, 0.5s → 1s backoff, 4s timeout |

The route validation on the Airlabs side is the most opinionated code in the
repo. It rejects a flight if the user is nowhere near its origin→destination
great circle, if the user sits outside a 10°-margin bounding box around the route,
or if the closest approach exceeds 50% of the total route length — the last check
catches short private-jet hops that report implausible positions.

### Selection rules

Raw provider results are noisy: five flights to the same hub, or the same
regional shuttle five times. `select_diverse_aircraft()` optimises for *variety*,
not proximity.

```mermaid
flowchart TD
    In["Candidate aircraft, sorted by distance"] --> Enrich["Attach destination distance from user"]
    Enrich --> Cat{"Categorise by operator"}
    Cat -->|cargo| Drop["Skipped entirely<br/>(temporary, see TODO in code)"]
    Cat -->|private| CP["cargo_private pool"]
    Cat -->|passenger| Dist{"Destination < 160 km<br/>from the user?"}
    Dist -->|yes| Near["passenger_near<br/>(deprioritised)"]
    Dist -->|no| Far["passenger_far<br/>(preferred)"]
    Far --> Pool["passenger_far + passenger_near"]
    Near --> Pool
    Pool --> D1["Pass 1: one flight per unique country"]
    D1 --> D2["Pass 2: fill with unused destination cities"]
    D2 --> D3["Pass 3: fill with anything left"]
    D3 --> SortP["Sort selection by aircraft distance"]
    SortP --> Insert{"Any private flights?"}
    CP --> Insert
    Insert -->|4+ passenger picks| Slot4["Insert private at position 4"]
    Insert -->|exactly 1| Append["Append up to 4 private"]
    Insert -->|none| Only["Use up to 5 private"]
    Insert -->|no private| Done
    Slot4 --> Done["Final list, max 5"]
    Append --> Done
    Only --> Done
```

Nearby destinations are pushed down the list deliberately: a flight from the next
town over is less interesting than one crossing an ocean, and the fun fact about
the destination city is worthless if the child already lives there.

---

## From aircraft to audio

Each plane's script is built from four segments, and each is generated and cached
independently so the expensive-but-repeatable parts can be reused.

```mermaid
flowchart LR
    AC["Selected aircraft"] --> GEN["generate_flight_text_for_aircraft<br/>split_text=True"]

    GEN --> O["Opening<br/>'Marvelous! We've detected a jet<br/>plane 9 miles from this Yoto!'"]
    GEN --> B["Body<br/>captain · aircraft · speed · route · ETA"]
    GEN --> FO["Fun fact opening<br/>'Did you know?'"]
    GEN --> FB["Fun fact body<br/>from cities.json"]

    O --> T1["TTS (always fresh —<br/>contains the distance)"]
    B --> T2["TTS (always fresh)"]
    FO --> C1{"Opening phrase<br/>cached?"}
    FB --> C2{"Fun fact<br/>cached by content hash?"}
    C1 -->|hit| A3
    C1 -->|miss| T3["TTS + cache"] --> A3["fun fact opening audio"]
    C2 -->|hit| A4
    C2 -->|miss| T4["TTS + cache"] --> A4["fun fact body audio"]

    T1 --> ST["stitch_audio_multi<br/>trim silence · gaps 1000/1000/500ms<br/>normalise to -20 dBFS"]
    T2 --> ST
    A3 --> ST
    A4 --> ST

    ST --> OUT["Final plane audio → S3"]
    T2 --> BODYC["body+fact stitched → S3<br/>(reused by the free tier)"]
```

Splitting the text is what makes the free tier possible. The opening names a
distance that is only true for the user who triggered the scan, but the body —
airline, route, aircraft, fun fact — is true for anybody. So the body is cached
separately and later paired with a generic pre-recorded opening.

Fun facts are cached by **content hash**, not by city, which gives free
invalidation: editing a fact in `cities.json` changes the hash and misses the
cache; removing one leaves an orphan that S3 lifecycle rules eventually reap.

The text itself is heavily randomised — opening exclamation, captain surname,
aircraft adjective, movement verb, which stat gets mentioned, which of four fun
fact openers is used, and a kid-scale ETA comparison ("about how long it takes to
read three bedtime stories"). Units follow the user's country: imperial for
`US`, `GB`, and seven others, metric elsewhere. Numbers are spelled out for TTS
("BA123" → "B A one two three") because the models otherwise mangle them.

If split TTS fails at any point, the code falls back to a single TTS call on the
full concatenated sentence. If TTS fails entirely, `/plane/N` returns JSON with
the text and the error instead of audio.

---

## Provider resolution and fallback

Two independent provider systems, same shape: a registry dict mapping a name to
`{display_name, is_configured, ...}`, resolved at request time.

```mermaid
flowchart TD
    subgraph Aircraft["Live aircraft — aircraft_providers/"]
        A1{"?provider= + valid ?secret= ?"}
        A1 -->|yes| A2["Use only that provider"]
        A1 -->|no| A3["LIVE_AIRCRAFT_PROVIDER"]
        A3 --> A4["then LIVE_AIRCRAFT_PROVIDER_FALLBACKS<br/>(comma-separated, deduped)"]
        A4 --> A5["default fr24 if list is empty"]
        A5 --> A6["Try each in order until flights returned"]
    end

    subgraph Voice["TTS — tts_providers/"]
        B1{"?tts= + valid ?secret= ?"}
        B1 -->|yes| B2["Use that provider"]
        B1 -->|no| B3["TTS_PROVIDER env var"]
        B3 --> B4{"= 'fallback'?"}
        B4 -->|yes| B5["ElevenLabs, then Inworld on error"]
        B4 -->|no| B6["Named provider only, no fallback"]
    end
```

The TTS provider choice cascades further than it looks. It determines the audio
format (`opus` for ElevenLabs and Inworld, `mp3` for Google), the MIME type, the
S3 folder for static clips (`edward` / `sadachbia` / `ronald`), and it is baked
into every cache key — so switching providers invalidates the entire audio cache
by construction.

`PROVIDER_OVERRIDE_SECRET` gates all overrides, including the `lat`/`lng`
position override. Without it configured, override query params are silently
ignored; with it configured, a wrong secret is logged with the client IP.

---

## Free tier

Free users don't trigger any live API calls. They "tune into" flights that a
paying user's scan already produced.

```mermaid
flowchart TD
    subgraph Produce["Producer — end of every paid pre-generation"]
        P1["Pre-generation finishes with 2+ aircraft"]
        P1 --> P2["For planes 1-3: read body audio from paid cache"]
        P2 --> P3["Copy to free_pool/{session}_plane{n}_body_{provider}"]
        P3 --> P4["Append entry to free_pool/index.json"]
        P4 --> P5{"More than 100 entries?"}
        P5 -->|yes| P6["Drop oldest (FIFO); S3 objects left to expire"]
    end

    subgraph Consume["Consumer — /free/plane/N"]
        C1["Request"] --> C2{"Rate limit<br/>50 req/min per IP"}
        C2 -->|exceeded| C3["429 + Retry-After"]
        C2 -->|ok| C4["Load index (60s in-memory cache)"]
        C4 --> C5{"Pool empty?"}
        C5 -->|yes| C6["'Still warming up my scanner' message"]
        C5 -->|no| C7["Pick a random session from the last 5"]
        C7 --> C8["Fetch body audio for this plane index"]
        C8 --> C9["Fetch random static intro 1-6"]
        C9 --> C10["Stitch intro + body, stream"]
    end

    P4 -.->|index.json| C4
    P3 -.->|audio objects| C8
```

Consequences worth knowing: the free tier is empty on a cold start until a paying
user scans; free content is stale by design (up to 100 sessions old); free audio
is read with `get_raw()`, bypassing the TTL check that governs the paid cache,
because the index — not the object age — is what controls its lifetime.

---

## The cache

One S3 bucket, several key spaces with different rules. There is no other
persistence layer.

| Key pattern | Contents | TTL | Read path |
|---|---|---|---|
| `cache/{md5}_aircraft.json` | Selected flights for a location + provider | 3 min | `get(content_type="json")` |
| `cache/{md5}_plane{n}_{provider}.{ext}` | Finished plane audio | 10 min | `get()` |
| `cache/{md5}_plane{n}_body_{provider}.{ext}` | Body (+fact) audio, for free-tier reuse | 10 min | `get_raw()` |
| `cache/fun_facts/{hash}_{provider}.{ext}` | Fun fact audio | none — content-hashed | `get_raw()` |
| `cache/fun_facts/openings/{hash}_{provider}.{ext}` | "Did you know?" etc. | none | `get_raw()` |
| `free_pool/index.json` | Session index, max 100 FIFO | none | `get_raw()` |
| `free_pool/{session}_plane{n}_body_{provider}.{ext}` | Free tier body audio | none | `get_raw()` |
| `free/intros/flight-intro-{1..6}.{ext}` | Generic free openings | static | `get_raw()` |
| `{voice}/intro.mp3`, `scanning.mp3`, … | Per-voice static clips | static | Public HTTPS GET |

The location hash is `md5("{lat:.2f},{lng:.2f}")` — roughly 1 km precision, so
neighbours share cache entries. The JSON key adds a `provider:{name}` namespace
so a fallback provider can't read the primary's results.

TTL is enforced on read, not by S3: `get()` issues a `HEAD`, compares
`Last-Modified` against the TTL, and treats anything older as a miss. Timeouts are
tiered — 3s for `HEAD`, 30s for `GET`, 60s for `PUT` — so a cache probe fails fast
while a real download gets room. Uploads retry with jittered exponential backoff
on 503 `SlowDown`. A shared `httpx` client (100 connections, 50 keep-alive) is
reused across the process.

Writes are almost always `asyncio.create_task(...)` — fire-and-forget, so a slow
S3 PUT never delays the audio stream.

### In-memory state

| Where | What | Lifetime |
|---|---|---|
| `location_utils._ip_cache` | IP → lat/lng/city | 24h (5 min for rate-limit fallbacks) |
| `scanning._scanning_request_cache` | Session key → last scan time | 30s debounce window |
| `free_pool._free_pool_index_cache` | Parsed index | 60s |
| `free_pool._rate_limit_cache` | IP → request timestamps | 60s window |

All four are plain module-level dicts. They are per-container and unbounded — fine
for one Railway replica, but they would need rethinking before scaling out, and
the rate limiter in particular becomes per-replica rather than global.

---

## Module map

```mermaid
graph LR
    main["main.py<br/>1.8k lines"]
    scanning["scanning.py"]
    free["free_pool.py"]
    text["flight_text.py"]
    loc["location_utils.py"]
    s3["s3_cache.py"]
    ff["fun_fact_cache.py"]
    ap["aircraft_providers/"]
    tp["tts_providers/"]
    db["*_database.py"]
    an["analytics.py"]

    main --> scanning
    main --> free
    main --> text
    main --> loc
    main --> s3
    main --> ff
    main --> ap
    main --> tp
    main --> db
    main --> an
    scanning -.->|deferred import| main
    scanning --> free
    scanning --> ff
    scanning --> text
    free --> s3
    free --> tp
    text --> db
    text --> loc
    ap --> db
    ap --> loc
    ff --> s3
```

| Module | Responsibility |
|---|---|
| `main.py` | Routes, TTS dispatch, aircraft fetch + selection, analytics helpers, free tier handlers |
| `scanning.py` | `/scanning` endpoint, debounce, background pre-generation of all 5 planes |
| `flight_text.py` | All user-facing text; unit localisation; TTS-friendly number spelling |
| `flight_text_seasonal.py` | Date-driven sentence overrides (e.g. holiday messages) |
| `free_pool.py` | Free tier index, rate limiting, and all pydub audio stitching |
| `s3_cache.py` | Hand-rolled SigV4 S3 client, key generation, TTL, retries |
| `fun_fact_cache.py` | Content-hashed fun fact audio caching |
| `location_utils.py` | IP geolocation + cache, haversine, great-circle route validation, UA parsing |
| `aircraft_providers/` | `fr24.py`, `airlabs.py` + registry — normalise flights to one dict shape |
| `tts_providers/` | `elevenlabs.py`, `google.py`, `inworld.py` + registry — text → audio bytes |
| `*_database.py` | Read-only JSON lookups: airports, airlines, aircraft, cities |
| `analytics.py` | Thin Mixpanel wrapper; swallows its own failures |
| `website_home.py` | Marketing page, robots.txt, sitemap |

The dotted arrow is real: `scanning.py` imports from `main.py` inside function
bodies to break the import cycle. It appears throughout `intro.py`,
`overandout.py`, and `scanning_again.py` too.

---

## Analytics

Mixpanel, with a `distinct_id` of `md5(ip + user_agent)[:16]` and an `$insert_id`
on every event for deduplication. Yoto Players are detected by their
`ESP32 HTTP Client/1.0` user agent and relabelled from "Other" to "Yoto Player".

| Event | Fired when | Notable properties |
|---|---|---|
| `scan:start` | `/scanning` or a `/free/*` entry point | `subscription` |
| `scan:complete` | Aircraft fetch resolves | `nearby_aircraft`, `aircraft_provider`, `from_cache` |
| `plane:request` | Any `/plane/N` or `/free/plane/N` | `plane_index`, `from_cache`, `free_pool_entry_id` |
| `generate:audio` | TTS produces a plane's audio | `generation_time_ms`, `tts_provider`, `fun_fact_source`, `fun_fact_cache_hit`, origin/destination |
| `error:location` | IP geolocation fails or falls back | `failure_type`, `fallback_location` |
| `intro`, `scanning-again`, `overandout` | Static clip streamed | Location, device |

Every tracking call is wrapped in `try/except` — analytics failures never reach
the user. Sentry sits alongside it for exceptions, sampling 10% of traces, with
the environment inferred from `RAILWAY_REPLICA_ID`.

---

## Sharp edges

Things that are true today and would surprise a reader of the code.

- **Cargo flights are excluded entirely.** `select_diverse_aircraft` drops them
  with a `TODO` saying it's temporary; only private operators reach the
  cargo/private slot.
- **A NameError is being swallowed in the Airlabs ETA path.**
  `aircraft_providers/airlabs.py:313` uses `aircraft_type` before it is assigned
  at line 353. The surrounding `try/except Exception` catches it, so ETA
  estimation silently yields `None` for the first flight and reuses the previous
  flight's type thereafter.
- **The free-tier rate limit docstring disagrees with the code** — 10/min in the
  docstring, `FREE_TIER_RATE_LIMIT = 50` in the constant.
- **`populate_free_pool` is passed 5 aircraft but only loops over planes 1-3**,
  matching the three free endpoints; the docstring still says "up to 5 planes".
- **`s3_cache.generate_cache_key`'s fallback format map says
  `elevenlabs → mp3`**, while the TTS registry says ElevenLabs produces `opus`.
  Harmless today because every real call passes `audio_format` explicitly, but
  it's a trap for a future caller that doesn't.
- **`/plane/N` accepts a `tts` query parameter it never reads** — the override is
  re-extracted from the raw request inside `get_tts_provider_override`, so the
  declared parameter is decorative.
- **Fallback location is New York City.** Any geolocation failure puts the child
  over NYC, and plane 1 says so out loud.

---

*Generated from the code as of the `docs/architecture-overview` branch. Diagrams
are Mermaid and render natively on GitHub.*
