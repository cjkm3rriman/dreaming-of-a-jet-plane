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