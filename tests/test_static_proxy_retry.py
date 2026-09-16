"""Static-audio proxy transport-error handling (Sentry DREAMING-OF-A-JETPLANE-21)

A transient connection blip between Railway and S3 failed a real
/free/scanning request with an empty-message httpx transport error. The proxy
now retries such errors once, and its terminal log line always names the
exception type (transport errors stringify to "", which made the original
Sentry event undiagnosable from its text).
"""

import logging

import httpx
import pytest
import respx
from starlette.requests import Request

from app.static_audio import proxy_s3_audio

URL = "https://dreaming-of-a-jet-plane.s3.us-east-2.amazonaws.com/free/scanning.opus"


def _request():
    return Request({"type": "http", "method": "GET", "path": "/free/scanning",
                    "query_string": b"", "headers": [], "client": ("1.2.3.4", 1)})


@pytest.mark.unit
async def test_transport_error_is_retried_and_recovers():
    """The DREAMING-OF-A-JETPLANE-21 scenario: first attempt dies with a
    bare ReadError, the immediate retry serves the clip"""
    calls = {"n": 0}

    def flaky(request):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ReadError("")  # empty message, like the real event
        return httpx.Response(200, content=b"opus-bytes")

    with respx.mock as router:
        router.get(URL).mock(side_effect=flaky)
        response = await proxy_s3_audio(_request(), URL, "audio/opus", error_style="json")

    assert calls["n"] == 2
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/opus"


@pytest.mark.unit
async def test_transport_error_retries_exactly_once(caplog):
    """A persistent failure gets one retry, not a loop - and the terminal
    error log names the exception type despite the empty message"""
    calls = {"n": 0}

    def always_fails(request):
        calls["n"] += 1
        raise httpx.ReadError("")

    with respx.mock as router:
        router.get(URL).mock(side_effect=always_fails)
        with caplog.at_level(logging.ERROR, logger="app.static_audio"):
            response = await proxy_s3_audio(_request(), URL, "audio/opus", error_style="json")

    assert calls["n"] == 2, "exactly one retry"
    assert response.status_code == 500
    assert any("ReadError" in r.message for r in caplog.records), \
        "the error log must name the exception type"


@pytest.mark.unit
async def test_timeout_is_not_retried():
    """Timeouts keep their historical behavior: a 30s wait must not become
    60s; the 504 path is unchanged"""
    calls = {"n": 0}

    def times_out(request):
        calls["n"] += 1
        raise httpx.ReadTimeout("timed out")

    with respx.mock as router:
        router.get(URL).mock(side_effect=times_out)
        response = await proxy_s3_audio(_request(), URL, "audio/opus", error_style="json")

    assert calls["n"] == 1, "timeouts must not be retried"
    assert response.status_code == 504
