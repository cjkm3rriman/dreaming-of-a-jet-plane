from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, HTMLResponse
import httpx
import math
import os
import asyncio
import logging
from typing import List, Dict, Any, Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
from .aircraft_database import get_aircraft_name, get_passenger_capacity
from .airport_database import get_city_country
from .airline_database import get_airline_name
from .intro import stream_intro, intro_options
from .scanning import stream_scanning, scanning_options
from .voice_test import stream_voice_test, voice_test_options
from .s3_cache import s3_cache
from .flight_text import generate_flight_text, generate_flight_text_for_aircraft
from .location_utils import get_user_location

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
            "model_id": "eleven_turbo_v2",
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

async def get_nearby_aircraft(lat: float, lng: float, radius_km: float = 100, limit: int = 3) -> tuple[List[Dict[str, Any]], str]:
    """Get aircraft near the given coordinates using Flightradar24 API with caching
    
    Args:
        lat: Latitude
        lng: Longitude
        radius_km: Search radius in kilometers
        limit: Maximum number of aircraft to return (default 3)
    
    Returns:
        tuple: (aircraft_list, error_message)
        - aircraft_list: List of aircraft data
        - error_message: Empty string if successful, error description if failed
    """
    if not FR24_API_KEY:
        logger.warning("Flightradar24 API key not configured")
        return [], "Flightradar24 API key not configured"
    
    # Check API response cache first
    api_cache_key = s3_cache.generate_cache_key(lat, lng, content_type="json")
    cached_aircraft = await s3_cache.get(api_cache_key, content_type="json")
    
    if cached_aircraft:
        logger.info(f"API cache hit for location: lat={lat}, lng={lng}")
        # Return up to limit aircraft from cached data
        aircraft_list = cached_aircraft.get('aircraft', [])[:limit]
        return aircraft_list, ""
    
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
            "limit": 10,  # Get multiple aircraft to find the actual nearest
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
                        
                        # Get airline information from painted_as field (ICAO code)
                        airline_icao = flight.get('painted_as')
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
                            "passenger_capacity": get_passenger_capacity(flight.get('type', '')),
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
                            "distance_km": round(distance),
                            "distance_miles": round(distance * 0.621371),
                            "status": None,  # Not available in this API response
                            "eta": flight.get('eta'),
                            "fr24_id": flight.get('fr24_id')
                        }
                        
                        aircraft_list.append(aircraft_info)
                        logger.info(f"Added flight {callsign} to aircraft list")
                        
                    except Exception as e:
                        logger.warning(f"Error processing flight data: {e}")
                        continue
                
                # Sort by distance and cache all aircraft data
                aircraft_list.sort(key=lambda x: x["distance_km"])
                
                if aircraft_list:
                    # Cache the aircraft data for future requests (store all aircraft)
                    cache_data = {"aircraft": aircraft_list}
                    asyncio.create_task(s3_cache.set(api_cache_key, cache_data, content_type="json"))
                    logger.info(f"Cached {len(aircraft_list)} aircraft for location: lat={lat}, lng={lng}")
                    
                    # Return up to limit aircraft
                    return aircraft_list[:limit], ""
                else:
                    # Cache empty result too to avoid repeated API calls
                    cache_data = {"aircraft": []}
                    asyncio.create_task(s3_cache.set(api_cache_key, cache_data, content_type="json"))
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


async def handle_plane_endpoint(request: Request, plane_index: int, lat: float = None, lng: float = None, debug: int = 0):
    """Handle individual plane endpoints (/plane/1, /plane/2, /plane/3)
    
    Args:
        request: FastAPI request object
        plane_index: 1-based plane index (1, 2, 3)
        lat: Optional latitude override
        lng: Optional longitude override
        debug: Debug mode flag
    """
    # Get user location using shared function
    user_lat, user_lng = await get_user_location(request, lat, lng)
    
    # Convert to 0-based index
    zero_based_index = plane_index - 1
    
    # Check cache first for the specific plane
    cache_key = s3_cache.generate_cache_key(user_lat, user_lng, plane_index=plane_index)
    cached_mp3 = await s3_cache.get(cache_key)
    
    if cached_mp3:
        logger.info(f"Serving cached MP3 for plane {plane_index} at location: lat={user_lat}, lng={user_lng}")
        response_headers = {
            "Content-Type": "audio/mpeg",
            "Content-Length": str(len(cached_mp3)),
            "Accept-Ranges": "bytes",
            "Cache-Control": "public, max-age=3600",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
            "Access-Control-Allow-Headers": "Range, Content-Range, Content-Length",
            "Access-Control-Expose-Headers": "Content-Length, Content-Range, Accept-Ranges"
        }
        
        return StreamingResponse(
            iter([cached_mp3]),
            status_code=200,
            media_type="audio/mpeg",
            headers=response_headers
        )
    
    # Cache miss - get aircraft data (this will use cached API data if available)
    logger.info(f"Cache miss - generating new MP3 for plane {plane_index} at location: lat={user_lat}, lng={user_lng}")
    aircraft, error_message = await get_nearby_aircraft(user_lat, user_lng, limit=max(3, plane_index))
    
    # Check if we have the requested plane
    if aircraft and len(aircraft) > zero_based_index:
        selected_aircraft = aircraft[zero_based_index]
        sentence = generate_flight_text_for_aircraft(selected_aircraft, user_lat, user_lng)
    elif aircraft and len(aircraft) > 0:
        # Not enough planes, return an appropriate message for this plane index
        if plane_index == 2:
            sentence = "I'm sorry my old chum but scanner bot could only find one jet plane nearby. Try listening to plane 1 instead."
        elif plane_index == 3:
            plane_count = len(aircraft)
            if plane_count == 1:
                sentence = "I'm sorry my old chum but scanner bot could only find one jet plane nearby. Try listening to plane 1 instead."
            else:
                sentence = "I'm sorry my old chum but scanner bot could only find two jet planes nearby. Try listening to plane 1 or plane 2 instead."
    else:
        # No aircraft found at all
        sentence = generate_flight_text([], error_message, user_lat, user_lng)
    
    # Debug mode: return text only without TTS
    if debug == 1:
        logger.info(f"Debug mode: returning HTML without TTS for plane {plane_index}: {sentence[:50]}...")
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Dreaming of a Jet Plane - Plane {plane_index} - Debug Mode</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; background-color: #f5f5f5; }}
                .container {{ background-color: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
                h2 {{ color: #34495e; margin-top: 30px; }}
                table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
                th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
                th {{ background-color: #3498db; color: white; }}
                tr:nth-child(even) {{ background-color: #f9f9f9; }}
                .message {{ background-color: #e8f6f3; padding: 20px; border-left: 4px solid #1abc9c; margin: 20px 0; }}
                .error {{ background-color: #fadbd8; border-left-color: #e74c3c; }}
                .success {{ background-color: #d5f4e6; border-left-color: #27ae60; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🛩️ Dreaming of a Jet Plane - Plane {plane_index} - Debug Mode</h1>
                
                <div class="message {'success' if aircraft and len(aircraft) > zero_based_index else 'error'}">
                    <strong>Generated Message:</strong><br>
                    {sentence}
                </div>
                
                <h2>📍 Location Information</h2>
                <table>
                    <tr><th>Parameter</th><th>Value</th></tr>
                    <tr><td>Latitude</td><td>{user_lat}</td></tr>
                    <tr><td>Longitude</td><td>{user_lng}</td></tr>
                    <tr><td>Plane Index</td><td>{plane_index}</td></tr>
                    <tr><td>Cache Key</td><td>{cache_key}</td></tr>
                </table>
                
                <h2>✈️ Flight Detection Results</h2>
                <table>
                    <tr><th>Parameter</th><th>Value</th></tr>
                    <tr><td>Total Aircraft Found</td><td>{len(aircraft)}</td></tr>
                    <tr><td>Requested Plane Available</td><td>{'Yes' if aircraft and len(aircraft) > zero_based_index else 'No'}</td></tr>
        """
        
        if error_message:
            html_content += f"""
                    <tr><td>Error Message</td><td>{error_message}</td></tr>
            """
        
        html_content += """
                </table>
        """
        
        # Add aircraft details if found
        if aircraft and len(aircraft) > zero_based_index:
            selected_aircraft = aircraft[zero_based_index]
            
            # Get aircraft coordinates for Google Maps link
            aircraft_lat = selected_aircraft.get('latitude')
            aircraft_lng = selected_aircraft.get('longitude')
            
            html_content += f"""
                <h2>🛫 Plane {plane_index} Details</h2>
                <table>
                    <tr><th>Property</th><th>Value</th></tr>
            """
            
            for key, value in selected_aircraft.items():
                if value is not None and value != "":
                    html_content += f"<tr><td>{key.replace('_', ' ').title()}</td><td>{value}</td></tr>"
            
            html_content += "</table>"
            
            # Add Google Maps directions link if we have aircraft coordinates
            if aircraft_lat and aircraft_lng:
                maps_url = f"https://www.google.com/maps/dir/?api=1&origin={user_lat},{user_lng}&destination={aircraft_lat},{aircraft_lng}&travelmode=driving"
                html_content += f"""
                <h2>🗺️ Google Maps</h2>
                <div class="message">
                    <a href="{maps_url}" target="_blank" style="color: #3498db; text-decoration: none; font-weight: bold;">
                        📍 View Directions from Your Location to Plane {plane_index} Position
                    </a>
                    <br><br>
                    <small style="color: #666;">
                        Your Location: {user_lat}, {user_lng}<br>
                        Plane {plane_index} Location: {aircraft_lat}, {aircraft_lng}
                    </small>
                </div>
                """
        
        html_content += """
            </div>
        </body>
        </html>
        """
        
        return HTMLResponse(content=html_content)
    
    # Generate TTS for the sentence
    logger.info(f"Generating TTS for plane {plane_index}: {sentence[:50]}...")
    audio_content, tts_error = await convert_text_to_speech(sentence)
    
    if audio_content and not tts_error:
        logger.info(f"Successfully generated MP3 for plane {plane_index} ({len(audio_content)} bytes) - caching in background")
        # Cache the newly generated MP3 (don't await - do in background)
        asyncio.create_task(s3_cache.set(cache_key, audio_content))
        
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


@app.get("/")
async def read_root(request: Request, lat: float = None, lng: float = None, debug: int = 0):
    # Get user location using shared function
    user_lat, user_lng = await get_user_location(request, lat, lng)
    
    # Check cache first
    cache_key = s3_cache.generate_cache_key(user_lat, user_lng)
    cached_mp3 = await s3_cache.get(cache_key)
    
    if cached_mp3:
        logger.info(f"Serving cached MP3 for location: lat={user_lat}, lng={user_lng}")
        response_headers = {
            "Content-Type": "audio/mpeg",
            "Content-Length": str(len(cached_mp3)),
            "Accept-Ranges": "bytes",
            "Cache-Control": "public, max-age=3600",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
            "Access-Control-Allow-Headers": "Range, Content-Range, Content-Length",
            "Access-Control-Expose-Headers": "Content-Length, Content-Range, Accept-Ranges"
        }
        
        return StreamingResponse(
            iter([cached_mp3]),
            status_code=200,
            media_type="audio/mpeg",
            headers=response_headers
        )
    
    # Cache miss - generate new MP3
    logger.info(f"Cache miss - generating new MP3 for location: lat={user_lat}, lng={user_lng}")
    
    # Get nearby aircraft
    aircraft, error_message = await get_nearby_aircraft(user_lat, user_lng)
    
    # Generate descriptive text about the aircraft
    sentence = generate_flight_text(aircraft, error_message, user_lat, user_lng)
    
    # Debug mode: return text only without TTS
    if debug == 1:
        logger.info(f"Debug mode: returning HTML without TTS: {sentence[:50]}...")
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Dreaming of a Jet Plane - Debug Mode</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; background-color: #f5f5f5; }}
                .container {{ background-color: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
                h2 {{ color: #34495e; margin-top: 30px; }}
                table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
                th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
                th {{ background-color: #3498db; color: white; }}
                tr:nth-child(even) {{ background-color: #f9f9f9; }}
                .message {{ background-color: #e8f6f3; padding: 20px; border-left: 4px solid #1abc9c; margin: 20px 0; }}
                .error {{ background-color: #fadbd8; border-left-color: #e74c3c; }}
                .success {{ background-color: #d5f4e6; border-left-color: #27ae60; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🛩️ Dreaming of a Jet Plane - Debug Mode</h1>
                
                <div class="message {'success' if len(aircraft) > 0 else 'error'}">
                    <strong>Generated Message:</strong><br>
                    {sentence}
                </div>
                
                <h2>📍 Location Information</h2>
                <table>
                    <tr><th>Parameter</th><th>Value</th></tr>
                    <tr><td>Latitude</td><td>{user_lat}</td></tr>
                    <tr><td>Longitude</td><td>{user_lng}</td></tr>
                    <tr><td>Cache Key</td><td>{cache_key}</td></tr>
                </table>
                
                <h2>✈️ Flight Detection Results</h2>
                <table>
                    <tr><th>Parameter</th><th>Value</th></tr>
                    <tr><td>Aircraft Found</td><td>{'Yes' if len(aircraft) > 0 else 'No'}</td></tr>
                    <tr><td>Aircraft Count</td><td>{len(aircraft)}</td></tr>
        """
        
        if error_message:
            html_content += f"""
                    <tr><td>Error Message</td><td>{error_message}</td></tr>
            """
        
        html_content += """
                </table>
        """
        
        # Add aircraft details if found
        if aircraft and len(aircraft) > 0:
            closest_aircraft = aircraft[0]
            
            # Get aircraft coordinates for Google Maps link
            aircraft_lat = closest_aircraft.get('latitude')
            aircraft_lng = closest_aircraft.get('longitude')
            
            html_content += """
                <h2>🛫 Aircraft Details</h2>
                <table>
                    <tr><th>Property</th><th>Value</th></tr>
            """
            
            for key, value in closest_aircraft.items():
                if value is not None and value != "":
                    html_content += f"<tr><td>{key.replace('_', ' ').title()}</td><td>{value}</td></tr>"
            
            html_content += "</table>"
            
            # Add Google Maps directions link if we have aircraft coordinates
            if aircraft_lat and aircraft_lng:
                maps_url = f"https://www.google.com/maps/dir/?api=1&origin={user_lat},{user_lng}&destination={aircraft_lat},{aircraft_lng}&travelmode=driving"
                html_content += f"""
                <h2>🗺️ Google Maps</h2>
                <div class="message">
                    <a href="{maps_url}" target="_blank" style="color: #3498db; text-decoration: none; font-weight: bold;">
                        📍 View Directions from Your Location to Aircraft Position
                    </a>
                    <br><br>
                    <small style="color: #666;">
                        Your Location: {user_lat}, {user_lng}<br>
                        Aircraft Location: {aircraft_lat}, {aircraft_lng}
                    </small>
                </div>
                """
        
        html_content += """
            </div>
        </body>
        </html>
        """
        
        return HTMLResponse(content=html_content)
    
    if aircraft and len(aircraft) > 0:
        # Convert sentence to speech
        logger.info(f"Generating TTS for aircraft detection: {sentence[:50]}...")
        audio_content, tts_error = await convert_text_to_speech(sentence)
        
        if audio_content and not tts_error:
            logger.info(f"Successfully generated MP3 ({len(audio_content)} bytes) - caching in background")
            # Cache the newly generated MP3 (don't await - do in background)
            asyncio.create_task(s3_cache.set(cache_key, audio_content))
            
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
        # Convert sentence to speech (sentence already generated by generate_flight_text)
        logger.info(f"Generating TTS for no aircraft found: {sentence[:50]}...")
        audio_content, tts_error = await convert_text_to_speech(sentence)
        
        if audio_content and not tts_error:
            logger.info(f"Successfully generated error MP3 ({len(audio_content)} bytes) - caching in background")
            # Cache the error MP3 too (don't await - do in background)
            asyncio.create_task(s3_cache.set(cache_key, audio_content))
            
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

@app.get("/test-cache")
async def test_cache_endpoint():
    """Test S3 cache functionality without using ElevenLabs API"""
    # Create dummy MP3 data (just some bytes that could represent audio)
    dummy_mp3_data = b"fake_mp3_data_for_testing_" * 1000  # ~26KB of fake data
    
    # Generate a test cache key
    test_lat, test_lng = 51.5074, -0.1278  # London coordinates
    cache_key = s3_cache.generate_cache_key(test_lat, test_lng)
    
    logger.info(f"Testing cache upload with key: {cache_key}")
    
    # Try to upload to cache
    upload_success = await s3_cache.set(cache_key, dummy_mp3_data)
    
    # Try to retrieve from cache
    cached_data = await s3_cache.get(cache_key)
    
    return {
        "test_location": {"lat": test_lat, "lng": test_lng},
        "cache_key": cache_key,
        "upload_success": upload_success,
        "upload_data_size": len(dummy_mp3_data),
        "cache_hit": cached_data is not None,
        "cached_data_size": len(cached_data) if cached_data else 0,
        "s3_cache_enabled": s3_cache.enabled,
        "bucket_name": s3_cache.bucket_name,
        "aws_configured": bool(s3_cache.aws_access_key and s3_cache.aws_secret_key)
    }

@app.get("/plane/1")
async def plane_1_endpoint(request: Request, lat: float = None, lng: float = None, debug: int = 0):
    """Get MP3 for the closest aircraft"""
    return await handle_plane_endpoint(request, 1, lat, lng, debug)

@app.get("/plane/2")
async def plane_2_endpoint(request: Request, lat: float = None, lng: float = None, debug: int = 0):
    """Get MP3 for the second closest aircraft"""
    return await handle_plane_endpoint(request, 2, lat, lng, debug)

@app.get("/plane/3")
async def plane_3_endpoint(request: Request, lat: float = None, lng: float = None, debug: int = 0):
    """Get MP3 for the third closest aircraft"""
    return await handle_plane_endpoint(request, 3, lat, lng, debug)

@app.options("/plane/1")
async def plane_1_options():
    """Handle CORS preflight requests for /plane/1 endpoint"""
    return StreamingResponse(
        iter([b""]),
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
            "Access-Control-Allow-Headers": "Range, Content-Range, Content-Length",
            "Access-Control-Max-Age": "3600"
        }
    )

@app.options("/plane/2")
async def plane_2_options():
    """Handle CORS preflight requests for /plane/2 endpoint"""
    return StreamingResponse(
        iter([b""]),
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
            "Access-Control-Allow-Headers": "Range, Content-Range, Content-Length",
            "Access-Control-Max-Age": "3600"
        }
    )

@app.options("/plane/3")
async def plane_3_options():
    """Handle CORS preflight requests for /plane/3 endpoint"""
    return StreamingResponse(
        iter([b""]),
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
            "Access-Control-Allow-Headers": "Range, Content-Range, Content-Length",
            "Access-Control-Max-Age": "3600"
        }
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)