"""Sentinel PR watcher hardening (27.09).

1. Baseline of PR statuses is DURABLE (pr_watch_state, like payment_guards);
   a missing baseline = record WITHOUT a message (incl. a brand-new PR).
2. With a recorded baseline, open → merged/closed alerts — including after a
   restart (fresh in-memory state, same durable row).
3. clean → dirty (CONFLICTING/DIRTY) sends one "PR има конфликт" per
   transition, not one per cycle.
4. "New payment received" alerts route to TELEGRAM_VIP_CHAT_ID when set;
   missing env = today's behaviour (the public channel). PR statuses and
   bulletins are untouched — they stay in the channel.
"""
from __future__ import annotations

import pytest


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """A REAL DashboardStore over a temp SQLite file (DATABASE_URL off)."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from integrations.dashboard_store import DashboardStore
    return DashboardStore(tmp_path / "pr_watch.db")


@pytest.fixture()
def sent(monkeypatch):
    """Record every Telegram send as (text, chat_id)."""
    from services import sentinel
    out: list[tuple[str, str]] = []
    monkeypatch.setattr(sentinel, "_tg_send",
                        lambda text, chat_id="": out.append((text, chat_id)) or True)
    return out


def _fake_github(monkeypatch, *, merged=False, state="open",
                 mergeable_state="clean"):
    from services import sentinel

    class _R:
        def __init__(self, payload):
            self._p = payload

        def json(self):
            return self._p

    def fake_get(url, **kwargs):
        if "/pulls/" in url:
            return _R({"merged": merged, "state": state,
                       "mergeable_state": mergeable_state})
        return _R({"stargazers_count": 0, "open_issues_count": 0,
                   "forks_count": 0})

    monkeypatch.setattr(sentinel.requests, "get", fake_get)


def _watch(monkeypatch, store):
    from services import sentinel
    monkeypatch.setattr(sentinel, "_dashboard_store", lambda: store)
    monkeypatch.setattr(sentinel, "WATCHED_PRS", [("acme/widgets", 7)])


# ── 1. missing baseline → record, no message ────────────────────────────────
def test_missing_baseline_records_without_a_message(store, sent, monkeypatch):
    """First sight of a PR (even one already merged) must be SILENT."""
    from services import sentinel
    _watch(monkeypatch, store)
    _fake_github(monkeypatch, merged=True, state="closed")

    sentinel._check_github({})               # no baseline anywhere

    assert sent == []                        # …and no message invented
    row = store.get_pr_watch_state("acme/widgets#7")
    assert row is not None                   # but durably recorded
    assert row["status"] == "merged"


# ── 2. open → merged alerts, even across a restart ──────────────────────────
def test_open_to_merged_alerts_once_after_restart(store, sent, monkeypatch):
    from services import sentinel
    store.set_pr_watch_state("acme/widgets#7", "open", "clean")
    _watch(monkeypatch, store)
    _fake_github(monkeypatch, merged=True, state="closed")

    sentinel._check_github({})               # fresh in-memory state = restart

    assert len(sent) == 1
    assert "🎉" in sent[0][0]
    assert "merged" in sent[0][0]
    assert "acme/widgets#7" in sent[0][0]
    assert store.get_pr_watch_state("acme/widgets#7")["status"] == "merged"

    sentinel._check_github({})               # same state again → no repeat
    assert len(sent) == 1


# ── 3. clean → dirty: one conflict message per transition ───────────────────
def test_conflict_transition_alerts_exactly_once(store, sent, monkeypatch):
    from services import sentinel
    store.set_pr_watch_state("acme/widgets#7", "open", "clean")
    _watch(monkeypatch, store)
    _fake_github(monkeypatch, mergeable_state="dirty")

    sentinel._check_github({})               # clean → dirty: ONE message

    assert len(sent) == 1
    assert "⚠️" in sent[0][0]
    assert "конфликт" in sent[0][0]

    sentinel._check_github({})               # still dirty → silence
    assert len(sent) == 1
    assert store.get_pr_watch_state("acme/widgets#7")["mergeable_state"] == "dirty"


# ── 4. payment alerts → the private chat when configured ────────────────────
def _revenue_round(monkeypatch, tmp_path, first, second):
    from services import sentinel
    monkeypatch.setattr(sentinel, "STATE_FILE", str(tmp_path / "sentinel.json"))
    balances = iter([first, second])
    monkeypatch.setattr(
        sentinel.requests, "post",
        lambda url, json=None, timeout=30: type("R", (), {
            "json": lambda self: {"result": hex(int(next(balances)))}
        })(),
    )
    state = {"usdc_balance": 0.0}
    sentinel._check_revenue(state)           # baseline — silent
    sentinel._check_revenue(state)           # increase — one alert
    return state


def test_payment_alert_goes_to_the_vip_chat(store, sent, monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_VIP_CHAT_ID", "-10077")
    _revenue_round(monkeypatch, tmp_path, "0", "50000")

    assert len(sent) == 1
    assert "💰" in sent[0][0]
    assert sent[0][1] == "-10077"            # the PRIVATE chat


def test_payment_alert_falls_back_to_the_channel(store, sent, monkeypatch, tmp_path):
    monkeypatch.delenv("TELEGRAM_VIP_CHAT_ID", raising=False)
    _revenue_round(monkeypatch, tmp_path, "0", "50000")

    assert len(sent) == 1
    assert sent[0][1] == ""                  # empty → _tg_send resolves the channel


# ── 5. conflict watch is open-only; "unknown" never overwrites ──────────────
def test_conflict_alert_skipped_for_non_open_pr(store, sent, monkeypatch):
    """A closed PR going dirty gets the status change, NOT the conflict alarm."""
    from services import sentinel
    store.set_pr_watch_state("acme/widgets#7", "open", "clean")
    _watch(monkeypatch, store)
    _fake_github(monkeypatch, state="closed", mergeable_state="dirty")

    sentinel._check_github({})

    assert len(sent) == 1                     # only open → closed
    assert "ℹ️" in sent[0][0] and "closed" in sent[0][0]
    assert not any("⚠️" in text for text, _ in sent)


def test_unknown_mergeable_never_overwrites_the_baseline(store, sent, monkeypatch):
    """mergeable_state=unknown is information-free: baseline stays put,
    and the real transition is still detected once GitHub settles."""
    from services import sentinel
    store.set_pr_watch_state("acme/widgets#7", "open", "clean")
    _watch(monkeypatch, store)

    _fake_github(monkeypatch, mergeable_state="unknown")
    sentinel._check_github({})
    assert sent == []
    assert store.get_pr_watch_state("acme/widgets#7")["mergeable_state"] == "clean"

    _fake_github(monkeypatch, mergeable_state="dirty")   # clean → dirty: alert
    sentinel._check_github({})
    assert len(sent) == 1 and "⚠️" in sent[0][0]

    _fake_github(monkeypatch, mergeable_state="unknown")  # unknown must not reset
    sentinel._check_github({})
    assert store.get_pr_watch_state("acme/widgets#7")["mergeable_state"] == "dirty"
    assert len(sent) == 1