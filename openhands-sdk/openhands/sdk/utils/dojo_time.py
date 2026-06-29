"""Dojo fake-time integration: read and advance the dojo time-server clock.

The dojo time-server is a *stopped* clock — it only moves when something POSTs
``/advance`` (the agent does this once per completion round). Between advances,
``GET /state`` returns a constant instant. The integration is active only when
the time-server publishes ``DOJO_TIMESERVER_URL`` into the environment (it does
so only while faking); absent, every function here is a no-op and callers fall
back to the real wall clock.

This is the explicit-read replacement for the old libfaketime/``LD_PRELOAD``
approach. Preloading libfaketime faked the clock process-wide — including inside
OpenSSL's certificate-validity check — so a real outbound TLS handshake to the
LLM endpoint saw a clock in the past and rejected the (not-yet-valid) cert.
Reading the fake clock explicitly, only where we stamp trajectory events, keeps
the process on the real clock for everything else (TLS, timeouts, logging).
"""

from __future__ import annotations

import os
from datetime import datetime

import httpx

from openhands.sdk.logger import get_logger


logger = get_logger(__name__)

_TIMESERVER_URL_ENV = "DOJO_TIMESERVER_URL"
_ADVANCE_DELTA_MS_ENV = "DOJO_TIMESERVER_ADVANCE_DELTA_MS"
_ADVANCE_DELTA_MS_DEFAULT = 1000
_STATE_PATH = "/state"
_ADVANCE_PATH = "/advance"
_TIMESERVER_TIMEOUT_SEC = 2.0


def _timeserver_url() -> str | None:
    """The dojo time-server base URL, or None when fake-time is inactive."""
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

    Reads ``GET /state`` live on every call (no caching) so the stamped time is
    exact — the clock can move (``/advance``) between any two calls. Best-effort:
    any failure returns None so callers fall back to the real clock rather than
    aborting the work that needed a timestamp.

    The returned naive datetime matches the previous ``datetime.now()``
    (libfaketime) behavior, so trajectory timestamps keep their existing format
    with no timezone suffix.
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
