"""Sentinel must be SILENT at boot — the channel speaks only on CHANGE.

Variant B (27.09): the startup announcement ("Kristo Sentinel активен…") and
its daily gate were removed from services/sentinel.py. This test boots the
real sentinel_loop with a fully fresh (post-deploy) state, with Telegram fully
configured, and asserts that zero messages are sent during startup.
"""
from __future__ import annotations

import pytest

from services import sentinel


class _BootCompleted(Exception):
    """Raised instead of sleeping, to exit the infinite loop."""


def test_no_message_at_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[str] = []

    # The channel IS configured — if any boot-announce code survived, it would send.
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "-100123")

    monkeypatch.setattr(sentinel, "_tg_send",
                        lambda text: sent.append(text) or True)
    # Baseline checks are network I/O — irrelevant for this assertion.
    monkeypatch.setattr(sentinel, "_check_health", lambda state: None)
    monkeypatch.setattr(sentinel, "_check_revenue", lambda state: None)
    monkeypatch.setattr(sentinel, "_check_github", lambda state: None)
    # The weekly report must never fire here, whatever weekday/hour the test runs.
    monkeypatch.setattr(sentinel, "REPORT_WEEKDAY", -1)
    # Fresh persisted state = the exact situation right after a deploy.
    monkeypatch.setattr(sentinel, "_load_persisted", lambda: {}, raising=False)

    def _exit_after_first_cycle(_secs: float) -> None:
        raise _BootCompleted()

    monkeypatch.setattr(sentinel.time, "sleep", _exit_after_first_cycle)

    with pytest.raises(_BootCompleted):
        sentinel.sentinel_loop()

    assert sent == [], f"boot must be silent, but sent: {sent}"