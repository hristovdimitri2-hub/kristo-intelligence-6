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
    # monitor + agent + catalog + stripe-snapshot + dashboard + dashboard-warmer
    # + requests-snapshot-warmer + memory-watch + whaleflow + keep-alive
    # + telegram-sales + organism-boot
    # + request-log-retention + reorg-watch
    # = 14 threads.
    #
    # `memory-watch` was added when the Render 512 MB OOM was being chased; it
    # is a diagnostic thread, so it is a real thread and must be counted. The
    # count below was stale at 13 and the test failed on the first full run
    # after the thread landed — the assertion is what keeps the guard honest.
    #
    # The last two moved here from MODULE level on 08.11.2026. Both call
    # `_isolated_store`, defined ~1,400 lines below where they were started, so
    # the thread could run before Python had created the name:
    #
    #     Request-log retention failed (non-fatal): name '_isolated_store' is
    #     not defined
    #
    # Retention is what keeps `request_log` bounded — the fix for the 07.11 OOM —
    # and reorg detection is what notices a chain reorganisation invalidating a
    # recorded sale. Both raised NameError, both were swallowed by their own
    # `except`, and both reported themselves as non-fatal while being dead.
    #
    # `organism-boot` writes the organism's opening heartbeat. It runs in its OWN
    # thread on purpose: the write is a Postgres round-trip, and this runs at
    # import time BEFORE gunicorn binds the port. A durable write on that path
    # already cost this project one deploy (module-level purge_old_requests in
    # a4c1cb0), so boot must not wait on telemetry.
    assert len(first_run) == 14, first_run
    assert "organism-boot" in first_run, (
        "the organism's boot heartbeat must be on its own thread, not on the "
        "path to binding the port")
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
