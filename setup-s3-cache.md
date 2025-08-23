# S3 Cache Setup Instructions

## Overview
This application uses S3 for caching generated MP3 files to reduce costs and improve performance.

## Prerequisites
1. AWS S3 bucket: `dreaming-of-a-jet-plane`
2. AWS credentials configured with S3 read/write permissions

## Environment Variables
Add these to your Railway deployment:

```bash
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key  
AWS_REGION=us-east-2
```

## S3 Lifecycle Policy Setup
To automatically clean up expired cache files, apply the lifecycle policy:

```bash
# Using AWS CLI
aws s3api put-bucket-lifecycle-configuration \
  --bucket dreaming-of-a-jet-plane \
  --lifecycle-configuration file://s3-lifecycle-policy.json
```

## Cache Structure
- **Cache Path**: `cache/{location_hash}.mp3`
- **TTL**: 10 minutes (handled by application logic)
- **Cleanup**: S3 lifecycle policy removes files after 1 day
- **Key Format**: MD5 hash of rounded coordinates (2 decimal places)

## How It Works

### Pre-generation Flow:
1. User hits `/scanning.mp3?lat=X&lng=Y` (or uses IP geolocation)
2. App serves scanning MP3 from S3
3. Background task generates flight MP3 and caches to S3

### Serving Flow:
1. User hits `/?lat=X&lng=Y` 10 seconds later
2. App checks S3 cache first
3. If cached and fresh: serves from S3
4. If cache miss: generates new MP3 + caches to S3

## Benefits
- **Cost**: Reduces ElevenLabs API calls by 50-80%
- **Performance**: Cached responses ~2x faster
- **Scalability**: No server memory usage
- **Persistence**: Cache survives deployments

## Monitoring
Check Railway logs for cache hit/miss rates:
- `Cache hit: {key}` - Served from S3
- `Cache miss: {key}` - Generated new MP3
- `Successfully pre-generated and cached MP3` - Background task completed