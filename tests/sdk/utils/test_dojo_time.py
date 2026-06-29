"""Tests for the dojo fake-time integration (openhands.sdk.utils.dojo_time)."""

from datetime import datetime
from unittest.mock import MagicMock, patch

from openhands.sdk.utils import dojo_time


_URL = "http://127.0.0.1:9989"
# Fake-time active: the feature flag is set and the time-server URL is published.
_ACTIVE_ENV = {dojo_time._ENABLED_ENV: "1", dojo_time._TIMESERVER_URL_ENV: _URL}


def _state_response(now_ms):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"nowMs": now_ms}
    return resp


def test_fake_now_inactive_when_flag_unset():
    """Flag unset => no HTTP, returns None, callers use the real clock."""
    with patch.dict("os.environ", {}, clear=True):
        with patch.object(dojo_time.httpx, "get") as mock_get:
            assert dojo_time.fake_now() is None
            mock_get.assert_not_called()


def test_flag_is_the_gate_not_the_url():
    """The URL alone does not activate fake-time; DOJO_FAKETIME_ENABLED does."""
    with patch.dict("os.environ", {dojo_time._TIMESERVER_URL_ENV: _URL}, clear=True):
        with patch.object(dojo_time.httpx, "get") as mock_get:
            assert dojo_time.fake_now() is None
            mock_get.assert_not_called()


def test_fake_now_none_when_enabled_but_url_missing():
    """Flag set but no URL => no-op (best-effort), never raises."""
    with patch.dict("os.environ", {dojo_time._ENABLED_ENV: "1"}, clear=True):
        with patch.object(dojo_time.httpx, "get") as mock_get:
            assert dojo_time.fake_now() is None
            mock_get.assert_not_called()


def test_now_isoformat_falls_back_to_real_clock_when_inactive():
    with patch.dict("os.environ", {}, clear=True):
        before = datetime.now()
        stamp = datetime.fromisoformat(dojo_time.now_isoformat())
        after = datetime.now()
        assert before <= stamp <= after


def test_fake_now_reads_state_nowms():
    """nowMs from /state becomes the (naive) timestamp."""
    now_ms = 1_700_000_000_000  # 2023-11-14T...
    expected = datetime.fromtimestamp(now_ms / 1000)
    with patch.dict("os.environ", _ACTIVE_ENV):
        with patch.object(
            dojo_time.httpx, "get", return_value=_state_response(now_ms)
        ) as mock_get:
            assert dojo_time.fake_now() == expected
            mock_get.assert_called_once_with(
                f"{_URL}/state", timeout=dojo_time._TIMESERVER_TIMEOUT_SEC
            )


def test_fake_now_reads_live_every_call():
    """No caching: each call hits /state so the stamp tracks the moving clock."""
    with patch.dict("os.environ", _ACTIVE_ENV):
        with patch.object(
            dojo_time.httpx, "get", return_value=_state_response(1_700_000_000_000)
        ) as mock_get:
            dojo_time.fake_now()
            dojo_time.fake_now()
            assert mock_get.call_count == 2


def test_fake_now_best_effort_on_failure():
    """A time-server error returns None (caller falls back), never raises."""
    with patch.dict("os.environ", _ACTIVE_ENV):
        with patch.object(dojo_time.httpx, "get", side_effect=Exception("boom")):
            assert dojo_time.fake_now() is None


def test_fake_now_rejects_nonpositive_nowms():
    with patch.dict("os.environ", _ACTIVE_ENV):
        with patch.object(dojo_time.httpx, "get", return_value=_state_response(0)):
            assert dojo_time.fake_now() is None


def test_advance_clock_posts_default_delta():
    with patch.dict("os.environ", _ACTIVE_ENV):
        with patch.object(dojo_time.httpx, "post") as mock_post:
            dojo_time.advance_clock()
            mock_post.assert_called_once_with(
                f"{_URL}/advance",
                json={"deltaMs": dojo_time._ADVANCE_DELTA_MS_DEFAULT},
                timeout=dojo_time._TIMESERVER_TIMEOUT_SEC,
            )


def test_advance_clock_honors_custom_delta():
    env = {**_ACTIVE_ENV, dojo_time._ADVANCE_DELTA_MS_ENV: "5000"}
    with patch.dict("os.environ", env):
        with patch.object(dojo_time.httpx, "post") as mock_post:
            dojo_time.advance_clock()
            assert mock_post.call_args.kwargs["json"] == {"deltaMs": 5000}


def test_advance_clock_inactive_when_flag_unset():
    with patch.dict("os.environ", {dojo_time._TIMESERVER_URL_ENV: _URL}, clear=True):
        with patch.object(dojo_time.httpx, "post") as mock_post:
            dojo_time.advance_clock()
            mock_post.assert_not_called()
