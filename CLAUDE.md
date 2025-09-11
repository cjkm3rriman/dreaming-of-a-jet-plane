# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a FastAPI application called "dreaming-of-a-jet-plane" that uses Yoto to help users learn about jet planes in the sky and their destinations. The project is deployed on Railway at: https://dreaming-of-a-jet-plane-production.up.railway.app

## Tech Stack

- **Python 3.13+**: Core language
- **UV**: Python package manager for dependency management
- **FastAPI**: Web framework with standard extras
- **Flightradar24 API**: Live flight tracking and aircraft data
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

The application requires several environment variables for full functionality:

### Required
- `FR24_API_KEY`: Flightradar24 API key for live flight data
- `ELEVENLABS_TEXT_TO_VOICE_API_KEY`: ElevenLabs API key for text-to-speech

### Optional
- `MIXPANEL_TOKEN`: Mixpanel project token for analytics tracking
- AWS S3 credentials for caching (if using S3 cache)

See `.env.example` for a template of environment variables.

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
        "Fact 1 with exciting description and specific details!",
        "Fact 2 about history or culture that kids would find interesting!",
        "Fact 3 about unique features or fun local traditions!",
        "Fact 4 about geography, nature, or amazing buildings!",
        "Fact 5 about food, activities, or modern attractions!"
    ]
}
```

### Example Reference:
See existing cities like Tokyo, Shanghai, or Nice for tone and style examples. Each fact should be educational but entertaining, helping kids learn while staying engaged.

## TODO: Priority Cities to Add

Based on analysis of major international flight destinations missing from the cities database, these cities should be prioritized for addition:

### Highest Priority (Major International Hubs)
3. **Perth, Australia** - Major Australian city
4. **Wellington, New Zealand** - National capital
5. **Marrakech, Morocco** - Iconic UNESCO tourist destination

### High Priority (Regional Capitals & Business Hubs)
6. **Kuwait City, Kuwait** - Gulf business center
7. **Chiang Mai, Thailand** - Major Thai tourist city
8. **Glasgow, Scotland** - Major Scottish cultural center
9. **Krakow, Poland** - UNESCO World Heritage site
10. **Quito, Ecuador** - UNESCO site, Galapagos gateway

### Medium Priority (Important Regional Destinations)
11. **Manama, Bahrain** - Gulf financial center
12. **Muscat, Oman** - Growing tourism hub
13. **Cebu, Philippines** - Key regional hub
14. **Macau** - Gaming and tourism destination
15. **Brisbane, Australia** - Gateway to Gold Coast
16. **Christchurch, New Zealand** - South Island hub
17. **Salzburg, Austria** - Mozart's birthplace
18. **Seville, Spain** - Cultural capital of Andalusia
19. **Accra, Ghana** - West African business hub
20. **San José, Costa Rica** - Eco-tourism hub
21. **Cartagena, Colombia** - UNESCO coastal gem

### European Destinations (Medium-High Priority)
22. **Corfu, Greece** - Ionian island paradise
23. **Exeter, United Kingdom** - Historic English cathedral city
24. **Paphos, Cyprus** - UNESCO archaeological site
25. **Split, Croatia** - Adriatic coastal gem with Roman heritage
26. **Girona, Spain** - Medieval Catalonian city
27. **Poznan, Poland** - Historic Polish cultural center
28. **Rzeszow, Poland** - Growing regional hub
29. **Sibiu, Romania** - Transylvanian medieval city
30. **Faro, Portugal** - Gateway to the Algarve

### Middle East/Africa Destinations (Medium Priority)
31. **Hurghada, Egypt** - Red Sea resort destination
32. **Rabat, Morocco** - Capital city and UNESCO site
33. **Dalaman, Turkey** - Mediterranean coastal gateway

These cities represent major gaps in airline destinations and would provide better global coverage for users learning about international flight destinations.

## AWS Polly TTS Integration Planning

Research and planning for adding AWS Polly as a TTS provider option alongside ElevenLabs (see TODO comments in `app/main.py:62-65`).

### Environment Configuration
```bash
# Provider selection
TTS_PROVIDER=elevenlabs  # Options: "elevenlabs", "polly", or "fallback" (try ElevenLabs, fallback to Polly)

# AWS Polly configuration
AWS_POLLY_VOICE_ID=Arthur           # British male neural voice (recommended)
AWS_POLLY_ENGINE=neural             # Options: generative, neural, standard
AWS_POLLY_REGION=us-east-1         
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret

# Voice model settings (configurable for future changes)
AWS_POLLY_OUTPUT_FORMAT=mp3
AWS_POLLY_SAMPLE_RATE=24000
```

### AWS Polly Voice Research Findings

**Available British Voices:**
- **Amy (Female, Generative)** - Only British generative voice available
- **Arthur (Male, Neural only)** - Not available in generative engine yet
- No direct male British generative voice equivalent to current Edward voice

**Pricing Comparison (per million characters):**
- ElevenLabs: ~$22
- AWS Polly Generative: $30
- AWS Polly Neural: $16
- **Free tier**: 100k characters/month generative, 1M characters/month neural

### Integration Architecture Options

**Provider Strategy Options:**
1. **Primary/Fallback**: Try ElevenLabs first, fallback to Polly on failure
2. **Switch**: Complete switch to Polly via env variable
3. **Load Balance**: Route based on usage/cost thresholds

**Function Structure:**
```python
async def convert_text_to_speech(text: str) -> tuple[bytes, str]:
    provider = os.getenv("TTS_PROVIDER", "elevenlabs")
    
    if provider == "elevenlabs":
        return await elevenlabs_tts(text)
    elif provider == "polly":
        return await polly_tts(text)
    elif provider == "fallback":
        result = await elevenlabs_tts(text)
        if result[1]:  # Error occurred
            return await polly_tts(text)
        return result
```

**Voice Quality Trade-offs:**
- Current: ElevenLabs Edward (British Male, Dark, Seductive)
- Option 1: AWS Polly Amy (British Female, Conversational, Generative)
- **Option 2: AWS Polly Arthur (British Male, Neural only, lower cost) - RECOMMENDED**
  - Use `<prosody rate="medium">` SSML for optimal pacing
  - Best match for current Edward voice characteristics
  - Lower cost than generative ($16 vs $30 per million characters)

### AWS Requirements
- **Region**: us-east-1 (required for generative voices)
- **Dependencies**: boto3, botocore
- **Credentials**: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
- **Permissions**: polly:SynthesizeSpeech