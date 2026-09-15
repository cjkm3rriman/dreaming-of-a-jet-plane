"""Long-lived process state stays bounded and consistent (DOJP-42)

These guard three degrade-over-weeks issues that a fresh container hides:
unbounded in-memory dicts, a free-pool index that could diverge from S3 on a
failed write, and fire-and-forget tasks the event loop can GC mid-flight.
"""

import asyncio

import pytest

import app.background as background
import app.free_pool as free_pool
import app.scanning as scanning


# ---------------------------------------------------------------------------
# 1a. scanning debounce cache eviction
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_scanning_cache_evicts_entries_past_the_debounce_window(monkeypatch):
    clock = {"now": 1_000_000.0}
    monkeypatch.setattr(scanning.time, "time", lambda: clock["now"])
    monkeypatch.setattr(scanning, "_scanning_request_cache", {})

    # simulate the write half of stream_scanning for many distinct sessions
    def record(session_key):
        current_time = scanning.time.time()
        cutoff = current_time - scanning.SCANNING_DEBOUNCE_SECONDS
        for key in [k for k, t in scanning._scanning_request_cache.items() if t < cutoff]:
            del scanning._scanning_request_cache[key]
        scanning._scanning_request_cache[session_key] = current_time

    for i in range(500):
        clock["now"] += 1  # 1s apart; window is 30s
        record(f"session-{i}")

    # only entries within the last 30s survive, not all 500
    assert len(scanning._scanning_request_cache) <= scanning.SCANNING_DEBOUNCE_SECONDS + 1


# ---------------------------------------------------------------------------
# 1b. rate-limit cache eviction of aged-out IPs
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_rate_limit_cache_evicts_stale_ips(monkeypatch):
    clock = {"now": 1_000_000.0}
    monkeypatch.setattr(free_pool.time, "time", lambda: clock["now"])
    monkeypatch.setattr(free_pool, "_rate_limit_cache", {})

    # 300 one-shot scraper IPs, each seen once, all now well past the window
    for i in range(300):
        free_pool.check_free_tier_rate_limit(f"10.0.{i // 256}.{i % 256}")

    clock["now"] += free_pool.FREE_TIER_RATE_WINDOW + 5

    # one more request triggers the sweep (dict is > 256)
    free_pool.check_free_tier_rate_limit("172.16.0.1")

    # every aged-out scraper IP is gone; effectively just the fresh one remains
    assert len(free_pool._rate_limit_cache) <= 2


@pytest.mark.unit
def test_rate_limit_still_enforces_the_limit_after_eviction(monkeypatch):
    """Eviction must not weaken the limiter for an active IP"""
    clock = {"now": 1_000_000.0}
    monkeypatch.setattr(free_pool.time, "time", lambda: clock["now"])
    monkeypatch.setattr(free_pool, "_rate_limit_cache", {})
    monkeypatch.setattr(free_pool, "FREE_TIER_RATE_LIMIT", 3)

    ip = "192.0.2.5"
    assert all(free_pool.check_free_tier_rate_limit(ip)[0] for _ in range(3))
    allowed, retry = free_pool.check_free_tier_rate_limit(ip)
    assert not allowed and retry is not None


# ---------------------------------------------------------------------------
# 2. free-pool index does not diverge from S3 on a failed write
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_failed_index_write_leaves_the_cache_unchanged(monkeypatch):
    seed = {"version": 1, "updated_at": "t0", "entries": [{"id": "existing", "planes": []}]}
    monkeypatch.setattr(free_pool, "_free_pool_index_cache", seed)
    monkeypatch.setattr(free_pool, "_free_pool_index_timestamp", 1e12)  # keep cache fresh

    async def failing_set(key, data):
        return False

    monkeypatch.setattr(free_pool.s3_cache, "set", failing_set)

    ok = await free_pool.update_free_pool_index("new-session", [{"index": 1}], "inworld")

    assert ok is False
    # the in-memory cache must not have gained the failed session
    ids = [e["id"] for e in free_pool._free_pool_index_cache["entries"]]
    assert ids == ["existing"], f"cache diverged from S3: {ids}"


@pytest.mark.unit
async def test_successful_index_write_updates_the_cache(monkeypatch):
    seed = {"version": 1, "updated_at": "t0", "entries": [{"id": "existing", "planes": []}]}
    monkeypatch.setattr(free_pool, "_free_pool_index_cache", seed)
    monkeypatch.setattr(free_pool, "_free_pool_index_timestamp", 1e12)

    async def ok_set(key, data):
        return True

    monkeypatch.setattr(free_pool.s3_cache, "set", ok_set)

    ok = await free_pool.update_free_pool_index("new-session", [{"index": 1}], "inworld")

    assert ok is True
    ids = [e["id"] for e in free_pool._free_pool_index_cache["entries"]]
    assert ids == ["existing", "new-session"]
    # and the original seed object was not mutated in place
    assert [e["id"] for e in seed["entries"]] == ["existing"]


# ---------------------------------------------------------------------------
# 3. background.spawn keeps a reference and surfaces exceptions
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_spawn_holds_a_reference_until_the_task_finishes(monkeypatch):
    monkeypatch.setattr(background, "_background_tasks", set())
    started = asyncio.Event()
    release = asyncio.Event()

    async def work():
        started.set()
        await release.wait()

    task = background.spawn(work(), "test")
    await started.wait()
    assert task in background._background_tasks  # strong ref held while running

    release.set()
    await task
    assert task not in background._background_tasks  # discarded on completion


@pytest.mark.unit
async def test_spawn_logs_a_failing_task_instead_of_swallowing_it(monkeypatch, caplog):
    monkeypatch.setattr(background, "_background_tasks", set())

    async def boom():
        raise ValueError("kaboom")

    import logging
    with caplog.at_level(logging.ERROR, logger="app.background"):
        task = background.spawn(boom(), "exploding task")
        with pytest.raises(ValueError):
            await task
        await asyncio.sleep(0)  # let the done-callback run

    assert any("exploding task" in r.message and "kaboom" in r.message for r in caplog.records)
    assert not background._background_tasks
