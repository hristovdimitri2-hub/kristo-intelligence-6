"""Tests for the Glama block in scripts/listing_monitor.py.

The Glama API is read-only (GETs only), so the block is pulse: it must read both
listings and the directory position, diff them against the saved state, and stay
completely silent when nothing moved. It must also work with no key at all
(CI / a fresh clone) and it must never read the key from anywhere but the
gitignored secrets file or the environment.
"""

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def monitor():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    return importlib.import_module("scripts.listing_monitor")


def _fake_get(payloads):
    """A stand-in for _glama_get keyed by path."""
    calls = []

    def fake(path, key, params=None):
        calls.append((path, params))
        if path in payloads:
            return payloads[path]
        return None

    fake.calls = calls
    return fake


SERVER_PAYLOAD = {
    "attributes": ["hosting:remote-capable"],
    "isBoosted": False,
    "qualityScore": None,
    "spdxLicense": None,
    "tools": [],
}
CONNECTOR_PAYLOAD = {
    "attributes": ["auth:none", "status:healthy"],
    "connection": {"transport": "streamable_http",
                   "url": "https://kristo-intelligence-api.onrender.com/mcp"},
    "healthy": True,
    "qualityScore": 4.7,
    "toolCount": 3,
    "lastTestedAt": "2026-09-22T09:25:14.365552Z",
}


# ── key resolution ─────────────────────────────────────────────────────────

def test_glama_key_prefers_env_over_file(monitor, monkeypatch, tmp_path):
    secret = tmp_path / "glama_api_key.txt"
    secret.write_text("from-file", encoding="utf-8")
    monkeypatch.setattr(monitor, "GLAMA_KEY_FILE", str(secret))
    monkeypatch.setenv("GLAMA_API_KEY", "from-env")
    assert monitor.glama_key() == "from-env"


def test_glama_key_falls_back_to_secrets_file(monitor, monkeypatch, tmp_path):
    secret = tmp_path / "glama_api_key.txt"
    secret.write_text("  glm_abc123\n", encoding="utf-8")
    monkeypatch.setattr(monitor, "GLAMA_KEY_FILE", str(secret))
    monkeypatch.delenv("GLAMA_API_KEY", raising=False)
    assert monitor.glama_key() == "glm_abc123"


def test_glama_key_absent_returns_none(monitor, monkeypatch, tmp_path):
    monkeypatch.setattr(monitor, "GLAMA_KEY_FILE", str(tmp_path / "missing.txt"))
    monkeypatch.delenv("GLAMA_API_KEY", raising=False)
    assert monitor.glama_key() is None


def test_key_file_lives_in_gitignored_secrets(monitor):
    """Key hygiene as a test: Desktop files are temporary, secrets/ is ignored."""
    assert monitor.GLAMA_KEY_FILE.replace("\\", "/").endswith(
        "secrets/glama_api_key.txt")
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "secrets/" in ignored


# ── state parsing ──────────────────────────────────────────────────────────

def test_fetch_glama_state_parses_both_listings(monitor, monkeypatch):
    monkeypatch.setattr(monitor, "_glama_get", _fake_get({
        f"/v1/servers/{monitor.GLAMA_SERVERS}": SERVER_PAYLOAD,
        f"/v1/connectors/{monitor.GLAMA_CONNECTOR}": CONNECTOR_PAYLOAD,
    }))
    state = monitor.fetch_glama_state("k")

    assert state["servers"] == {
        "quality_score": None, "spdx_license": None, "tools": 0,
        "attributes": ["hosting:remote-capable"], "boosted": False}
    assert state["connector"]["healthy"] is True
    assert state["connector"]["quality_score"] == 4.7
    assert state["connector"]["tool_count"] == 3
    assert state["connector"]["transport"] == "streamable_http"
    assert state["connector"]["last_tested_at"].startswith("2026-09-22")


def test_fetch_glama_state_counts_servers_tools(monitor, monkeypatch):
    payload = dict(SERVER_PAYLOAD, tools=[{"name": "a"}, {"name": "b"}])
    monkeypatch.setattr(monitor, "_glama_get", _fake_get({
        f"/v1/servers/{monitor.GLAMA_SERVERS}": payload}))
    state = monitor.fetch_glama_state("k")
    assert state["servers"]["tools"] == 2


def test_fetch_glama_state_positions(monitor, monkeypatch):
    ours = {"namespace": "hristovdimitri2-hub", "slug": "kristo-intelligence-6"}
    defi = {"servers": [{"namespace": "someone", "slug": "other"}, ours]}
    signals = {"servers": [{"namespace": "someone", "slug": "other"}]}

    def fake(path, key, params=None):
        if params and params.get("query") == "defi":
            return defi
        if params and params.get("query") == "signals":
            return signals
        return None

    monkeypatch.setattr(monitor, "_glama_get", fake)
    state = monitor.fetch_glama_state("k")
    assert state["positions"]["defi"] == {"position": 2, "shown": 2}
    assert state["positions"]["signals"] == {"position": None, "shown": 1}


def test_fetch_glama_state_survives_an_unreachable_api(monitor, monkeypatch):
    monkeypatch.setattr(monitor, "_glama_get", lambda *a, **k: None)
    state = monitor.fetch_glama_state("k")
    assert state["servers"]["tools"] == 0
    assert state["connector"]["healthy"] is None
    assert state["positions"]["defi"]["position"] is None


# ── diffing ────────────────────────────────────────────────────────────────

def test_diff_glama_silent_when_nothing_moved(monitor, monkeypatch):
    monkeypatch.setattr(monitor, "_glama_get", _fake_get({
        f"/v1/servers/{monitor.GLAMA_SERVERS}": SERVER_PAYLOAD,
        f"/v1/connectors/{monitor.GLAMA_CONNECTOR}": CONNECTOR_PAYLOAD,
    }))
    state = monitor.fetch_glama_state("k")
    assert monitor.diff_glama(state, state) == []


def test_diff_glama_alarms_on_score_and_health_change(monitor, monkeypatch):
    monkeypatch.setattr(monitor, "_glama_get", _fake_get({
        f"/v1/servers/{monitor.GLAMA_SERVERS}": SERVER_PAYLOAD,
        f"/v1/connectors/{monitor.GLAMA_CONNECTOR}": CONNECTOR_PAYLOAD,
    }))
    prev = monitor.fetch_glama_state("k")
    cur = monitor.fetch_glama_state("k")
    cur["servers"]["quality_score"] = 4.2
    cur["servers"]["spdx_license"] = "MIT"
    cur["servers"]["tools"] = 3
    cur["connector"]["healthy"] = False
    cur["connector"]["tool_count"] = 2

    joined = " | ".join(monitor.diff_glama(prev, cur))
    assert "GLAMA servers quality_score: None -> 4.2" in joined
    assert "GLAMA servers spdx_license: None -> MIT" in joined
    assert "GLAMA servers tools: 0 -> 3" in joined
    assert "GLAMA connector healthy: True -> False" in joined
    assert "GLAMA connector tool_count: 3 -> 2" in joined


def test_diff_glama_alarms_on_rank_change(monitor, monkeypatch):
    ours = {"namespace": "hristovdimitri2-hub", "slug": "kristo-intelligence-6"}
    monkeypatch.setattr(monitor, "_glama_get",
                        _fake_get({"/v1/servers": {"servers": [ours]}}))
    prev = monitor.fetch_glama_state("k")
    monkeypatch.setattr(monitor, "_glama_get",
                        _fake_get({"/v1/servers": {"servers": [{"x": 1}, ours]}}))
    cur = monitor.fetch_glama_state("k")

    changes = monitor.diff_glama(prev, cur)
    assert any("GLAMA rank q=defi: 1 -> 2" in c for c in changes)
    assert any("GLAMA rank q=signals: 1 -> 2" in c for c in changes)


def test_diff_glama_without_a_key_on_this_run_does_not_alarm(monitor, monkeypatch):
    """Key removed between runs → no glama block in `cur` → no false alarms."""
    monkeypatch.setattr(monitor, "_glama_get", _fake_get({
        f"/v1/servers/{monitor.GLAMA_SERVERS}": SERVER_PAYLOAD,
        f"/v1/connectors/{monitor.GLAMA_CONNECTOR}": CONNECTOR_PAYLOAD,
    }))
    prev = monitor.fetch_glama_state("k")
    assert monitor.diff_glama(prev, {}) == []


def test_glama_terms_and_base_are_pinned(monitor):
    assert monitor.GLAMA_TERMS == ["defi", "signals"]
    assert monitor.GLAMA_BASE == "https://glama.ai/api/mcp"