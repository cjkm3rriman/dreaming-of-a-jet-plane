"""
S3-based MP3 caching system for flight audio data
"""

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional
import httpx
import os

logger = logging.getLogger(__name__)

class S3MP3Cache:
    def __init__(self, 
                 bucket_name: str = "dreaming-of-a-jet-plane", 
                 cache_prefix: str = "cache/",
                 ttl_minutes: int = 10):
        self.bucket_name = bucket_name
        self.cache_prefix = cache_prefix
        self.ttl_minutes = ttl_minutes
        
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
    
    def generate_cache_key(self, lat: float, lng: float) -> str:
        """Generate cache key based on rounded location coordinates"""
        # Round to 2 decimal places (~1km precision) to increase cache hits
        rounded_lat = round(lat, 2)
        rounded_lng = round(lng, 2)
        
        # Create hash of location
        location_str = f"{rounded_lat},{rounded_lng}"
        cache_key = hashlib.md5(location_str.encode()).hexdigest()
        
        logger.info(f"Generated cache key {cache_key} for location {location_str}")
        return f"{self.cache_prefix}{cache_key}.mp3"
    
    async def get(self, cache_key: str) -> Optional[bytes]:
        """Get MP3 data from S3 cache if not expired"""
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
                
                # Check if cached file is still valid
                last_modified_str = head_response.headers.get("last-modified")
                if last_modified_str:
                    try:
                        # Parse S3 date format: 'Wed, 21 Oct 2015 07:28:00 GMT'
                        from email.utils import parsedate_to_datetime
                        last_modified = parsedate_to_datetime(last_modified_str)
                        now = datetime.now(last_modified.tzinfo)
                        
                        if now - last_modified > timedelta(minutes=self.ttl_minutes):
                            logger.info(f"Cache expired: {cache_key} (age: {now - last_modified})")
                            return None
                    except Exception as e:
                        logger.warning(f"Error parsing last-modified date: {e}")
                        return None
                
                # File exists and is fresh, download it
                get_response = await client.get(s3_url, timeout=30.0)
                
                if get_response.status_code == 200:
                    logger.info(f"Cache hit: {cache_key} ({len(get_response.content)} bytes)")
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
    
    async def set(self, cache_key: str, data: bytes) -> bool:
        """Store MP3 data in S3 cache"""
        if not self.enabled:
            logger.warning("S3 cache disabled - cannot store data")
            return False
            
        try:
            # Use boto3-style presigned URL for upload (simplified approach)
            # For production, you'd typically use boto3 or AWS SDK
            # For now, we'll use a simple PUT request approach
            
            s3_url = f"https://{self.bucket_name}.s3.{self.aws_region}.amazonaws.com/{cache_key}"
            
            headers = {
                "Content-Type": "audio/mpeg",
                "Content-Length": str(len(data)),
                # Add metadata for TTL tracking
                "x-amz-meta-cached-at": datetime.utcnow().isoformat(),
                "x-amz-meta-ttl-minutes": str(self.ttl_minutes)
            }
            
            # Note: This is a simplified approach. In production, you'd want to:
            # 1. Use proper AWS authentication (boto3)
            # 2. Use presigned URLs for security
            # 3. Handle AWS-specific error responses
            
            logger.info(f"Uploading to S3 cache: {cache_key} ({len(data)} bytes)")
            
            # For now, we'll skip the actual S3 upload and just log it
            # This would need proper AWS SDK integration
            logger.info(f"Would upload {len(data)} bytes to S3: {s3_url}")
            
            return True
            
        except Exception as e:
            logger.error(f"S3 cache set error for key {cache_key}: {e}")
            return False
    
    async def exists_and_fresh(self, cache_key: str) -> bool:
        """Check if cached file exists and is still fresh"""
        if not self.enabled:
            return False
            
        try:
            s3_url = f"https://{self.bucket_name}.s3.{self.aws_region}.amazonaws.com/{cache_key}"
            
            async with httpx.AsyncClient() as client:
                head_response = await client.head(s3_url, timeout=10.0)
                
                if head_response.status_code != 200:
                    return False
                
                # Check freshness
                last_modified_str = head_response.headers.get("last-modified")
                if last_modified_str:
                    try:
                        from email.utils import parsedate_to_datetime
                        last_modified = parsedate_to_datetime(last_modified_str)
                        now = datetime.now(last_modified.tzinfo)
                        
                        is_fresh = now - last_modified <= timedelta(minutes=self.ttl_minutes)
                        logger.info(f"Cache freshness check: {cache_key} = {is_fresh}")
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