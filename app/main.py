from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
import httpx
import math
import os
import logging
from typing import List, Dict, Any, Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
from .aircraft_database import get_aircraft_name
from .airport_database import get_city_country
from .airline_database import get_airline_name
from .intro import stream_intro, intro_options
from .scanning import stream_scanning, scanning_options
from .voice_test import stream_voice_test, voice_test_options

app = FastAPI()

# Flightradar24 API configuration
FR24_API_KEY = os.getenv("FR24_API_KEY")
FR24_BASE_URL = "https://fr24api.flightradar24.com"

# ElevenLabs API configuration
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_TEXT_TO_VOICE_API_KEY")
ELEVENLABS_BASE_URL = "https://api.elevenlabs.io/v1"
DEFAULT_VOICE_ID = "goT3UYdM9bhm0n2lmKQx"  # Edward voice - British, Dark, Seductive, Low

def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points using Haversine formula (in km)"""
    R = 6371  # Earth's radius in kilometers
    
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    
    a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    
    return R * c

async def convert_text_to_speech(text: str) -> tuple[bytes, str]:
    """Convert text to speech using ElevenLabs API
    
    Returns:
        tuple: (audio_content, error_message)
        - audio_content: MP3 audio bytes if successful, empty bytes if failed
        - error_message: Empty string if successful, error description if failed
    """
    if not ELEVENLABS_API_KEY:
        logger.warning("ElevenLabs API key not configured")
        return b"", "ElevenLabs API key not configured"
    
    try:
        # Prepare the request to ElevenLabs API
        url = f"{ELEVENLABS_BASE_URL}/text-to-speech/{DEFAULT_VOICE_ID}"
        
        headers = {
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json"
        }
        
        payload = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.5
            }
        }
        
        logger.info(f"ElevenLabs API Request: URL={url}")
        logger.info(f"ElevenLabs API Text: {text}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            
            logger.info(f"ElevenLabs API Response: Status={response.status_code}")
            
            if response.status_code == 200:
                return response.content, ""
            else:
                # Log error response for debugging
                try:
                    error_body = response.text
                    logger.error(f"ElevenLabs API Error: Status={response.status_code}, Body={error_body}")
                except:
                    logger.error(f"ElevenLabs API Error: Status={response.status_code}, Body=<unable to read>")
                
                return b"", f"ElevenLabs API returned status {response.status_code}"
                
    except httpx.TimeoutException:
        logger.error(f"ElevenLabs API Timeout: Request timed out after 30 seconds")
        return b"", "ElevenLabs API timeout (30 seconds exceeded)"
    except httpx.RequestError as e:
        logger.error(f"ElevenLabs API Connection Error: {str(e)}")
        return b"", f"ElevenLabs API connection error: {str(e)}"
    except Exception as e:
        logger.error(f"ElevenLabs API Unexpected Error: {str(e)}")
        return b"", f"ElevenLabs API unexpected error: {str(e)}"

async def get_nearby_aircraft(lat: float, lng: float, radius_km: float = 100) -> tuple[List[Dict[str, Any]], str]:
    """Get aircraft near the given coordinates using Flightradar24 API
    
    Returns:
        tuple: (aircraft_list, error_message)
        - aircraft_list: List of aircraft data
        - error_message: Empty string if successful, error description if failed
    """
    if not FR24_API_KEY:
        logger.warning("Flightradar24 API key not configured")
        return [], "Flightradar24 API key not configured"
    
    try:
        # Create bounding box for location filtering
        lat_delta = radius_km / 111.0  # 1 degree lat ≈ 111 km
        lon_delta = radius_km / (111.0 * math.cos(math.radians(lat)))  # Adjust for longitude
        
        bounds = {
            "south": lat - lat_delta,
            "north": lat + lat_delta, 
            "west": lng - lon_delta,
            "east": lng + lon_delta
        }
        
        url = f"{FR24_BASE_URL}/api/live/flight-positions/full"
        headers = {
            "Authorization": f"Bearer {FR24_API_KEY}",
            "Accept": "application/json",
            "Accept-Version": "v1"
        }
        
        params = {
            "bounds": f"{bounds['north']:.3f},{bounds['south']:.3f},{bounds['west']:.3f},{bounds['east']:.3f}",
            "limit": 1,  # Limit to 1 result for testing
            "categories": "P"  # Filter to passenger aircraft only
        }
        
        logger.info(f"Flightradar24 API Request: URL={url}")
        logger.info(f"Flightradar24 API Params: bounds={params['bounds']}, limit={params['limit']}")
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, params=params, timeout=10.0)
            
            logger.info(f"Flightradar24 API Response: Status={response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"Flightradar24 API Response: Found {len(data.get('data', []))} flights")
                logger.info(f"Raw flight data: {data.get('data', [])}")
                
                flights = data.get('data', [])
                aircraft_list = []
                
                for flight in flights:
                    try:
                        # Extract position data using Flightradar24 field names
                        aircraft_lat = flight.get('lat')
                        aircraft_lon = flight.get('lon')
                        
                        logger.info(f"Processing flight: {flight.get('callsign')} at lat={aircraft_lat}, lon={aircraft_lon}")
                        
                        if aircraft_lat is None or aircraft_lon is None:
                            logger.info(f"Skipping flight {flight.get('callsign')}: missing coordinates")
                            continue
                            
                        distance = calculate_distance(lat, lng, aircraft_lat, aircraft_lon)
                        logger.info(f"Flight {flight.get('callsign')} distance: {distance:.2f}km (limit: {radius_km}km)")
                        
                        # Skip if outside radius (API bounds are approximate)
                        if distance > radius_km:
                            logger.info(f"Skipping flight {flight.get('callsign')}: outside radius")
                            continue
                        
                        callsign = flight.get('callsign', '').strip() or "Unknown"
                        
                        # Get origin and destination airport information
                        origin_iata = flight.get('orig_iata')
                        dest_iata = flight.get('dest_iata')
                        
                        origin_city, origin_country = get_city_country(origin_iata) if origin_iata else (None, None)
                        dest_city, dest_country = get_city_country(dest_iata) if dest_iata else (None, None)
                        
                        # Get airline information from operating_as field (ICAO code)
                        airline_icao = flight.get('operating_as')
                        airline_name = get_airline_name(airline_icao) if airline_icao else None
                        
                        aircraft_info = {
                            "icao24": flight.get('hex'),
                            "callsign": callsign,
                            "flight_number": flight.get('flight'),
                            "airline_icao": airline_icao,
                            "airline_name": airline_name,
                            "aircraft_registration": flight.get('reg'),
                            "aircraft_icao": flight.get('type'),
                            "aircraft": get_aircraft_name(flight.get('type', '')),
                            "origin_airport": origin_iata,
                            "origin_city": origin_city,
                            "origin_country": origin_country,
                            "destination_airport": dest_iata,
                            "destination_city": dest_city,
                            "destination_country": dest_country,
                            "country": None,  # Not available in this API response
                            "latitude": aircraft_lat,
                            "longitude": aircraft_lon,
                            "altitude": flight.get('alt', 0),
                            "velocity": flight.get('gspeed', 0),
                            "heading": flight.get('track', 0),
                            "distance_km": round(distance, 2),
                            "status": None,  # Not available in this API response
                            "eta": flight.get('eta'),
                            "fr24_id": flight.get('fr24_id')
                        }
                        
                        aircraft_list.append(aircraft_info)
                        logger.info(f"Added flight {callsign} to aircraft list")
                        
                    except Exception as e:
                        logger.warning(f"Error processing flight data: {e}")
                        continue
                
                # Sort by distance and return closest aircraft
                aircraft_list.sort(key=lambda x: x["distance_km"])
                if aircraft_list:
                    return aircraft_list[:1], ""
                else:
                    return [], "No passenger aircraft found within 100km radius"
                
            else:
                error_msg = f"Flightradar24 API returned HTTP {response.status_code}"
                logger.error(f"Flightradar24 API Error: Status={response.status_code}, Body={response.text[:500]}")
                return [], error_msg
                
    except httpx.TimeoutException:
        logger.error(f"Flightradar24 API Timeout: Request timed out after 10 seconds")
        return [], "Flightradar24 API request timed out (10 seconds)"
    except httpx.RequestError as e:
        logger.error(f"Flightradar24 API Connection Error: {str(e)}")
        return [], f"Network connection error: {str(e)}"
    except Exception as e:
        logger.error(f"Flightradar24 API Unexpected Error: {str(e)}")
        return [], f"Unexpected error: {str(e)}"
    
    return [], "Unknown error occurred"

async def get_location_from_ip(ip: str) -> tuple[float, float]:
    """Get latitude and longitude from IP address using ipapi.co"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"https://ipapi.co/{ip}/json/")
            if response.status_code == 200:
                data = response.json()
                return data.get("latitude", 0.0), data.get("longitude", 0.0)
    except Exception:
        pass
    return 0.0, 0.0

@app.get("/")
async def read_root(request: Request, lat: float = None, lng: float = None):
    # Check for real IP in common proxy headers
    client_ip = (
        request.headers.get("x-forwarded-for", "").split(",")[0].strip() or
        request.headers.get("x-real-ip") or
        request.headers.get("cf-connecting-ip") or  # Cloudflare
        request.client.host
    )
    
    # Get latitude and longitude - use parameters if provided, otherwise IP lookup
    if lat is not None and lng is not None:
        # Use provided coordinates
        logger.info(f"Using provided coordinates: lat={lat}, lng={lng}")
        user_lat, user_lng = lat, lng
    else:
        # Get latitude and longitude from IP
        user_lat, user_lng = await get_location_from_ip(client_ip)
        logger.info(f"Using IP-based location: lat={user_lat}, lng={user_lng} for IP {client_ip}")
    
    # Get nearby aircraft
    aircraft, error_message = await get_nearby_aircraft(user_lat, user_lng)
    
    # Return descriptive sentence about the aircraft
    if aircraft and len(aircraft) > 0:
        closest_aircraft = aircraft[0]
        
        # Extract values for the sentence template
        distance_km = closest_aircraft.get("distance_km", "unknown")
        flight_number = closest_aircraft.get("flight_number") or closest_aircraft.get("callsign", "unknown flight")
        airline_name = closest_aircraft.get("airline_name")
        destination_city = closest_aircraft.get("destination_city", "an unknown destination")
        destination_country = closest_aircraft.get("destination_country", "an unknown country")
        
        # Build flight identifier with airline name if available
        if airline_name:
            flight_identifier = f"{airline_name} flight {flight_number}"
        else:
            flight_identifier = f"flight {flight_number}"
        
        # Build the descriptive sentences
        detection_sentence = f"Jet plane detected in the sky overhead {distance_km} km from your Yoto player."
        
        if destination_city == "an unknown destination" or destination_country == "an unknown country":
            flight_sentence = f"This is {flight_identifier}, travelling to an unknown destination."
        else:
            flight_sentence = f"This is {flight_identifier}, travelling to {destination_city} in {destination_country}."
        
        sentence = f"{detection_sentence} {flight_sentence}"
        
        # Convert sentence to speech
        audio_content, tts_error = await convert_text_to_speech(sentence)
        
        if audio_content and not tts_error:
            # Return MP3 audio
            response_headers = {
                "Content-Type": "audio/mpeg",
                "Content-Length": str(len(audio_content)),
                "Accept-Ranges": "bytes",
                "Cache-Control": "public, max-age=3600",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
                "Access-Control-Allow-Headers": "Range, Content-Range, Content-Length",
                "Access-Control-Expose-Headers": "Content-Length, Content-Range, Accept-Ranges"
            }
            
            return StreamingResponse(
                iter([audio_content]),
                status_code=200,
                media_type="audio/mpeg",
                headers=response_headers
            )
        else:
            # Fall back to text if TTS fails
            return {"message": sentence, "tts_error": tts_error}
    else:
        # Handle error cases with descriptive sentence
        if error_message:
            error_sentence = f"No aircraft detected nearby, because of {error_message.lower()}"
        else:
            error_sentence = "No aircraft detected nearby, because no passenger aircraft found within 100km radius"
        
        # Convert error sentence to speech
        audio_content, tts_error = await convert_text_to_speech(error_sentence)
        
        if audio_content and not tts_error:
            # Return MP3 audio
            response_headers = {
                "Content-Type": "audio/mpeg",
                "Content-Length": str(len(audio_content)),
                "Accept-Ranges": "bytes",
                "Cache-Control": "public, max-age=3600",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
                "Access-Control-Allow-Headers": "Range, Content-Range, Content-Length",
                "Access-Control-Expose-Headers": "Content-Length, Content-Range, Accept-Ranges"
            }
            
            return StreamingResponse(
                iter([audio_content]),
                status_code=200,
                media_type="audio/mpeg",
                headers=response_headers
            )
        else:
            # Fall back to text if TTS fails
            return {"message": error_sentence, "tts_error": tts_error}

@app.options("/")
async def root_options():
    """Handle CORS preflight requests for main endpoint"""
    return StreamingResponse(
        iter([b""]),
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
            "Access-Control-Allow-Headers": "Range, Content-Range, Content-Length",
            "Access-Control-Max-Age": "3600"
        }
    )

@app.get("/intro.mp3")
async def intro_endpoint(request: Request):
    """Stream MP3 file from S3"""
    return await stream_intro(request)

@app.options("/intro.mp3") 
async def intro_options_endpoint():
    """Handle CORS preflight requests for /intro.mp3 endpoint"""
    return await intro_options()

@app.get("/scanning.mp3")
async def scanning_endpoint(request: Request):
    """Stream scanning MP3 file from S3"""
    return await stream_scanning(request)

@app.options("/scanning.mp3") 
async def scanning_options_endpoint():
    """Handle CORS preflight requests for /scanning.mp3 endpoint"""
    return await scanning_options()

@app.get("/voice-test")
async def voice_test_endpoint(request: Request):
    """Convert text to speech using ElevenLabs API and stream audio"""
    return await stream_voice_test(request)

@app.options("/voice-test") 
async def voice_test_options_endpoint():
    """Handle CORS preflight requests for /voice-test endpoint"""
    return await voice_test_options()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)