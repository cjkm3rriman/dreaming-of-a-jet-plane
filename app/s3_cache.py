"""
S3-based MP3 caching system for flight audio data
"""

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional, Union, Dict, Any
import httpx
import os
import hmac
import urllib.parse
import json

logger = logging.getLogger(__name__)

class S3MP3Cache:
    def __init__(self, 
                 bucket_name: str = "dreaming-of-a-jet-plane", 
                 cache_prefix: str = "cache/",
                 ttl_minutes: int = 10,
                 api_ttl_minutes: int = 5):
        self.bucket_name = bucket_name
        self.cache_prefix = cache_prefix
        self.ttl_minutes = ttl_minutes
        self.api_ttl_minutes = api_ttl_minutes
        
        # AWS credentials from environment
        self.aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
        self.aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        self.aws_region = os.getenv("AWS_REGION", "us-east-2")
        
        if not self.aws_access_key or not self.aws_secret_key:
            logger.warning("AWS credentials not configured - S3 cache disabled")
            self.enabled = False
        else:
            self.enabled = True
            logger.info(f"S3 cache initialized: bucket={bucket_name}, prefix={cache_prefix}")
    
    def generate_cache_key(self, lat: float, lng: float, content_type: str = "mp3", plane_index: Optional[int] = None) -> str:
        """Generate cache key based on rounded location coordinates
        
        Args:
            lat: Latitude
            lng: Longitude  
            content_type: Type of content ("mp3", "json")
            plane_index: Optional plane index for multiple aircraft (1, 2, 3)
        """
        # Round to 2 decimal places (~1km precision) to increase cache hits
        rounded_lat = round(lat, 2)
        rounded_lng = round(lng, 2)
        
        # Create hash of location
        location_str = f"{rounded_lat},{rounded_lng}"
        cache_key = hashlib.md5(location_str.encode()).hexdigest()
        
        # Build filename based on content type and plane index
        if content_type == "json":
            filename = f"{cache_key}_aircraft.json"
        elif plane_index is not None:
            filename = f"{cache_key}_plane{plane_index}.mp3"
        else:
            filename = f"{cache_key}.mp3"
        
        full_key = f"{self.cache_prefix}{filename}"
        logger.info(f"Generated cache key {full_key} for location {location_str}, content_type={content_type}, plane_index={plane_index}")
        return full_key
    
    def _create_aws_signature(self, method: str, url: str, headers: dict, payload: bytes) -> dict:
        """Create AWS Signature Version 4 headers for S3 request"""
        from urllib.parse import urlparse
        import datetime
        
        parsed_url = urlparse(url)
        host = parsed_url.netloc
        path = parsed_url.path
        
        # Create timestamp
        t = datetime.datetime.utcnow()
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
    
    async def get(self, cache_key: str, content_type: str = "mp3") -> Optional[Union[bytes, Dict[str, Any]]]:
        """Get data from S3 cache if not expired
        
        Args:
            cache_key: Cache key to retrieve
            content_type: Type of content ("mp3", "json") - determines TTL and return type
        
        Returns:
            bytes for MP3 content, dict for JSON content, None if not found/expired
        """
        if not self.enabled:
            return None
            
        try:
            s3_url = f"https://{self.bucket_name}.s3.{self.aws_region}.amazonaws.com/{cache_key}"
            
            # First, check if object exists and get metadata
            async with httpx.AsyncClient() as client:
                head_response = await client.head(s3_url, timeout=10.0)
                
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
                            logger.info(f"Cache expired: {cache_key} (age: {now - last_modified}, TTL: {ttl_minutes}min)")
                            return None
                    except Exception as e:
                        logger.warning(f"Error parsing last-modified date: {e}")
                        return None
                
                # File exists and is fresh, download it
                get_response = await client.get(s3_url, timeout=30.0)
                
                if get_response.status_code == 200:
                    logger.info(f"Cache hit: {cache_key} ({len(get_response.content)} bytes)")
                    
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
    
    async def set(self, cache_key: str, data: Union[bytes, Dict[str, Any]], content_type: str = "mp3") -> bool:
        """Store data in S3 cache
        
        Args:
            cache_key: Cache key
            data: Data to store (bytes for MP3, dict for JSON)
            content_type: Type of content ("mp3", "json")
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
            else:
                if isinstance(data, bytes):
                    data_bytes = data
                    content_type_header = "audio/mpeg"
                    ttl_minutes = self.ttl_minutes
                else:
                    raise ValueError("Data must be bytes for MP3 content_type")
            
            headers = {
                "Content-Type": content_type_header,
                "Content-Length": str(len(data_bytes)),
                # Add metadata for TTL tracking
                "x-amz-meta-cached-at": datetime.utcnow().isoformat(),
                "x-amz-meta-ttl-minutes": str(ttl_minutes),
                "x-amz-meta-content-type": content_type
            }
            
            logger.info(f"Uploading to S3 cache: {cache_key} ({len(data_bytes)} bytes, type={content_type})")
            
            # Add AWS signature headers
            aws_headers = self._create_aws_signature('PUT', s3_url, headers, data_bytes)
            headers.update(aws_headers)
            
            # Perform actual S3 upload
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.put(s3_url, content=data_bytes, headers=headers)
                
                if response.status_code == 200:
                    logger.info(f"Successfully uploaded to S3: {cache_key} ({len(data_bytes)} bytes, type={content_type})")
                    return True
                else:
                    logger.error(f"S3 upload failed: {response.status_code} - {response.text[:200]}")
                    return False
            
        except Exception as e:
            logger.error(f"S3 cache set error for key {cache_key}: {e}")
            return False
    
    async def exists_and_fresh(self, cache_key: str, content_type: str = "mp3") -> bool:
        """Check if cached file exists and is still fresh"""
        if not self.enabled:
            return False
            
        try:
            s3_url = f"https://{self.bucket_name}.s3.{self.aws_region}.amazonaws.com/{cache_key}"
            
            async with httpx.AsyncClient() as client:
                head_response = await client.head(s3_url, timeout=10.0)
                
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
                
        except Exception as e:
            logger.error(f"S3 cache exists check error for key {cache_key}: {e}")
            return False


# Global cache instance
s3_cache = S3MP3Cache()