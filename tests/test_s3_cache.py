"""Unit tests for the hand-rolled S3 client (DOJP-47 item 5)

This is the transport layer the full-flow tests deliberately fake: SigV4
signing, the HEAD+Last-Modified TTL check, and 503 retry with backoff. A
signing bug turns into wall-to-wall 403s (cache dead, every request paying
full TTS latency); a TTL parsing bug replays stale flights - so this layer
gets real tests even though production is its ultimate oracle.

No real AWS is ever touched: instances are built with fake credentials and
every HTTP call is intercepted by respx (which raises on unmocked requests).
"""

import asyncio
import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import httpx
import pytest
import respx

import app.s3_cache as s3_cache_module
from app.s3_cache import S3MP3Cache

BUCKET = "dreaming-of-a-jet-plane"
REGION = "us-east-2"
HOST = f"{BUCKET}.s3.{REGION}.amazonaws.com"
KEY = "cache/test_object.opus"
URL = f"https://{HOST}/{KEY}"


@pytest.fixture
def creds(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIATESTFAKEKEY00000")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testsecret/testsecret/testsecret0000000")
    monkeypatch.setenv("AWS_REGION", REGION)


@pytest.fixture
async def cache(creds):
    instance = S3MP3Cache()
    assert instance.enabled
    yield instance
    await instance.close()


def _last_modified(age_seconds):
    return format_datetime(datetime.now(timezone.utc) - timedelta(seconds=age_seconds), usegmt=True)


# ---------------------------------------------------------------------------
# SigV4 signing
# ---------------------------------------------------------------------------


def _reference_signature(access_key, secret_key, region, method, url, headers, payload, amzdate):
    """Independent SigV4 reference, written directly from the AWS spec steps
    (canonical request -> string to sign -> derived key -> signature). Takes
    the amzdate the production code chose, so no clock freezing is needed.
    """
    from urllib.parse import urlparse
    parsed = urlparse(url)
    payload_hash = hashlib.sha256(payload).hexdigest()

    canonical = {"host": parsed.netloc, "x-amz-content-sha256": payload_hash, "x-amz-date": amzdate}
    for k, v in headers.items():
        if k.lower().startswith("x-amz-meta-"):
            canonical[k.lower()] = str(v)
    items = sorted(canonical.items())
    canonical_headers = "".join(f"{k}:{v}\n" for k, v in items)
    signed_headers = ";".join(k for k, _ in items)
    canonical_request = (
        f"{method}\n{parsed.path}\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}"
    )

    datestamp = amzdate[:8]
    scope = f"{datestamp}/{region}/s3/aws4_request"
    string_to_sign = (
        f"AWS4-HMAC-SHA256\n{amzdate}\n{scope}\n"
        f"{hashlib.sha256(canonical_request.encode()).hexdigest()}"
    )

    def _hmac(key, msg):
        return hmac.new(key, msg.encode(), hashlib.sha256).digest()

    k = _hmac(("AWS4" + secret_key).encode(), datestamp)
    k = _hmac(k, region)
    k = _hmac(k, "s3")
    k = _hmac(k, "aws4_request")
    signature = hmac.new(k, string_to_sign.encode(), hashlib.sha256).hexdigest()
    return (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )


@pytest.mark.unit
def test_signature_matches_an_independent_spec_implementation(creds):
    """The production signer and a from-the-spec reference must agree byte
    for byte, including x-amz-meta header canonicalization"""
    cache = S3MP3Cache()
    headers = {
        "Content-Type": "audio/opus",
        "x-amz-meta-ttl-minutes": "3",
        "x-amz-meta-cached-at": "2026-09-13T00:00:00+00:00",
    }
    payload = b"opus bytes"

    signed = cache._create_aws_signature("PUT", URL, headers, payload)
    expected = _reference_signature(
        cache.aws_access_key, cache.aws_secret_key, REGION,
        "PUT", URL, headers, payload, signed["x-amz-date"],
    )

    assert signed["Authorization"] == expected
    assert signed["x-amz-content-sha256"] == hashlib.sha256(payload).hexdigest()


@pytest.mark.unit
def test_meta_headers_are_signed_but_content_type_is_not(creds):
    """S3 verifies exactly the SignedHeaders list - including a header S3
    will receive but we didn't sign is legal, signing one we mangle is not"""
    cache = S3MP3Cache()
    signed = cache._create_aws_signature(
        "PUT", URL, {"Content-Type": "audio/opus", "x-amz-meta-ttl-minutes": "3"}, b"x"
    )
    auth = signed["Authorization"]
    signed_headers = auth.split("SignedHeaders=")[1].split(",")[0]
    assert signed_headers == "host;x-amz-content-sha256;x-amz-date;x-amz-meta-ttl-minutes"


@pytest.mark.unit
@pytest.mark.parametrize("change", ["method", "path", "payload", "meta"])
def test_signature_is_sensitive_to_every_signed_input(creds, change):
    cache = S3MP3Cache()
    base_args = dict(method="PUT", url=URL, headers={"x-amz-meta-ttl-minutes": "3"}, payload=b"x")
    varied = dict(base_args)
    if change == "method":
        varied["method"] = "GET"
    elif change == "path":
        varied["url"] = URL + "2"
    elif change == "payload":
        varied["payload"] = b"y"
    elif change == "meta":
        varied["headers"] = {"x-amz-meta-ttl-minutes": "10"}

    sig_a = cache._create_aws_signature(base_args["method"], base_args["url"], base_args["headers"], base_args["payload"])
    sig_b = cache._create_aws_signature(varied["method"], varied["url"], varied["headers"], varied["payload"])
    assert sig_a["Authorization"].split("Signature=")[1] != sig_b["Authorization"].split("Signature=")[1]


# ---------------------------------------------------------------------------
# get(): TTL enforcement on Last-Modified
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_fresh_object_is_served(cache):
    with respx.mock as router:
        router.head(URL).mock(return_value=httpx.Response(
            200, headers={"Last-Modified": _last_modified(cache.ttl_minutes * 60 - 20)}))
        get_route = router.get(URL).mock(return_value=httpx.Response(200, content=b"audio"))

        assert await cache.get(KEY) == b"audio"
        assert get_route.call_count == 1


@pytest.mark.unit
async def test_expired_object_is_a_miss_and_is_never_downloaded(cache):
    """Past the TTL: report a miss AND don't waste the GET bandwidth"""
    with respx.mock as router:
        router.head(URL).mock(return_value=httpx.Response(
            200, headers={"Last-Modified": _last_modified(cache.ttl_minutes * 60 + 20)}))
        get_route = router.get(URL).mock(return_value=httpx.Response(200, content=b"audio"))

        assert await cache.get(KEY) is None
        assert get_route.call_count == 0


@pytest.mark.unit
async def test_content_type_selects_the_matching_ttl(creds):
    """audio uses ttl_minutes, json uses api_ttl_minutes - an object older
    than one but younger than the other must behave differently by type"""
    instance = S3MP3Cache(ttl_minutes=2, api_ttl_minutes=10)
    age_between = 5 * 60  # older than 2min audio TTL, younger than 10min json TTL
    try:
        with respx.mock as router:
            router.head(URL).mock(return_value=httpx.Response(
                200, headers={"Last-Modified": _last_modified(age_between)}))
            router.get(URL).mock(return_value=httpx.Response(200, content=b'{"a": 1}'))

            assert await instance.get(KEY, content_type="audio") is None
            assert await instance.get(KEY, content_type="json") == {"a": 1}
    finally:
        await instance.close()


@pytest.mark.unit
async def test_missing_last_modified_is_treated_as_expired(cache):
    """No Last-Modified means freshness is unverifiable, so it's a miss and
    the GET never fires - not served forever (DOJP-44 item 3, flipped)"""
    with respx.mock as router:
        router.head(URL).mock(return_value=httpx.Response(200))
        get_route = router.get(URL).mock(return_value=httpx.Response(200, content=b"audio"))

        assert await cache.get(KEY) is None
        assert get_route.call_count == 0


@pytest.mark.unit
async def test_head_404_is_a_miss(cache):
    with respx.mock as router:
        router.head(URL).mock(return_value=httpx.Response(404))
        assert await cache.get(KEY) is None


@pytest.mark.unit
async def test_disabled_cache_never_touches_the_network(monkeypatch):
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
    instance = S3MP3Cache()
    assert not instance.enabled

    with respx.mock:  # raises on any unmocked request
        assert await instance.get(KEY) is None
        assert await instance.get_raw(KEY) is None
        assert await instance.set(KEY, b"x") is False


# ---------------------------------------------------------------------------
# _retry_with_backoff
# ---------------------------------------------------------------------------


def _http_status_error(status):
    request = httpx.Request("PUT", URL)
    return httpx.HTTPStatusError(
        f"{status}", request=request, response=httpx.Response(status, request=request)
    )


@pytest.fixture
def sleepless(monkeypatch):
    """Capture backoff delays instead of actually sleeping"""
    delays = []

    async def fake_sleep(seconds):
        delays.append(seconds)

    monkeypatch.setattr(s3_cache_module.asyncio, "sleep", fake_sleep)
    return delays


@pytest.mark.unit
async def test_retry_succeeds_after_transient_503s(cache, sleepless):
    attempts = 0

    async def flaky():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise _http_status_error(503)
        return "ok"

    assert await cache._retry_with_backoff(flaky) == "ok"
    assert attempts == 3
    # exponential with jitter: 2^n * 0.1 + U(0, 0.1)
    assert 0.1 <= sleepless[0] <= 0.2
    assert 0.2 <= sleepless[1] <= 0.3


@pytest.mark.unit
async def test_retry_gives_up_after_max_attempts(cache, sleepless):
    async def always_503():
        raise _http_status_error(503)

    with pytest.raises(httpx.HTTPStatusError):
        await cache._retry_with_backoff(always_503)
    assert len(sleepless) == 2  # sleeps between attempts, not after the last


@pytest.mark.unit
@pytest.mark.parametrize("status", [400, 403, 500])
async def test_non_503_errors_are_not_retried(cache, sleepless, status):
    attempts = 0

    async def failing():
        nonlocal attempts
        attempts += 1
        raise _http_status_error(status)

    with pytest.raises(httpx.HTTPStatusError):
        await cache._retry_with_backoff(failing)
    assert attempts == 1
    assert sleepless == []


# ---------------------------------------------------------------------------
# set(): upload path end to end (through respx)
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_set_uploads_with_signed_headers_and_ttl_metadata(cache):
    with respx.mock as router:
        put_route = router.put(URL).mock(return_value=httpx.Response(200))
        assert await cache.set(KEY, b"opus bytes") is True

    request = put_route.calls[0].request
    assert request.headers["x-amz-meta-ttl-minutes"] == str(cache.ttl_minutes)
    assert request.headers["Content-Type"] == "audio/opus"  # from the .opus key
    assert request.headers["Authorization"].startswith("AWS4-HMAC-SHA256 Credential=")
    assert request.content == b"opus bytes"


@pytest.mark.unit
async def test_set_json_uses_the_api_ttl(cache):
    json_url = f"https://{HOST}/cache/data.json"
    with respx.mock as router:
        put_route = router.put(json_url).mock(return_value=httpx.Response(200))
        assert await cache.set("cache/data.json", {"a": 1}, content_type="json") is True

    request = put_route.calls[0].request
    assert request.headers["x-amz-meta-ttl-minutes"] == str(cache.api_ttl_minutes)
    assert request.headers["Content-Type"] == "application/json"


@pytest.mark.unit
async def test_set_retries_through_a_transient_503(cache, sleepless):
    with respx.mock as router:
        put_route = router.put(URL)
        put_route.side_effect = [httpx.Response(503), httpx.Response(200)]

        assert await cache.set(KEY, b"x") is True
        assert put_route.call_count == 2
        assert len(sleepless) == 1


@pytest.mark.unit
async def test_set_returns_false_when_503s_persist(cache, sleepless):
    with respx.mock as router:
        put_route = router.put(URL).mock(return_value=httpx.Response(503))
        assert await cache.set(KEY, b"x") is False
        assert put_route.call_count == 3  # max retries, then swallowed to False


@pytest.mark.unit
async def test_set_does_not_retry_a_403(cache, sleepless):
    """A signing/permission failure is deterministic - retrying it is waste"""
    with respx.mock as router:
        put_route = router.put(URL).mock(return_value=httpx.Response(403))
        assert await cache.set(KEY, b"x") is False
        assert put_route.call_count == 1
        assert sleepless == []


# ---------------------------------------------------------------------------
# get_raw
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_get_raw_ignores_object_age(cache):
    """No TTL for content-hashed objects - a year-old fun fact still serves"""
    with respx.mock as router:
        router.get(URL).mock(return_value=httpx.Response(
            200, content=b"old audio",
            headers={"Last-Modified": _last_modified(365 * 24 * 3600)}))
        assert await cache.get_raw(KEY) == b"old audio"


@pytest.mark.unit
async def test_get_raw_404_is_none(cache):
    with respx.mock as router:
        router.get(URL).mock(return_value=httpx.Response(404))
        assert await cache.get_raw(KEY) is None
