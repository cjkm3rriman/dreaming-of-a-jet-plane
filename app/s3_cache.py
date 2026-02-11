"""
S3-based MP3 caching system for flight audio data
"""

import hashlib
import logging
from datetime import datetime, timedelta, UTC
from typing import Optional, Union, Dict, Any
import httpx
import os
import hmac
import urllib.parse
import json
import asyncio
import random

logger = logging.getLogger(__name__)

class S3MP3Cache:
    # Timeouts for different operations (seconds)
    HEAD_TIMEOUT = 3.0      # Fast fail for cache existence checks
    GET_TIMEOUT = 30.0      # Longer timeout for downloading audio
    PUT_TIMEOUT = 60.0      # Longest timeout for uploads

    def __init__(self,
                 bucket_name: str = "dreaming-of-a-jet-plane",
                 cache_prefix: str = "cache/",
                 ttl_minutes: int = 3,
                 api_ttl_minutes: int = 3):
        self.bucket_name = bucket_name
        self.cache_prefix = cache_prefix
        self.ttl_minutes = ttl_minutes
        self.api_ttl_minutes = api_ttl_minutes

        # AWS credentials from environment
        self.aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
        self.aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        self.aws_region = os.getenv("AWS_REGION", "us-east-2")

        # Shared HTTP client for connection pooling (lazy initialized)
        self._client: Optional[httpx.AsyncClient] = None

        if not self.aws_access_key or not self.aws_secret_key:
            logger.warning("AWS credentials not configured - S3 cache disabled")
            self.enabled = False
        else:
            self.enabled = True
            logger.info(f"S3 cache initialized: bucket={bucket_name}, prefix={cache_prefix}")

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create shared HTTP client for connection pooling"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                # Connection pool settings
                limits=httpx.Limits(
                    max_keepalive_connections=5,
                    max_connections=10,
                    keepalive_expiry=30.0
                ),
                # Default timeout (overridden per-request)
                timeout=httpx.Timeout(self.GET_TIMEOUT)
            )
        return self._client

    async def close(self):
        """Close the shared HTTP client"""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def generate_cache_key(self, lat: float, lng: float, content_type: str = "audio", plane_index: Optional[int] = None, tts_provider: Optional[str] = None, audio_format: Optional[str] = None, namespace: Optional[str] = None) -> str:
        """Generate cache key based on rounded location coordinates

        Args:
            lat: Latitude
            lng: Longitude
            content_type: Type of content ("audio", "json")
            plane_index: Optional plane index for multiple aircraft (1-5)
            tts_provider: Optional TTS provider name for audio caching (different providers = different cache)
            audio_format: Optional audio format extension ("mp3", "ogg")
            namespace: Optional namespace to differentiate caches (e.g., provider name)
        """
        # Round to 2 decimal places (~1km precision) to increase cache hits
        rounded_lat = round(lat, 2)
        rounded_lng = round(lng, 2)

        # Create hash of location
        location_str = f"{rounded_lat},{rounded_lng}"
        if namespace:
            location_str = f"{location_str}:{namespace}"
        cache_key = hashlib.md5(location_str.encode()).hexdigest()

        # Build filename based on content type, plane index, and TTS provider
        if content_type == "json":
            filename = f"{cache_key}_aircraft.json"
        elif plane_index is not None:
            # Determine file extension from explicit format or provider mapping
            if audio_format:
                ext = audio_format
            elif tts_provider:
                # Map provider to format
                format_map = {"google": "mp3", "elevenlabs": "mp3"}  # TODO: Switch Google back to OGG later
                ext = format_map.get(tts_provider.lower(), "mp3")
            else:
                ext = "mp3"

            # Include TTS provider in filename for audio files
            provider_suffix = f"_{tts_provider}" if tts_provider else ""
            filename = f"{cache_key}_plane{plane_index}{provider_suffix}.{ext}"
        else:
            filename = f"{cache_key}.mp3"  # Legacy format

        full_key = f"{self.cache_prefix}{filename}"
        return full_key

    async def _retry_with_backoff(self, operation, max_retries: int = 3):
        """Retry an async operation with exponential backoff for S3 rate limiting

        Args:
            operation: Async callable to retry
            max_retries: Maximum number of retry attempts

        Returns:
            Result from operation if successful

        Raises:
            Exception from last retry attempt if all retries fail
        """
        for attempt in range(max_retries):
            try:
                return await operation()
            except httpx.HTTPStatusError as e:
                # Check if it's a rate limiting error (503 SlowDown)
                if e.response.status_code == 503:
                    if attempt < max_retries - 1:
                        # Exponential backoff with jitter: 2^attempt * 100ms + random(0-100ms)
                        backoff = (2 ** attempt) * 0.1 + random.uniform(0, 0.1)
                        logger.warning(f"S3 rate limit hit, retrying in {backoff:.2f}s (attempt {attempt + 1}/{max_retries})")
                        await asyncio.sleep(backoff)
                        continue
                    else:
                        logger.error(f"S3 rate limit exceeded after {max_retries} retries")
                        raise
                else:
                    # Not a rate limit error, don't retry
                    raise
            except Exception as e:
                # For other exceptions, don't retry
                raise

    def _create_aws_signature(self, method: str, url: str, headers: dict, payload: bytes) -> dict:
        """Create AWS Signature Version 4 headers for S3 request"""
        from urllib.parse import urlparse
        import datetime

        parsed_url = urlparse(url)
        host = parsed_url.netloc
        path = parsed_url.path

        # Create timestamp
        t = datetime.datetime.now(datetime.UTC)
        amzdate = t.strftime('%Y%m%dT%H%M%SZ')
        datestamp = t.strftime('%Y%m%d')
        
        # Create canonical request with all headers that will be sent
        canonical_uri = path
        canonical_querystring = ''
        payload_hash = hashlib.sha256(payload).hexdigest()
        
        # Build canonical headers - include all headers that will be sent
        canonical_headers_dict = {
            'host': host,
            'x-amz-content-sha256': payload_hash,
            'x-amz-date': amzdate,
        }
        
        # Add any x-amz-meta headers from the original headers
        for key, value in headers.items():
            if key.lower().startswith('x-amz-meta-'):
                canonical_headers_dict[key.lower()] = str(value)
        
        # Sort headers and build canonical string
        sorted_headers = sorted(canonical_headers_dict.items())
        canonical_headers = ''.join([f'{k}:{v}\n' for k, v in sorted_headers])
        signed_headers = ';'.join([k for k, v in sorted_headers])
        
        canonical_request = f'{method}\n{canonical_uri}\n{canonical_querystring}\n{canonical_headers}\n{signed_headers}\n{payload_hash}'
        
        # Create string to sign
        algorithm = 'AWS4-HMAC-SHA256'
        credential_scope = f'{datestamp}/{self.aws_region}/s3/aws4_request'
        string_to_sign = f'{algorithm}\n{amzdate}\n{credential_scope}\n{hashlib.sha256(canonical_request.encode()).hexdigest()}'
        
        # Create signing key
        def sign(key, msg):
            return hmac.new(key, msg.encode('utf-8'), hashlib.sha256).digest()
        
        def getSignatureKey(key, dateStamp, regionName, serviceName):
            kDate = sign(('AWS4' + key).encode('utf-8'), dateStamp)
            kRegion = sign(kDate, regionName)
            kService = sign(kRegion, serviceName)
            kSigning = sign(kService, "aws4_request")
            return kSigning
        
        signing_key = getSignatureKey(self.aws_secret_key, datestamp, self.aws_region, 's3')
        signature = hmac.new(signing_key, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()
        
        # Create authorization header
        authorization_header = f'{algorithm} Credential={self.aws_access_key}/{credential_scope}, SignedHeaders={signed_headers}, Signature={signature}'
        
        # Return headers to add to request
        return {
            'x-amz-date': amzdate,
            'x-amz-content-sha256': payload_hash,
            'Authorization': authorization_header
        }
    
    async def get(self, cache_key: str, content_type: str = "audio") -> Optional[Union[bytes, Dict[str, Any]]]:
        """Get data from S3 cache if not expired

        Args:
            cache_key: Cache key to retrieve
            content_type: Type of content ("audio", "json") - determines TTL and return type

        Returns:
            bytes for audio content, dict for JSON content, None if not found/expired
        """
        if not self.enabled:
            return None
            
        try:
            s3_url = f"https://{self.bucket_name}.s3.{self.aws_region}.amazonaws.com/{cache_key}"
            client = await self._get_client()

            # First, check if object exists and get metadata (fast timeout)
            head_response = await client.head(s3_url, timeout=self.HEAD_TIMEOUT)

            if head_response.status_code == 404:
                logger.info(f"Cache miss: {cache_key} not found")
                return None
            elif head_response.status_code != 200:
                logger.warning(f"S3 HEAD request failed: {head_response.status_code}")
                return None

            # Check if cached file is still valid - use appropriate TTL
            ttl_minutes = self.api_ttl_minutes if content_type == "json" else self.ttl_minutes
            last_modified_str = head_response.headers.get("last-modified")
            if last_modified_str:
                try:
                    # Parse S3 date format: 'Wed, 21 Oct 2015 07:28:00 GMT'
                    from email.utils import parsedate_to_datetime
                    last_modified = parsedate_to_datetime(last_modified_str)
                    now = datetime.now(last_modified.tzinfo)

                    if now - last_modified > timedelta(minutes=ttl_minutes):
                        return None
                except Exception as e:
                    logger.warning(f"Error parsing last-modified date: {e}")
                    return None

            # File exists and is fresh, download it (longer timeout for actual data)
            get_response = await client.get(s3_url, timeout=self.GET_TIMEOUT)

            if get_response.status_code == 200:

                # Return appropriate data type
                if content_type == "json":
                    try:
                        return json.loads(get_response.content.decode('utf-8'))
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse cached JSON: {e}")
                        return None
                else:
                    return get_response.content
            else:
                logger.warning(f"S3 GET request failed: {get_response.status_code}")
                return None
                    
        except httpx.TimeoutException:
            logger.error(f"S3 cache timeout for key: {cache_key}")
            return None
        except Exception as e:
            logger.error(f"S3 cache get error for key {cache_key}: {e}")
            return None
    
    async def set(self, cache_key: str, data: Union[bytes, Dict[str, Any]], content_type: str = "audio") -> bool:
        """Store data in S3 cache

        Args:
            cache_key: Cache key
            data: Data to store (bytes for audio, dict for JSON)
            content_type: Type of content ("audio", "json")
        """
        if not self.enabled:
            logger.warning("S3 cache disabled - cannot store data")
            return False
            
        try:
            s3_url = f"https://{self.bucket_name}.s3.{self.aws_region}.amazonaws.com/{cache_key}"
            
            # Convert data to bytes and set appropriate headers
            if content_type == "json":
                if isinstance(data, dict):
                    data_bytes = json.dumps(data).encode('utf-8')
                    content_type_header = "application/json"
                    ttl_minutes = self.api_ttl_minutes
                else:
                    raise ValueError("Data must be dict for JSON content_type")
            else:  # "audio"
                if isinstance(data, bytes):
                    data_bytes = data
                    # Determine MIME type from cache key extension
                    if cache_key.endswith('.ogg'):
                        content_type_header = "audio/ogg"
                    else:
                        content_type_header = "audio/mpeg"
                    ttl_minutes = self.ttl_minutes
                else:
                    raise ValueError("Data must be bytes for audio content_type")
            
            headers = {
                "Content-Type": content_type_header,
                "Content-Length": str(len(data_bytes)),
                # Add metadata for TTL tracking
                "x-amz-meta-cached-at": datetime.now(UTC).isoformat(),
                "x-amz-meta-ttl-minutes": str(ttl_minutes),
                "x-amz-meta-content-type": content_type
            }
            
            logger.info(f"Uploading to S3 cache: {cache_key} ({len(data_bytes)} bytes, type={content_type})")

            # Add AWS signature headers
            aws_headers = self._create_aws_signature('PUT', s3_url, headers, data_bytes)
            headers.update(aws_headers)

            # Perform actual S3 upload with retry logic for rate limiting
            async def upload_operation():
                client = await self._get_client()
                response = await client.put(s3_url, content=data_bytes, headers=headers, timeout=self.PUT_TIMEOUT)
                response.raise_for_status()  # Raises HTTPStatusError for 4xx/5xx
                return response

            response = await self._retry_with_backoff(upload_operation)

            if response.status_code == 200:
                logger.info(f"Successfully uploaded to S3: {cache_key} ({len(data_bytes)} bytes, type={content_type})")
                return True
            else:
                logger.error(f"S3 upload failed: {response.status_code} - {response.text[:200]}")
                return False
            
        except Exception as e:
            logger.error(f"S3 cache set error for key {cache_key}: {e}")
            return False
    
    async def get_raw(self, cache_key: str) -> Optional[bytes]:
        """Get raw bytes from S3 without TTL check (for free pool audio)

        Free pool audio should be served regardless of age since it's
        explicitly managed by the free pool index (FIFO, max 100 entries).

        Args:
            cache_key: S3 key to retrieve (can be full path like 'free_pool/xyz.mp3')

        Returns:
            bytes if found, None if not found or error
        """
        if not self.enabled:
            return None

        try:
            s3_url = f"https://{self.bucket_name}.s3.{self.aws_region}.amazonaws.com/{cache_key}"
            client = await self._get_client()
            response = await client.get(s3_url, timeout=self.GET_TIMEOUT)

            if response.status_code == 200:
                return response.content
            elif response.status_code == 404:
                logger.info(f"Free pool audio not found: {cache_key}")
                return None
            else:
                logger.warning(f"S3 GET request failed for free pool: {response.status_code}")
                return None

        except httpx.TimeoutException:
            logger.error(f"S3 timeout fetching free pool audio: {cache_key}")
            return None
        except Exception as e:
            logger.error(f"S3 error fetching free pool audio {cache_key}: {e}")
            return None

    async def exists_and_fresh(self, cache_key: str, content_type: str = "audio") -> bool:
        """Check if cached file exists and is still fresh"""
        if not self.enabled:
            return False

        try:
            s3_url = f"https://{self.bucket_name}.s3.{self.aws_region}.amazonaws.com/{cache_key}"
            client = await self._get_client()
            head_response = await client.head(s3_url, timeout=self.HEAD_TIMEOUT)

            if head_response.status_code != 200:
                return False

            # Check freshness - use appropriate TTL
            ttl_minutes = self.api_ttl_minutes if content_type == "json" else self.ttl_minutes
            last_modified_str = head_response.headers.get("last-modified")
            if last_modified_str:
                try:
                    from email.utils import parsedate_to_datetime
                    last_modified = parsedate_to_datetime(last_modified_str)
                    now = datetime.now(last_modified.tzinfo)

                    is_fresh = now - last_modified <= timedelta(minutes=ttl_minutes)
                    logger.info(f"Cache freshness check: {cache_key} = {is_fresh} (TTL: {ttl_minutes}min)")
                    return is_fresh
                except Exception as e:
                    logger.warning(f"Error checking cache freshness: {e}")
                    return False

            return True

        except httpx.TimeoutException:
            logger.warning(f"S3 cache freshness check timeout for key: {cache_key}")
            return False
        except Exception as e:
            logger.error(f"S3 cache exists check error for key {cache_key}: {e}")
            return False


# Global cache instance
s3_cache = S3MP3Cache()
