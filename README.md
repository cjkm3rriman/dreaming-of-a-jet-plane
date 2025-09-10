# dreaming-of-a-jet-plane
Magically turn your Yoto player into a Jet Plane Scanner that finds airplanes in the skies around you, then teaches you all about them and the faraway destinations they are headed.

[![Dreaming of a Jet Plane](https://img.youtube.com/vi/heSlOrH17po/maxresdefault.jpg)](https://youtu.be/heSlOrH17po)

Check it out: https://share.yoto.co/s/27Y3g3KjqiWkIqdTWc27g2


## tech stack

### Core Framework & Language
- **Python 3.13+** - Core programming language
- **FastAPI** - Modern async web framework with automatic API documentation
- **UV** - Fast Python package manager for dependency management

### External APIs & Services
- **Flightradar24 API** - Unified live flight tracking with comprehensive aircraft and route data
- **ElevenLabs API** - Primary text-to-speech voice synthesis (Edward voice)
- **AWS Polly** - Secondary/fallback text-to-speech with neural voices (Amy voice)
- **ipapi.co** - IP geolocation service for converting IP addresses to coordinates
- **Mixpanel** - Analytics

### HTTP Client & Networking
- **httpx** - Async HTTP client for API requests and MP3 streaming
- **boto3** - AWS SDK for Python (Polly TTS and S3 operations)

### Cloud Services & Infrastructure
- **Railway** - Deployment platform with automatic CI/CD from GitHub
- **Amazon S3** - Object storage for MP3 file hosting and caching (us-east-2 region)

### Development Tools
- **Claude Code** - AI-powered development assistant for code generation and debugging