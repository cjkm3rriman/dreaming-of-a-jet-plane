"""
Intro endpoint for streaming MP3 file from S3
"""

from fastapi import Request
from fastapi.responses import StreamingResponse
import httpx


async def stream_intro(request: Request):
    """Stream MP3 file from S3 with headers that mimic direct S3 access"""
    # MP3 file hosted on S3
    mp3_url = "https://dreaming-of-a-jet-plane.s3.us-east-2.amazonaws.com/intro.mp3"
    
    try:
        # Prepare headers for the S3 request - copy all client headers
        headers = {}
        
        # Handle Range requests for seeking/partial content
        range_header = request.headers.get("range")
        if range_header:
            headers["Range"] = range_header
            
        # Copy other relevant headers
        if request.headers.get("if-none-match"):
            headers["If-None-Match"] = request.headers["if-none-match"]
        if request.headers.get("if-modified-since"):
            headers["If-Modified-Since"] = request.headers["if-modified-since"]
        
        async with httpx.AsyncClient() as client:
            async with client.stream("GET", mp3_url, headers=headers) as response:
                if response.status_code in [200, 206, 304]:  # Include 304 Not Modified
                    
                    async def stream_content():
                        async for chunk in response.aiter_bytes(chunk_size=8192):
                            yield chunk
                    
                    # Copy all S3 response headers to mimic direct access
                    response_headers = {}
                    
                    # Essential headers for MP3 streaming
                    response_headers["Content-Type"] = response.headers.get("content-type", "audio/mpeg")
                    response_headers["Accept-Ranges"] = response.headers.get("accept-ranges", "bytes")
                    
                    # Copy S3-specific headers
                    s3_headers_to_copy = [
                        "content-length", "last-modified", "etag", "cache-control",
                        "expires", "content-range", "content-encoding", "x-amz-request-id"
                    ]
                    
                    for header in s3_headers_to_copy:
                        if response.headers.get(header):
                            response_headers[header.title()] = response.headers[header]
                    
                    # Add CORS headers for browser compatibility
                    response_headers.update({
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
                        "Access-Control-Allow-Headers": "Range, Content-Range, Content-Length, If-None-Match, If-Modified-Since",
                        "Access-Control-Expose-Headers": "Content-Length, Content-Range, Accept-Ranges, Last-Modified, ETag"
                    })
                    
                    # Use the same status code as S3
                    status_code = response.status_code
                    
                    return StreamingResponse(
                        stream_content(),
                        status_code=status_code,
                        media_type="audio/mpeg",
                        headers=response_headers
                    )
                else:
                    return {"error": f"MP3 file not accessible. Status: {response.status_code}"}
    except Exception as e:
        return {"error": f"Failed to stream MP3: {str(e)}"}


async def intro_options():
    """Handle CORS preflight requests for /intro endpoint"""
    return StreamingResponse(
        iter([b""]),
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
            "Access-Control-Allow-Headers": "Range, Content-Range, Content-Length",
            "Access-Control-Max-Age": "3600"
        }
    )