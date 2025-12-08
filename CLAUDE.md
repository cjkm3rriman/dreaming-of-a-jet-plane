# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a FastAPI application called "dreaming-of-a-jet-plane" that uses Yoto to help users learn about jet planes in the sky and their destinations. The project is deployed on Railway at: https://dreaming-of-a-jet-plane-production.up.railway.app

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

**IMPORTANT**: When the user asks to "deploy", this means commit all changes to GitHub which automatically triggers Railway deployment. Use git add, commit, and push to deploy the application.

## Environment Variables

**IMPORTANT**: This project uses **Railway environment variables**, NOT local `.env` files. All environment variables are configured in the Railway dashboard at:
https://railway.app/project/dreaming-of-a-jet-plane/settings

The `.env.example` file serves as documentation only. When testing locally, environment variables must be exported manually or set in your shell.

The application requires several environment variables for full functionality:

### Required
- `FR24_API_KEY`: Flightradar24 API key for live flight data
- `GOOGLE_API_KEY`: Google API key for Gemini TTS
- `TTS_PROVIDER`: TTS provider to use (options: `elevenlabs`, `polly`, `google`, `fallback`)
- `LIVE_AIRCRAFT_PROVIDER`: Primary live aircraft provider key (e.g., `fr24` or `airlabs`)

### Optional
- `ELEVENLABS_TEXT_TO_VOICE_API_KEY`: ElevenLabs API key for text-to-speech (if using ElevenLabs)
- `MIXPANEL_TOKEN`: Mixpanel project token for analytics tracking
- `PROVIDER_OVERRIDE_SECRET`: Shared secret for overriding both TTS and live aircraft providers via query parameters
- `LIVE_AIRCRAFT_PROVIDER_FALLBACKS`: Comma-separated list of fallback providers to try if the primary fails
- `AIRLABS_API_KEY`: Airlabs API key (needed if `airlabs` is used as a primary or fallback provider)
- AWS S3 credentials for caching (if using S3 cache)
- AWS Polly credentials (if using Polly TTS provider)

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


## TODO: Improve Aircraft Selection Diversity and Filtering

**Problem**: With multiple providers (FR24 and Airlabs) returning different result sets, we need smarter aircraft selection to provide diverse, interesting flight information while filtering out less relevant flights.

**Goals**:
1. **Filter out cargo and private flights** - Focus on passenger flights that are more interesting for users
2. **Prioritize destination diversity** - Avoid showing 3 flights all going to the same city
3. **Consider destination rareness** - Prioritize interesting/exotic destinations over common short-haul routes
4. **Leverage multiple providers** - Use Airlabs' broader coverage to find more diverse results
5. **Smart selection algorithm** - Balance distance, destination interest, and diversity

**Implementation Ideas**:

### 1. Cargo & Private Flight Filtering
- Use existing `is_cargo_airline()` and `is_private_airline()` functions from `airline_database.py`
- Filter these out early in the selection process unless no passenger flights are available
- Track analytics on filtered vs. shown flights

### 2. Destination Diversity Scoring
- When selecting 3 aircraft, prefer flights going to different cities/countries
- Penalize selecting multiple flights to the same destination
- Consider: "Flight to Paris, London, Tokyo" > "Flight to Paris, Paris, Lyon"

### 3. Destination Rareness/Interest Score
- Score destinations based on:
  - Distance from user (longer = more interesting)
  - Population size (major cities = more interesting, from `cities.json`)
  - Geographic diversity (different continents/regions)
  - Whether we have fun facts for the destination (indicates it's noteworthy)
- Create a simple scoring system to rank flights

### 4. Selection Algorithm
```
For each aircraft in nearby results:
  - Skip if cargo/private (unless no passenger flights available)
  - Calculate interest score = (distance_score + destination_score + diversity_score)
  - distance_score: normalize distance to 0-100 scale
  - destination_score: based on city population, continent, fun facts availability
  - diversity_score: bonus points if destination differs from already-selected flights

Select top 3 flights by interest score
```

### 5. Provider Strategy
- Try primary provider first (FR24 or Airlabs)
- If results are low-diversity (e.g., all same destination, mostly cargo), try fallback provider
- Merge results from multiple providers and apply selection algorithm
- Track which provider contributed each selected flight in analytics

**Benefits**:
- More interesting flight information for users
- Better educational value with diverse destinations
- Avoid showing boring cargo/private flights
- Make better use of multiple provider data

**Files to modify**:
- `app/main.py` - Add aircraft selection/filtering logic
- `app/airline_database.py` - Already has cargo/private detection (✓)
- `app/cities_database.py` - Use for destination scoring
- `app/aircraft_providers/*.py` - Consider filtering at provider level
- `app/analytics.py` - Track diversity metrics

**Phase 1 (Quick Wins)**:
- Filter out cargo airlines using existing `is_cargo_airline()`
- Filter out private/charter airlines using existing `is_private_airline()`
- Simple destination deduplication (don't show 3 flights to same city)

**Phase 2 (Smart Selection)**:
- Implement destination interest scoring
- Add diversity bonuses to selection algorithm
- Consider distance and destination population

**Phase 3 (Advanced)**:
- Multi-provider result merging with smart selection
- Geographic diversity scoring (different continents)
- Analytics dashboard for selection quality


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
