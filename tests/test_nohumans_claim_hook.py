"""The no humans ownership hook: armed from env, never from the repo.

Background. To edit a listing at nohumans.directory we prove domain control by
echoing a one-time 24h token that they issue per listing. The hook has existed
since the first claim, but the token table was a literal dict in main.py -- and
this repo is PUBLIC. So the only way to re-arm a challenge was to commit a live
credential, which publishes it.

On 07.11 we had to rotate exactly because claim tokens had leaked, so writing
the replacements into the same public file would have repeated the fault. The
table is now read from NOHUMANS_CLAIM_TOKENS_JSON.

What must stay true:
  * unset, empty, malformed or wrong-typed env is IGNORED, never fatal -- this
    hook runs on every response and a bad env var must not take us down;
  * only non-empty string values survive;
  * a token is echoed on its own path and NOWHERE else, so the hook cannot be
    used to attest control of a route we never asked about;
  * no token value ever reaches a log line.
"""
import json

import pytest

import main


@pytest.fixture()
def client(monkeypatch, tmp_path):
    """A live test client, with the real dashboard DB swapped out.

    The claim hook runs on every request, so exercising it against the real
    store would write traffic rows into the production-shaped database. Same
    shape as the fixture in test_price_sweep.py.
    """
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("KRISTO_FREE_TIER_LIMIT", "0")
    from integrations.dashboard_store import DashboardStore

    monkeypatch.setattr(main, "FREE_TIER_LIMIT", 0, raising=False)
    monkeypatch.setattr(main, "dashboard_db",
                        DashboardStore(tmp_path / "dashboard_state.db"))
    return main.app.test_client()


# ── parsing ────────────────────────────────────────────────────────────────

def test_unset_env_arms_nothing(monkeypatch):
    monkeypatch.delenv("NOHUMANS_CLAIM_TOKENS_JSON", raising=False)
    assert main._load_claim_tokens() == {}


@pytest.mark.parametrize("raw", ["", "   ", "not json at all", "{unclosed",
                                 "[1,2,3]", '"just a string"', "42", "null"])
def test_unusable_env_is_ignored_not_fatal(monkeypatch, raw):
    """Every one of these must return empty rather than raise."""
    monkeypatch.setenv("NOHUMANS_CLAIM_TOKENS_JSON", raw)
    assert main._load_claim_tokens() == {}


def test_a_well_formed_map_is_loaded(monkeypatch):
    token = "a" * 48
    monkeypatch.setenv("NOHUMANS_CLAIM_TOKENS_JSON",
                       json.dumps({"/api/bot-status": token}))
    assert main._load_claim_tokens() == {"/api/bot-status": token}


def test_non_string_and_blank_values_are_dropped(monkeypatch):
    monkeypatch.setenv("NOHUMANS_CLAIM_TOKENS_JSON", json.dumps({
        "/a": 123,          # not a string
        "/b": "",           # empty
        "/c": "   ",        # blank
        "/d": None,
        "/e": ["x"],        # wrong shape
        "/f": "keep-me",    # the only usable entry
    }))
    assert main._load_claim_tokens() == {"/f": "keep-me"}


def test_a_token_value_is_never_logged(monkeypatch, caplog):
    """The paths may be logged. The token must not appear, not even in part."""
    token = "SECRET-TOKEN-VALUE-" + "z" * 30
    monkeypatch.setenv("NOHUMANS_CLAIM_TOKENS_JSON",
                       json.dumps({"/api/bot-status": token}))
    with caplog.at_level("DEBUG"):
        main._load_claim_tokens()
    joined = "\n".join(r.getMessage() for r in caplog.records)
    assert token not in joined
    assert token[:12] not in joined, "even a prefix must not be logged"
    assert "/api/bot-status" in joined, "the path should be logged"


# ── the hook itself ────────────────────────────────────────────────────────

def test_the_header_is_echoed_on_its_own_path_only(monkeypatch, client):
    """Armed for one endpoint, silent on every other."""
    token = "b" * 48
    monkeypatch.setattr(main, "NOHUMANS_CLAIM_TOKENS",
                        {"/api/bot-status": token}, raising=True)
    c = client if hasattr(client, "get") else client[0]

    armed = c.get("/api/bot-status", headers={"User-Agent": "t/1.0"})
    assert armed.headers.get("x-nohumans-claim") == token

    for other in ("/api/stats", "/api/sales", "/health", "/"):
        r = c.get(other, headers={"User-Agent": "t/1.0"})
        assert "x-nohumans-claim" not in r.headers, (
            "%s must not attest a challenge issued for another path" % other)


def test_an_empty_table_echoes_nothing(monkeypatch, client):
    monkeypatch.setattr(main, "NOHUMANS_CLAIM_TOKENS", {}, raising=True)
    c = client if hasattr(client, "get") else client[0]
    r = c.get("/api/bot-status", headers={"User-Agent": "t/1.0"})
    assert "x-nohumans-claim" not in r.headers


def test_a_402_challenge_carries_the_header_too(monkeypatch, client):
    """Their verifier may probe the paid route and get a 402, not a 200.

    The hook runs `after_request`, so it must survive the paywall path --
    a token that only appears on 200s would fail to prove control of any
    paid endpoint, which is all five of ours.
    """
    token = "c" * 48
    monkeypatch.setattr(main, "NOHUMANS_CLAIM_TOKENS",
                        {"/api/bot-status": token}, raising=True)
    c = client if hasattr(client, "get") else client[0]
    r = c.get("/api/bot-status", headers={"User-Agent": "probe/" + "9" * 20})
    assert r.headers.get("x-nohumans-claim") == token


# ── the repo must not carry a live credential ──────────────────────────────

def test_the_repo_ships_an_empty_table():
    """The source default must be empty: a committed token is a published one."""
    from pathlib import Path
    src = Path(main.__file__).read_text(encoding="utf-8")
    assert "NOHUMANS_CLAIM_TOKENS = _load_claim_tokens()" in src, (
        "the table must come from the environment, not a literal")
    assert "NOHUMANS_CLAIM_TOKENS = {}" not in src, (
        "a hard-coded empty dict is fine at runtime but the assignment must "
        "go through the loader so the env path is the only way to arm it")
