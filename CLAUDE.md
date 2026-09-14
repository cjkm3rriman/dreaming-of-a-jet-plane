# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a FastAPI application called "dreaming-of-a-jet-plane" that uses Yoto to help users learn about jet planes in the sky and their destinations. The project is deployed on Railway at: https://dreaming-of-a-jet-plane-production.up.railway.app

See `docs/ARCHITECTURE.md` for the system architecture: request lifecycle, provider fallback, caching strategy, and the free tier.

## Sentry

- **Organization**: `raccoon-research-labs` (region: `https://us.sentry.io`)
- **Project**: `dreaming-of-a-jetplane`

## Tech Stack

- **Python 3.13+**: Core language
- **UV**: Python package manager for dependency management
- **FastAPI**: Web framework with standard extras
- **Flightradar24 & Airlabs APIs**: Live flight tracking and aircraft data across multiple providers
- **HTTPX**: Async HTTP client for API requests
- **ElevenLabs API**: Text-to-speech voice synthesis
- **Mixpanel**: Analytics tracking for usage metrics
- **Railway**: Deployment platform

## Development Commands

### Package Management
```bash
uv install          # Install dependencies
uv add <package>    # Add new dependency
uv remove <package> # Remove dependency
uv sync             # Sync environment with lock file
```

### Running the Application
```bash
uv run fastapi dev app/main.py    # Run development server
uv run fastapi run app/main.py    # Run production server
uv run fastapi run app/main.py --host 0.0.0.0 --port 8000    # Run with custom host/port
```

### Railway Deployment
```bash
# Railway will automatically use the railway.toml configuration
# Or fall back to the Procfile for deployment
railway up    # Deploy to Railway (if Railway CLI is installed)
```

## Git Workflow

**Use feature branches and pull requests** for all changes (do not commit directly to main).

### Workflow:
1. **Create feature branch** from main:
   ```bash
   git checkout main && git pull
   git checkout -b feature/description-of-change
   ```

2. **Make commits** on the feature branch as you work

3. **Push and create PR** when ready:
   ```bash
   git push -u origin feature/description-of-change
   gh pr create --fill
   ```

4. **Merge via GitHub** - use "Squash and merge" for clean history

5. **Clean up** locally after merge:
   ```bash
   git checkout main && git pull && git branch -d feature/description-of-change
   ```

### Branch naming conventions:
- `feature/add-retry-logic` - new functionality
- `fix/s3-timeout-handling` - bug fixes
- `refactor/cleanup-error-handling` - code improvements

### Deployment:
When the user asks to "deploy", this means:
1. Push the feature branch to GitHub
2. Create a PR (or update existing PR)
3. Merge the PR via GitHub
4. Railway automatically deploys from main

## Linear Integration

This project uses Linear for issue tracking. When working on Linear issues:

- **Branch names**: Use Linear's suggested git branch name (from the issue's `gitBranchName` field)
- **PR titles**: Include the issue identifier (e.g., `DOJP-17: Remove AWS Polly support`)
- **PR linking**: Include `Closes DOJP-XX` in the PR body to link it to the Linear issue
- **Start of work**: When beginning work on a Linear issue, set its status to **In Progress**
- **PR merged**: When the user says they have merged the PR, set the issue status to **Done**

## Testing

The suite has two tiers, enforced by markers — a `conftest.py` collection hook
requires every test to carry exactly one of `@pytest.mark.unit` /
`@pytest.mark.integration`, and aborts collection naming any offender.

- **unit** (~205 tests, fully offline, ~10s): no API keys, no live services.
  Includes recorded-payload contract tests for both flight providers, an
  offline full-flow test that decodes every audio response
  (`tests/test_full_flow_offline.py`), real-ffmpeg stitching tests, SigV4/TTL
  tests for the hand-rolled S3 client, and TTS provider tests via respx.
  Requires `ffmpeg` installed locally.
- **integration** (17 tests): fetch live aircraft. They skip themselves
  without API keys and can skip on an empty sky — skips are normal, FAILED is
  not.

### Commands

```bash
uv run pytest                                  # offline suite - run before every push
uv run pytest tests/test_<area>.py -v          # while iterating on one area
railway run uv run pytest                      # full suite incl. live integration tests
railway run uv run pytest -m integration -rs   # just the live tests, with skip reasons
railway run uv run pytest -m integration -k detailed_output -s   # eyeball generated text
```

`uv run pytest` is byte-for-byte what CI runs — green locally means a green
required check.

### What runs automatically

- **Every PR and push to main**: `.github/workflows/ci.yml` runs the offline
  suite with coverage reporting (`--cov=app`, reported not gated). Branch
  protection requires the `test` check, so nothing merges red.
- **Mondays 06:00 UTC + manual dispatch**: `.github/workflows/integration.yml`
  runs the 17 live tests with `-rs` and pipes skip/fail lines into the job
  summary — chronic skipping is the alarm it exists to raise. Uses the
  `FR24_API_KEY` and `AIRLABS_API_KEY` repository secrets.

### Conventions

- Fixtures in `tests/fixtures/` are genuine recorded API responses. Refresh by
  re-recording, never by hand editing — their value is that nobody chose their
  contents.
- Audio-producing tests decode output with pydub and assert audible content
  (`dBFS`), not just byte length. "The bytes actually play" is the property
  production cares about; silent-but-decodable output has slipped past
  duration-only checks before.
- Avoid module-level side effects in test files (network, subprocess, ffmpeg):
  pytest imports every test file during collection, even when all of its tests
  will be deselected in that environment.
- Expected results: offline — everything passes, the 17 integration tests
  skip. Any FAILED is a regression; do not merge it.

## Environment Variables

**IMPORTANT**: This project uses **Railway environment variables**, NOT local `.env` files. All environment variables are configured in the Railway dashboard at:
https://railway.app/project/dreaming-of-a-jet-plane/settings

The `.env.example` file serves as documentation only. When testing locally, environment variables must be exported manually or set in your shell.

The application requires several environment variables for full functionality:

### Required
- `FR24_API_KEY`: Flightradar24 API key for live flight data
- `GOOGLE_API_KEY`: Google API key for Gemini TTS
- `TTS_PROVIDER`: TTS provider to use (options: `elevenlabs`, `google`, `inworld`, `fallback`)
- `LIVE_AIRCRAFT_PROVIDER`: Primary live aircraft provider key (e.g., `fr24` or `airlabs`)

### Optional
- `ELEVENLABS_TEXT_TO_VOICE_API_KEY`: ElevenLabs API key for text-to-speech (if using ElevenLabs)
- `MIXPANEL_TOKEN`: Mixpanel project token for analytics tracking
- `PROVIDER_OVERRIDE_SECRET`: Shared secret for overriding both TTS and live aircraft providers via query parameters
- `LIVE_AIRCRAFT_PROVIDER_FALLBACKS`: Comma-separated list of fallback providers to try if the primary fails
- `AIRLABS_API_KEY`: Airlabs API key (needed if `airlabs` is used as a primary or fallback provider)
- AWS S3 credentials for caching (if using S3 cache)

See `.env.example` for a complete template of environment variables.

## Analytics

The application includes comprehensive Mixpanel analytics tracking:

- **Plane Requests**: User location, plane number, results found, errors
- **Fun Facts**: City, country, and fact count when fun facts are included  
- **Audio Generation**: Text length, generation time, voice model used
- **Flight Data API**: Success/failure, response time, aircraft count

## Project Structure

```
app/
├── __init__.py           # Empty package initializer
├── main.py               # FastAPI application entry point
├── analytics.py          # Mixpanel analytics integration
├── cities_database.py    # Cities data and fun facts
├── airport_database.py   # Airport lookup functionality
├── flight_text.py        # Flight text generation
├── cities.json           # Cities database with fun facts
├── airports.json         # Airport data for IATA code lookups
└── ...                   # Other supporting modules
railway.toml              # Railway deployment configuration
Procfile                 # Alternative deployment configuration
.env.example             # Environment variables template
```

## Architecture Notes

- **Simple FastAPI Structure**: Single-file application in `app/main.py`
- **FastAPI App Instance**: Created directly in main.py (note: indentation suggests this may need fixing)
- **Basic Route**: Single root endpoint returning JSON message
- **UV Package Management**: Uses `pyproject.toml` for project configuration and `uv.lock` for dependency locking

The application currently has a basic structure with a single endpoint. The main FastAPI app is defined in `app/main.py:3` with a root GET endpoint at `app/main.py:5-7`.

## Plane Endpoint Text Output

The `/plane/1` through `/plane/5` endpoints return MP3 audio generated from descriptive flight text. Understanding the character count is useful for TTS cost estimation and buffer sizing.

### Text Composition

Each flight description includes:
1. **Opening sentence** (~80-100 chars): Distance detection with random opening word
2. **Scanner sentence** (~150-200 chars): Aircraft type, captain name, capacity, speed, altitude
3. **Flight details** (~150-250 chars): Airline, flight number, origin, destination, ETA with kid-friendly comparison
4. **Fun fact** (~80-150 chars): Random fact about destination city (optional, not all cities have facts)
### Character Count Estimates

| Endpoint | Typical Range | Notes |
|----------|---------------|-------|
| `/plane/1` | 450-550 chars | First plane detected |
| `/plane/2` | 450-550 chars | Second plane found |
| `/plane/3` | 400-500 chars | Sometimes no fun fact |
| `/plane/4` | 450-550 chars | Fourth plane spotted |
| `/plane/5` | 400-500 chars | Final plane found |
| **All 5 planes** | **2,200-2,650 chars** | Total for a full session |

Note: Closing prompts ("Should we find another jet plane?", etc.) are now handled as separate static audio files, not included in the generated text.

### Variables Affecting Length

- **Aircraft type name**: "Boeing 787 Dreamliner" vs "Saab 340"
- **City/country names**: Varies significantly by destination
- **Distance/speed values**: Numbers and word equivalents vary
- **ETA formatting**: "a few minutes" to "sometime tomorrow"
- **Fun fact availability**: Not all cities have fun facts in the database
- **Unit system**: Metric ("kilometers") vs Imperial ("miles")

### Example Output (578 characters)

```
Marvelous! We've detected a jet plane up in the sky, 9 miles from this Yoto! My scanner tells me that Captain Olsen is piloting this mega, massive Canadair Regional Jet nine zero zero cruising at 2,257 feet. This flight D L four nine nine nine belongs to Delta Air Lines and is sky skimming from New York City in New York all the way to Hebron in Kentucky landing in about 2 hours - that's like watching eight of your favorite tv episodes in a row. Did you know? Hebron is perfectly located in the Tri-State area where Ohio, Kentucky, and Indiana all meet - you can visit three states in one day!. Should we find another jet plane?
```

## Adding Cities to the Database

When adding new cities to `app/cities.json`:

### Process:
1. **Check existing cities**: Use Grep to search for the city name to ensure it doesn't already exist
2. **Research city information**: Use WebSearch to gather:
   - Current population (latest available data)
   - State/province (or null for countries without states)
   - Country name
   - Interesting, kid-friendly facts about the city

### Fun Facts Style Guide:
- **Always start each fact with the city name** (e.g., "Tokyo has...", "Brisbane is home to...", "Cork was...")
- Write in a child-friendly, enthusiastic tone with exclamation points
- Use comparisons that kids can understand ("bigger than 75 football fields!")
- Include specific numbers and superlatives when possible ("oldest", "largest", "most")
- Mix historical, cultural, geographical, and modern facts
- Keep each fact to 1-2 sentences maximum
- Add 4-5 fun facts per city
- Use descriptive, colorful language that sparks imagination
- Include unique local features, food, landmarks, or cultural elements

### JSON Structure:
```json
"CityName": {
    "city": "CityName",
    "state": "State" or null,
    "country": "Country",
    "population": number,
    "fun_facts": [
        "CityName has exciting description and specific details!",
        "CityName is famous for history or culture that kids would find interesting!",
        "CityName features unique local traditions or fun landmarks!",
        "CityName sits in amazing geography with nature or incredible buildings!",
        "CityName offers amazing food, activities, or modern attractions!"
    ]
}
```

### Example Reference:
See existing cities like Tokyo, Shanghai, or Nice for tone and style examples. Each fact should be educational but entertaining, helping kids learn while staying engaged.


## TODO: Smart Fun Facts Based on User Location

### Feature: Use Departure City Fun Facts When User is at Destination

**Problem**: Currently, the app always shows fun facts about the destination city, even when the user is already located in that city.

**Solution**:
1. Extract city information from existing `ipapi.co` IP geolocation response (currently only using lat/lng)
2. Compare user's city with flight destination city
3. If they match, show fun facts about the departure/origin city instead
4. Include friendly intro like "Since you're already in {destination}, here's something about where this flight came from!"

**Implementation Notes**:
- Modify `get_location_from_ip()` in `location_utils.py` to return city data alongside coordinates
- Update `generate_flight_text_for_aircraft()` in `flight_text.py` to accept and use user city
- Add simple string comparison with case-insensitive matching
- Graceful fallback to current behavior if city data unavailable

**Benefits**:
- More relevant content for local users
- Educational value about departure cities
- Better user experience with personalized context

**Files to modify**: `app/location_utils.py`, `app/flight_text.py`, function callers


## TODO: Track Aircraft Diversity Analytics

**Problem**: We need visibility into how diverse the selected aircraft are (cargo/passenger mix, destination variety, provider source), but we currently do not emit analytics events that capture these details.

**Goals**:
1. Emit Mixpanel (or similar) events whenever aircraft are selected.
2. Capture metrics such as number of unique destinations, presence of cargo/private operators, distance spread, and provider breakdown.
3. Store enough metadata to diagnose why diversity rules might not trigger.

**Implementation Ideas**:
- Extend `app/analytics.py` with a helper like `track_aircraft_diversity_event()` that accepts the final aircraft list plus summary stats.
- Compute summary statistics in the selection code (likely `app/main.py`) before returning results.
- Include experiment flags/versioning so we can compare new selection strategies later.
- Consider logging both "raw provider results" and "final selection" metrics to understand filtering impact.

**Benefits**:
- Observability into whether diversity goals are being met.
- Data to justify future tweaks to selection algorithms.
- Easier debugging when users report repetitive or uninteresting flights.

**Files to modify**: `app/main.py`, `app/analytics.py`, and any modules responsible for aircraft selection.


## TODO: Clean Up Error Handling and Logging

**Scope**: Review and improve error handling and logging throughout the application

**Tasks**:
- Standardize error logging format and levels across all modules
- Review exception handling patterns for consistency
- Ensure all external API calls have proper error handling
- Add appropriate try/except blocks where missing
- Consider structured logging for better observability
- Review and clean up debug log statements
- Ensure analytics failures don't break user-facing functionality
- Add request ID tracking for better debugging

**Files to review**: All modules in `app/`, particularly:
- `app/main.py` - Main application logic and TTS providers
- `app/scanning.py` - Pre-generation flow
- `app/analytics.py` - Analytics tracking
- `app/location_utils.py` - IP geolocation
- `app/s3_cache.py` - S3 caching operations


## TODO: Dynamic Intro for Premium Scanning Endpoint

**Problem**: The `/scanning` endpoint currently streams a static pre-recorded MP3 file (`scanning.mp3`). This misses an opportunity for personalization and variety.

**Solution**: Generate dynamic intro audio that can include:
- Time-of-day greetings ("Good morning!", "Good evening!")
- Location-aware content ("Let's see what's flying over London today!")
- Seasonal or weather references
- Variety in phrasing to keep the experience fresh

**Implementation Ideas**:
1. Generate intro text dynamically based on user context (time, location, etc.)
2. Use TTS to generate the intro audio
3. Cache generated intros with a key based on the dynamic factors (e.g., `scanning_{city}_{time_of_day}_{provider}.mp3`)
4. Fall back to static MP3 if TTS fails

**Considerations**:
- Balance between variety and caching efficiency
- TTS latency - intro needs to start playing quickly
- Could pre-generate common combinations during off-peak hours

**Files to modify**: `app/scanning.py`, potentially new `app/intro_text.py` for text generation


