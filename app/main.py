from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
import httpx
import math
from typing import List, Dict, Any

app = FastAPI()

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

async def get_nearby_aircraft(lat: float, lng: float, radius_km: float = 100) -> List[Dict[str, Any]]:
    """Get aircraft near the given coordinates using OpenSky Network API"""
    try:
        # Create bounding box (approximate)
        lat_delta = radius_km / 111.0  # 1 degree lat ≈ 111 km
        lon_delta = radius_km / (111.0 * math.cos(math.radians(lat)))  # Adjust for longitude
        
        lamin = lat - lat_delta
        lamax = lat + lat_delta
        lomin = lng - lon_delta
        lomax = lng + lon_delta
        
        url = f"https://opensky-network.org/api/states/all?lamin={lamin}&lomin={lomin}&lamax={lamax}&lomax={lomax}"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=10.0)
            if response.status_code == 200:
                data = response.json()
                states = data.get("states", [])
                
                aircraft_list = []
                for state in states:
                    if len(state) >= 7 and state[6] is not None and state[5] is not None:
                        aircraft_lat = state[6]
                        aircraft_lon = state[5]
                        distance = calculate_distance(lat, lng, aircraft_lat, aircraft_lon)
                        
                        aircraft_info = {
                            "callsign": state[1].strip() if state[1] else "Unknown",
                            "country": state[2] if state[2] else "Unknown",
                            "latitude": aircraft_lat,
                            "longitude": aircraft_lon,
                            "altitude": state[7] if state[7] else 0,
                            "velocity": state[9] if state[9] else 0,
                            "heading": state[10] if state[10] else 0,
                            "distance_km": round(distance, 2)
                        }
                        aircraft_list.append(aircraft_info)
                
                # Sort by distance and return top 10
                aircraft_list.sort(key=lambda x: x["distance_km"])
                return aircraft_list[:10]
    
    except Exception:
        pass
    
    return []

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
async def read_root(request: Request):
    # Check for real IP in common proxy headers
    client_ip = (
        request.headers.get("x-forwarded-for", "").split(",")[0].strip() or
        request.headers.get("x-real-ip") or
        request.headers.get("cf-connecting-ip") or  # Cloudflare
        request.client.host
    )
    
    # Get latitude and longitude from IP
    lat, lng = await get_location_from_ip(client_ip)
    
    # Get nearby aircraft
    aircraft = await get_nearby_aircraft(lat, lng)
    
    return {
        "location": f"{client_ip}|{lat},{lng}",
        "nearby_aircraft": aircraft,
        "aircraft_count": len(aircraft)
    }

@app.get("/intro")
async def stream_intro():
    """Stream MP3 file from CDN"""
    # MP3 file hosted on S3
    mp3_url = "https://dreaming-of-a-jet-plane.s3.us-east-2.amazonaws.com/intro.mp3"
    
    try:
        async with httpx.AsyncClient() as client:
            async with client.stream("GET", mp3_url) as response:
                if response.status_code == 200:
                    content_length = response.headers.get("content-length")
                    content_type = response.headers.get("content-type", "audio/mpeg")
                    
                    async def stream_content():
                        async for chunk in response.aiter_bytes(chunk_size=8192):
                            yield chunk
                    
                    headers = {"Content-Type": content_type}
                    if content_length:
                        headers["Content-Length"] = content_length
                    
                    return StreamingResponse(
                        stream_content(),
                        media_type="audio/mpeg",
                        headers=headers
                    )
                else:
                    return {"error": "MP3 file not found or not accessible"}
    except Exception as e:
        return {"error": f"Failed to stream MP3: {str(e)}"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)