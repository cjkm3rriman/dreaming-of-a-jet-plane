# dreaming-of-a-jet-plane
Use your Yoto to Learn about the jet planes in the sky around you right now and what wonderful destinations they are headed to.

## tech stack

### Core Framework & Language
- **Python 3.13+** - Core programming language
- **FastAPI** - Modern async web framework with automatic API documentation
- **UV** - Fast Python package manager for dependency management

### External APIs & Services
- **OpenSky Network API** - Real-time aircraft tracking and flight data with extended metadata
- **FlightLabs API** - Commercial flight details lookup by ICAO24 transponder address
- **ipapi.co** - IP geolocation service for converting IP addresses to coordinates

### HTTP Client & Networking
- **httpx** - Async HTTP client for API requests and MP3 streaming

### Cloud Services & Infrastructure
- **Railway** - Deployment platform with automatic CI/CD from GitHub
- **Amazon S3** - Object storage for MP3 file hosting (us-east-2 region)

### Development Tools
- **Claude Code** - AI-powered development assistant for code generation and debugging

### Data & Intelligence
- **Aircraft Database** - Custom ICAO aircraft type mappings (60+ aircraft models)
- **Commercial Flight Filtering** - Regex-based patterns to identify airline vs private aircraft
- **Geographic Algorithms** - Haversine formula for accurate distance calculations

### Key Features
- **Smart Commercial Aircraft Detection** - Filters for airlines only (UAL, DAL, SWA, etc.)
- **Real-time IP Geolocation** - User location detection via IP address
- **ICAO24 Aircraft Identification** - Permanent transponder address lookup
- **Human-readable Aircraft Names** - "Boeing 737 MAX 8" instead of "B38M"
- **MP3 Audio Streaming** - Direct S3 streaming with range request support
- **Comprehensive Flight Details** - Airline, aircraft type, origin/destination airports
- **Geographic Proximity Search** - 100km radius bounding box calculations
- **Async/await Architecture** - High performance concurrent API calls