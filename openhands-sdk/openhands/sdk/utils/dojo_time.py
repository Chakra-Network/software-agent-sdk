"""Dojo fake-time integration: read and advance the dojo time-server clock.

The time-server is a *stopped* clock — it only moves on ``POST /advance`` (the
agent does this once per completion round); ``GET /state`` returns the current
instant. Active only when ``DOJO_FAKETIME_ENABLED`` is set (the time-server's
feature flag); otherwise every function here is a no-op and callers fall back to
the real wall clock.
"""

from __future__ import annotations

import os
from datetime import datetime

import httpx

from openhands.sdk.logger import get_logger


logger = get_logger(__name__)

_ENABLED_ENV = "DOJO_FAKETIME_ENABLED"
_TIMESERVER_URL_ENV = "DOJO_TIMESERVER_URL"
_ADVANCE_DELTA_MS_ENV = "DOJO_TIMESERVER_ADVANCE_DELTA_MS"
_ADVANCE_DELTA_MS_DEFAULT = 1000
_STATE_PATH = "/state"
_ADVANCE_PATH = "/advance"
_TIMESERVER_TIMEOUT_SEC = 2.0


def _timeserver_url() -> str | None:
    """The time-server base URL when fake-time is enabled, else None.

    Gated on the ``DOJO_FAKETIME_ENABLED`` feature flag; the URL comes from
    ``DOJO_TIMESERVER_URL``.
    """
    if _ENABLED_ENV not in os.environ:
        return None
    return os.environ.get(_TIMESERVER_URL_ENV) or None


def _advance_delta_ms() -> int:
    raw = os.environ.get(_ADVANCE_DELTA_MS_ENV)
    if not raw:
        return _ADVANCE_DELTA_MS_DEFAULT
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            f"invalid {_ADVANCE_DELTA_MS_ENV}={raw!r}; "
            f"using {_ADVANCE_DELTA_MS_DEFAULT}"
        )
        return _ADVANCE_DELTA_MS_DEFAULT


def fake_now() -> datetime | None:
    """The time-server's simulated clock, or None when inactive/unreachable.

    Read live on every call (no caching) so the stamp is exact — the clock can
    move between calls. Best-effort: any failure returns None so callers fall back
    to the real clock. Returns a naive datetime to match ``datetime.now()``'s
    format (no timezone suffix).
    """
    url = _timeserver_url()
    if not url:
        return None
    try:
        resp = httpx.get(f"{url}{_STATE_PATH}", timeout=_TIMESERVER_TIMEOUT_SEC)
        resp.raise_for_status()
        now_ms = resp.json().get("nowMs")
    except Exception as e:
        logger.warning(f"dojo time-server {_STATE_PATH} failed: {e}")
        return None
    if not isinstance(now_ms, (int, float)) or now_ms <= 0:
        logger.warning(f"dojo time-server {_STATE_PATH} returned nowMs={now_ms!r}")
        return None
    return datetime.fromtimestamp(now_ms / 1000)


def now_isoformat() -> str:
    """ISO timestamp for events: the fake clock if active, else the real clock."""
    return (fake_now() or datetime.now()).isoformat()


def advance_clock() -> None:
    """Advance the dojo time-server clock by one configured step.

    No-op unless dojo fake-time is active. Called once per completion round,
    after the round's events — and their recorded timestamps — exist, so the
    round keeps its pre-advance time and the clock moves on for the next round.
    Best-effort: a time-server hiccup must not abort the agent run.
    """
    url = _timeserver_url()
    if not url:
        return
    try:
        httpx.post(
            f"{url}{_ADVANCE_PATH}",
            json={"deltaMs": _advance_delta_ms()},
            timeout=_TIMESERVER_TIMEOUT_SEC,
        )
    except Exception as e:
        logger.warning(f"dojo time-server {_ADVANCE_PATH} failed: {e}")


async def aadvance_clock() -> None:
    """Async variant of :func:`advance_clock`."""
    url = _timeserver_url()
    if not url:
        return
    try:
        async with httpx.AsyncClient(timeout=_TIMESERVER_TIMEOUT_SEC) as client:
            await client.post(
                f"{url}{_ADVANCE_PATH}", json={"deltaMs": _advance_delta_ms()}
            )
    except Exception as e:
        logger.warning(f"dojo time-server {_ADVANCE_PATH} failed: {e}")
