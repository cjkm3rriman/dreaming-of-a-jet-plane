"""Fire-and-forget task management (DOJP-42).

`asyncio.create_task` returns a task the event loop holds only a *weak*
reference to. A caller that discards the return value can have the task
garbage-collected mid-flight, and any exception it raised is never retrieved
(silently swallowed). Both matter here: the fire-and-forget sites are the
entire cache-write path and the pre-generation pipeline, so a dropped task is
missing audio with nothing in the logs.

`spawn` keeps a strong reference until the task finishes and logs any
exception it raised. Use it instead of a bare `asyncio.create_task` for work
whose result is not awaited.
"""

import asyncio
import logging
from typing import Set

logger = logging.getLogger(__name__)

# Strong references to in-flight fire-and-forget tasks, so the event loop
# cannot garbage-collect them before they complete.
_background_tasks: Set[asyncio.Task] = set()


def spawn(coro, description: str = "background task") -> asyncio.Task:
    """Schedule a coroutine as a tracked fire-and-forget task.

    The task is kept referenced until it finishes; if it raises, the exception
    is logged (a bare create_task would swallow it). Returns the task, though
    callers typically ignore it.
    """
    task = asyncio.create_task(coro)
    _background_tasks.add(task)

    def _done(t: asyncio.Task) -> None:
        _background_tasks.discard(t)
        if t.cancelled():
            return
        exc = t.exception()
        if exc is not None:
            logger.error("Background task '%s' failed: %s", description, exc, exc_info=exc)

    task.add_done_callback(_done)
    return task
