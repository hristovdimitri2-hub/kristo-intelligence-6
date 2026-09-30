"""Root guard regression: a duplicate module-level load of main.py must
NOT start a second set of background threads.

Defect documented 30.09: a lazy `import main` (sentinel._dashboard_store,
telegram_sales handlers, discovery routes) re-executed main.py inside the
running process — a fresh Flask app reset `app._bg_started`, so every loop
started twice on every boot since 27.09 (duplicate revenue checks, duplicate
Telegram alerts, double blockchain-monitor settle attempts).
"""

import os
from types import SimpleNamespace


def test_duplicate_module_load_skips_all_threads(monkeypatch):
    import main

    started = []
    registered = {"webhook": 0, "commands": 0}

    class FakeThread:
        """Records thread starts without ever running the target."""

        def __init__(self, target=None, daemon=None, name=None, **kwargs):
            self.name = name or "thread"
            self.target = target

        def start(self):
            started.append(self.name)

    # `threading.Thread` inside _start_background_threads must resolve via
    # main's module globals — swap only that binding, never the stdlib.
    monkeypatch.setattr(main, "threading", SimpleNamespace(Thread=FakeThread))
    monkeypatch.setattr(
        main,
        "register_webhook",
        lambda: registered.__setitem__("webhook", registered["webhook"] + 1),
    )
    monkeypatch.setattr(
        main,
        "register_bot_commands",
        lambda: registered.__setitem__("commands", registered["commands"] + 1),
    )

    from services import arb_radar, sentinel

    monkeypatch.setattr(arb_radar, "start_arb_radar_thread", lambda: None)
    monkeypatch.setattr(sentinel, "start_sentinel_thread", lambda: None)

    # Full-start path: no disable flag, guard flag empty (fresh process).
    monkeypatch.delenv("KRISTO_DISABLE_BACKGROUND_THREADS", raising=False)
    monkeypatch.setenv("KRISTO_BG_THREADS_STARTED", "")

    # Fresh module state, as after a lazy `import main` re-execution.
    monkeypatch.setattr(main.app, "_bg_started", False, raising=False)

    main._start_background_threads()
    first_run = list(started)
    # monitor + agent + catalog + stripe-snapshot + dashboard + whaleflow
    # + keep-alive + telegram-sales = 8 threads.
    assert len(first_run) == 8, first_run
    assert registered["webhook"] == 1
    assert registered["commands"] == 1
    # Set only because threads actually started.
    assert os.environ["KRISTO_BG_THREADS_STARTED"] == "1"

    # Second invocation with a FRESH Flask app (the module state a
    # re-executed main.py would carry) — the process-wide env guard must
    # skip the entire second thread set and the re-registrations.
    monkeypatch.setattr(main.app, "_bg_started", False, raising=False)
    main._start_background_threads()

    assert started == first_run
    assert registered["webhook"] == 1
    assert registered["commands"] == 1
