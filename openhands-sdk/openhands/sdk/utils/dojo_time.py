"""Dojo fake-time integration: read and advance the dojo time-server clock.

The time-server is a *stopped* clock — it only moves on ``POST /advance`` (the
agent does this once per completion round); ``GET /state`` returns the current
instant. Active only when ``DOJO_FAKETIME_ENABLED`` is set (the time-server's
feature flag); otherwise every function here is a no-op and callers fall back to
the real wall clock.

When fake-time *is* active, failures raise rather than fall back: a broken
time-server must surface loudly, not silently stamp real-clock times into the
trajectory.
"""

from __future__ import annotations

import os
from datetime import datetime

import httpx


_ENABLED_ENV = "DOJO_FAKETIME_ENABLED"
_TIMESERVER_URL_ENV = "DOJO_TIMESERVER_URL"
_ADVANCE_DELTA_MS_ENV = "DOJO_TIMESERVER_ADVANCE_DELTA_MS"
_ADVANCE_DELTA_MS_DEFAULT = 1000
_STATE_PATH = "/state"
_ADVANCE_PATH = "/advance"
_TIMESERVER_TIMEOUT_SEC = 2.0


def _enabled() -> bool:
    """Whether dojo fake-time is active (the ``DOJO_FAKETIME_ENABLED`` flag)."""
    return _ENABLED_ENV in os.environ


def _timeserver_url() -> str:
    """The time-server base URL. Call only when :func:`_enabled`.

    Raises if the flag is set without a URL — a misconfiguration we surface
    rather than silently disabling fake-time.
    """
    url = os.environ.get(_TIMESERVER_URL_ENV)
    if not url:
        raise RuntimeError(f"{_ENABLED_ENV} is set but {_TIMESERVER_URL_ENV} is empty")
    return url


def _advance_delta_ms() -> int:
    raw = os.environ.get(_ADVANCE_DELTA_MS_ENV)
    if not raw:
        return _ADVANCE_DELTA_MS_DEFAULT
    return int(raw)  # raises ValueError on a malformed value — fail fast


def fake_now() -> datetime | None:
    """The time-server's simulated clock, or None when fake-time is inactive.

    Read live on every call (no caching) so the stamp is exact — the clock can
    move between calls. Raises on any failure while active. Returns a naive
    datetime to match ``datetime.now()``'s format (no timezone suffix).
    """
    if not _enabled():
        return None
    url = _timeserver_url()
    resp = httpx.get(f"{url}{_STATE_PATH}", timeout=_TIMESERVER_TIMEOUT_SEC)
    resp.raise_for_status()
    now_ms = resp.json()["nowMs"]
    if not isinstance(now_ms, (int, float)) or now_ms <= 0:
        raise ValueError(f"dojo time-server {_STATE_PATH} returned nowMs={now_ms!r}")
    return datetime.fromtimestamp(now_ms / 1000)


def now_isoformat() -> str:
    """ISO timestamp for events: the fake clock if active, else the real clock."""
    return (fake_now() or datetime.now()).isoformat()


def _advance_request() -> tuple[str, int] | None:
    """The ``(url, deltaMs)`` for a ``POST /advance``, or None when there's
    nothing to do — fake-time inactive, or a delta of 0 (clock frozen)."""
    if not _enabled():
        return None
    delta_ms = _advance_delta_ms()
    if delta_ms == 0:
        return None
    return _timeserver_url(), delta_ms


def advance_clock() -> None:
    """Advance the dojo time-server clock by one configured step.

    No-op unless dojo fake-time is active and the delta is non-zero. Called once
    per completion round, after the round's events — and their recorded
    timestamps — exist, so the round keeps its pre-advance time and the clock
    moves on for the next round. Raises if the advance fails.
    """
    req = _advance_request()
    if req is None:
        return
    url, delta_ms = req
    resp = httpx.post(
        f"{url}{_ADVANCE_PATH}",
        json={"deltaMs": delta_ms},
        timeout=_TIMESERVER_TIMEOUT_SEC,
    )
    resp.raise_for_status()


async def aadvance_clock() -> None:
    """Async variant of :func:`advance_clock`."""
    req = _advance_request()
    if req is None:
        return
    url, delta_ms = req
    async with httpx.AsyncClient(timeout=_TIMESERVER_TIMEOUT_SEC) as client:
        resp = await client.post(f"{url}{_ADVANCE_PATH}", json={"deltaMs": delta_ms})
    resp.raise_for_status()
