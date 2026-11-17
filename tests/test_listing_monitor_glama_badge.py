"""The monitor must not read an API 404 as "this listing does not exist".

MEASURED 17.11.2026, and it cost a month of wrong reports:

    GET /v1/servers/hristovdimitri2-hub/kristo-intelligence-6   ->  HTTP 404
    GET .../badges/score.svg for that same slug                 ->  "kristo-intelligence
                                                                    — MCP server rated B on Glama"
    GET .../badges/score.svg for a made-up slug                 ->  "This MCP server is
                                                                    not listed on Glama"

So a 404 means the listing is NOT VISIBLE to the API — hidden, unclaimed, or
under review — and the badge is what separates that from a listing that truly
does not exist. The monitor used to set `missing` from the API status alone and
reported a hidden listing with a real score as absent.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import listing_monitor as lm  # noqa: E402


class _Resp:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text


HIDDEN = ('<svg><text>kristo-intelligence</text>'
          '<text>MCP server rated B on Glama</text></svg>')
ABSENT = '<svg><text>This MCP server is not listed on Glama</text></svg>'


def test_the_badge_text_is_read_from_the_svg(monkeypatch):
    monkeypatch.setattr(lm.requests, "get",
                        lambda *a, **k: _Resp(200, HIDDEN))
    text = lm._glama_badge_text("owner/slug")
    assert text and "rated B" in text, text


def test_an_unreachable_badge_is_none_not_a_verdict(monkeypatch):
    """A failed read is not evidence of absence — the same rule as everywhere
    else in this codebase."""
    monkeypatch.setattr(lm.requests, "get",
                        lambda *a, **k: _Resp(503, ""))
    assert lm._glama_badge_text("owner/slug") is None

    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(lm.requests, "get", boom)
    assert lm._glama_badge_text("owner/slug") is None


def _state_with(monkeypatch, api_status, badge_text):
    monkeypatch.setattr(lm, "_glama_get", lambda *a, **k: (api_status, None))
    monkeypatch.setattr(lm, "_glama_badge_text", lambda slug: badge_text)
    return lm.fetch_glama_state("key")


def test_a_404_with_a_scored_badge_is_HIDDEN_not_missing(monkeypatch):
    state = _state_with(monkeypatch, 404, "kristo-intelligence — MCP server rated B on Glama")
    srv = state["servers"]
    assert srv["status"] == 404
    assert srv["listing_state"] == "hidden", srv
    assert srv["missing"] is False, srv
    assert srv["badge_renders_a_score"] is True


def test_a_404_with_a_not_listed_badge_IS_absent(monkeypatch):
    state = _state_with(monkeypatch, 404, "This MCP server is not listed on Glama")
    srv = state["servers"]
    assert srv["listing_state"] == "absent", srv
    assert srv["missing"] is True, srv
    assert srv["badge_renders_a_score"] is False


def test_a_404_with_an_unreadable_badge_is_UNKNOWN_not_absent(monkeypatch):
    """We could not tell. Calling it absent would be a verdict we did not earn;
    calling it hidden would be the same error in the other direction."""
    state = _state_with(monkeypatch, 404, None)
    assert state["servers"]["listing_state"] == "unknown", state["servers"]
    assert state["servers"]["missing"] is False


def test_a_200_is_visible_and_never_missing(monkeypatch):
    state = _state_with(monkeypatch, 200, None)
    assert state["servers"]["listing_state"] == "visible"
    assert state["servers"]["missing"] is False
