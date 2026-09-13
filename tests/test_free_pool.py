"""Unit tests for free_pool: stitching, rate limiting, session selection

DOJP-47 item 4. Stitching is the last hop before a child's speaker and had
zero direct coverage; the rate limiter guards the free tier and had none
either. Stitch tests use real pydub/ffmpeg over generated tones; limiter
tests use a fake clock so boundaries are exact, not sleep-based.
"""

import io

import pytest
from pydub import AudioSegment
from pydub.generators import Sine

import app.free_pool as free_pool
from app.free_pool import (
    _trim_silence,
    check_free_tier_rate_limit,
    get_session_for_free_user,
    stitch_audio,
    stitch_audio_multi,
)

# ---------------------------------------------------------------------------
# audio helpers
# ---------------------------------------------------------------------------


def _tone(ms=500, freq=440):
    return Sine(freq).to_audio_segment(duration=ms).set_channels(1)


def _mp3(segment):
    buf = io.BytesIO()
    segment.export(buf, format="mp3")
    return buf.getvalue()


def _decode(audio_bytes, fmt="mp3"):
    return AudioSegment.from_file(io.BytesIO(audio_bytes), format=fmt)


# ---------------------------------------------------------------------------
# stitch_audio
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_stitch_audio_duration_is_lead_opening_gap_body_tail():
    """add_silence=True wraps in 1s lead + 1s tail, with a 1s gap between:
    1.0 + 0.5 + 1.0 + 0.5 + 1.0 = 4.0s"""
    out = await stitch_audio(_mp3(_tone(500)), _mp3(_tone(500)), add_silence=True)
    clip = _decode(out)
    assert clip.duration_seconds == pytest.approx(4.0, abs=0.3)


@pytest.mark.unit
async def test_stitch_audio_without_padding():
    """add_silence=False: 0.5 + 1.0 gap + 0.5 = 2.0s"""
    out = await stitch_audio(_mp3(_tone(500)), _mp3(_tone(500)), add_silence=False)
    assert _decode(out).duration_seconds == pytest.approx(2.0, abs=0.3)


@pytest.mark.unit
async def test_stitch_audio_trims_silence_so_the_gap_stays_one_second():
    """An opening with a long silent tail and a body with a long silent lead
    must NOT produce a dead 2.4s pause - trimming keeps the gap at ~1s"""
    opening = _tone(500) + AudioSegment.silent(duration=800)
    body = AudioSegment.silent(duration=600) + _tone(500)
    out = await stitch_audio(_mp3(opening), _mp3(body), add_silence=False)
    # 0.5 + 1.0 + 0.5 plus the 75ms tail padding the trimmer preserves
    assert _decode(out).duration_seconds == pytest.approx(2.1, abs=0.35)


@pytest.mark.unit
async def test_stitch_audio_normalizes_loudness():
    """Output is normalized to TARGET_DBFS so every plane sounds the same"""
    quiet = _tone(500).apply_gain(-25)
    loud = _tone(500).apply_gain(+5)
    out = await stitch_audio(_mp3(quiet), _mp3(loud), add_silence=False)
    assert _decode(out).dBFS == pytest.approx(free_pool.TARGET_DBFS, abs=4)


@pytest.mark.unit
async def test_stitch_audio_opus_round_trip():
    """The production format: opus in, decodable ogg/opus out"""
    seg = _tone(400)
    buf = io.BytesIO()
    seg.export(buf, format="ogg", codec="libopus")
    opus = buf.getvalue()

    out = await stitch_audio(opus, opus, add_silence=False, audio_format="opus")
    clip = _decode(out, fmt="ogg")
    assert clip.duration_seconds == pytest.approx(1.8, abs=0.35)
    assert clip.dBFS > -50


# ---------------------------------------------------------------------------
# stitch_audio_multi
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_stitch_multi_honors_custom_gap_durations():
    """The production call: 4 segments with gaps 1000/1000/500ms.
    1.0 lead + 4x0.4 + (1.0 + 1.0 + 0.5) + 1.0 tail = 6.1s"""
    seg = _mp3(_tone(400))
    out = await stitch_audio_multi(
        [seg, seg, seg, seg], add_silence=True, gap_durations=[1000, 1000, 500]
    )
    assert _decode(out).duration_seconds == pytest.approx(6.1, abs=0.4)


@pytest.mark.unit
async def test_stitch_multi_defaults_to_one_second_gaps():
    """3 segments, no gap_durations: 0.4*3 + 2x1.0 = 3.2s (no padding)"""
    seg = _mp3(_tone(400))
    out = await stitch_audio_multi([seg, seg, seg], add_silence=False)
    assert _decode(out).duration_seconds == pytest.approx(3.2, abs=0.35)


@pytest.mark.unit
async def test_stitch_multi_single_segment_has_no_gaps():
    out = await stitch_audio_multi([_mp3(_tone(400))], add_silence=False)
    assert _decode(out).duration_seconds == pytest.approx(0.4, abs=0.3)


@pytest.mark.unit
async def test_stitch_multi_rejects_empty_input():
    with pytest.raises(ValueError):
        await stitch_audio_multi([], add_silence=False)


@pytest.mark.unit
async def test_stitch_survives_all_silent_segments():
    """_trim_silence's guard: a fully-silent segment is passed through rather
    than trimmed to nothing - the stitch must not crash or emit garbage"""
    silent = _mp3(AudioSegment.silent(duration=400))
    out = await stitch_audio_multi([silent, silent], add_silence=False)
    clip = _decode(out)  # decodable, even though inaudible
    assert clip.duration_seconds > 0.5


# ---------------------------------------------------------------------------
# _trim_silence
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_trim_silence_removes_lead_and_tail_but_keeps_the_tone():
    padded = AudioSegment.silent(duration=700) + _tone(500) + AudioSegment.silent(duration=700)
    trimmed = _trim_silence(padded)
    # tone survives; trailing keeps <=75ms padding + detection granularity
    assert 480 <= len(trimmed) <= 700
    assert trimmed.dBFS > -50


@pytest.mark.unit
def test_trim_silence_returns_all_silent_input_unchanged():
    silent = AudioSegment.silent(duration=400)
    assert len(_trim_silence(silent)) == len(silent)


# ---------------------------------------------------------------------------
# check_free_tier_rate_limit (fake clock - no sleeps, exact boundaries)
# ---------------------------------------------------------------------------


@pytest.fixture
def clock(monkeypatch):
    """Controllable time for the limiter, isolated cache per test"""
    state = {"now": 1_000_000.0}
    monkeypatch.setattr(free_pool.time, "time", lambda: state["now"])
    monkeypatch.setattr(free_pool, "_rate_limit_cache", {})
    monkeypatch.setattr(free_pool, "FREE_TIER_RATE_LIMIT", 3)
    return state


@pytest.mark.unit
def test_requests_allowed_up_to_the_limit(clock):
    for i in range(3):
        allowed, retry = check_free_tier_rate_limit("1.2.3.4")
        assert allowed, f"request {i + 1} of 3 should be allowed"
        assert retry is None


@pytest.mark.unit
def test_request_over_the_limit_is_denied_with_exact_retry_after(clock):
    for _ in range(3):
        check_free_tier_rate_limit("1.2.3.4")

    clock["now"] += 10  # 10s into the 60s window
    allowed, retry = check_free_tier_rate_limit("1.2.3.4")
    assert not allowed
    # oldest request at t0, window 60s: retry = 60 - 10 + 1
    assert retry == free_pool.FREE_TIER_RATE_WINDOW - 10 + 1


@pytest.mark.unit
def test_window_expiry_readmits_the_client(clock):
    for _ in range(3):
        check_free_tier_rate_limit("1.2.3.4")

    clock["now"] += free_pool.FREE_TIER_RATE_WINDOW + 1
    allowed, retry = check_free_tier_rate_limit("1.2.3.4")
    assert allowed
    assert retry is None


@pytest.mark.unit
def test_denied_requests_do_not_extend_the_ban(clock):
    """Hammering while limited must not push the reset time out"""
    for _ in range(3):
        check_free_tier_rate_limit("1.2.3.4")
    for _ in range(20):  # a scraper retrying while banned
        clock["now"] += 1
        check_free_tier_rate_limit("1.2.3.4")

    clock["now"] = 1_000_000.0 + free_pool.FREE_TIER_RATE_WINDOW + 1
    allowed, _ = check_free_tier_rate_limit("1.2.3.4")
    assert allowed, "denied attempts must not count toward the limit"


@pytest.mark.unit
def test_rate_limit_is_per_ip(clock):
    for _ in range(3):
        check_free_tier_rate_limit("1.2.3.4")

    allowed, _ = check_free_tier_rate_limit("5.6.7.8")
    assert allowed, "one household's limit must not block another"


# ---------------------------------------------------------------------------
# get_session_for_free_user
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_empty_pool_returns_none():
    assert get_session_for_free_user("1.2.3.4", {}) is None
    assert get_session_for_free_user("1.2.3.4", {"entries": []}) is None


@pytest.mark.unit
def test_single_entry_pool_returns_it():
    entry = {"id": "only"}
    assert get_session_for_free_user("1.2.3.4", {"entries": [entry]}) == entry


@pytest.mark.unit
def test_selection_draws_only_from_the_five_newest_sessions():
    """Freshness by construction: older sessions must never be served"""
    entries = [{"id": f"s{i}"} for i in range(8)]
    index = {"entries": entries}
    newest_five = {f"s{i}" for i in range(3, 8)}

    seen = {get_session_for_free_user("1.2.3.4", index)["id"] for _ in range(200)}
    assert seen <= newest_five, f"served a stale session: {seen - newest_five}"
    # and with 200 draws over 5 entries, all of them should appear
    assert seen == newest_five, "recent sessions missing from rotation"
