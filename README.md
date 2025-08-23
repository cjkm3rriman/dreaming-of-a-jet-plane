# dreaming-of-a-jet-plane
Use your Yoto to Learn about the jet planes in the sky around you right now and what wonderful destinations they are headed to.

## tech stack

### Core Framework & Language
- **Python 3.13+** - Core programming language
- **FastAPI** - Modern async web framework with automatic API documentation
- **UV** - Fast Python package manager for dependency management

### External APIs & Services
- **Flightradar24 API** - Unified live flight tracking with comprehensive aircraft and route data
- **ElevenLabs API** - Text-to-speech voice synthesis for audio content
- **ipapi.co** - IP geolocation service for converting IP addresses to coordinates

### HTTP Client & Networking
- **httpx** - Async HTTP client for API requests and MP3 streaming

### Cloud Services & Infrastructure
- **Railway** - Deployment platform with automatic CI/CD from GitHub
- **Amazon S3** - Object storage for MP3 file hosting (us-east-2 region)

### Development Tools
- **Claude Code** - AI-powered development assistant for code generation and debugging

## TODO

### S3 Cache Cleanup Configuration
Add S3 lifecycle policy to automatically clean up expired cache files:

**Via AWS Console:**
1. Go to S3 Console → `dreaming-of-a-jet-plane` bucket
2. Management tab → Lifecycle rules → Create lifecycle rule
3. Rule name: `FlightMP3CacheCleanup`
4. Rule scope: Limit to prefix `cache/`  
5. Lifecycle rule actions: ✓ Expire current versions of objects
6. Days after object creation: `1`
7. Create rule

This will automatically delete cache files older than 1 day to prevent storage costs from accumulating.

