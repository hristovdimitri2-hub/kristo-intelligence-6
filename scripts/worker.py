"""
Kristo Intelligence 6 — Standalone Background Worker
====================================================

Runs all background loops in a dedicated process, separate from the Flask
web server. This is the production-recommended deployment pattern:

  ┌─────────────────────┐         ┌─────────────────────┐
  │   web (gunicorn)    │         │   worker (python)   │
  │   HTTP only         │         │   Background only   │
  │   KRISTO_DISABLE_   │         │   KRISTO_WORKER_    │
  │   BACKGROUND_THREADS│         │   MODE=true         │
  │   =true             │         │                     │
  └─────────────────────┘         └─────────────────────┘
              ↑                              ↑
              └──────── Postgres ────────────┘
                    (shared state)

Usage:
    python -m scripts.worker

Environment:
    DATABASE_URL              — PostgreSQL URL (shared with web)
    KRISTO_WORKER_MODE=true   — marker (set automatically by docker-compose)
    KRISTO_DISABLE_BACKGROUND_THREADS — ignored in worker mode (always False)

Loops started:
    1. blockchain-monitor  — watches incoming USDC transfers on Base
    2. agent-loop          — periodic trading agent evaluation
    3. catalog-analytics   — daily 24h metrics refresh
    4. stripe-snapshot     — periodic Stripe payment snapshot refresh
    5. telegram-sales      — periodic market bulletins (if TELEGRAM_BOT_TOKEN set)

All loops are daemon threads; the main process stays alive waiting on them.
On SIGTERM/SIGINT, loops stop gracefully (they check a shared stop event).
"""
from __future__ import annotations

import logging
import signal
import sys
import threading
import time

# ── Configure logging ──────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("kristo.v6.worker")

# ── Set worker-mode env BEFORE importing main (so main knows its role) ────
import os
os.environ["KRISTO_WORKER_MODE"] = "true"
os.environ["KRISTO_DISABLE_BACKGROUND_THREADS"] = "false"  # worker runs them
# Force web-mode flag off — we are NOT the web server
os.environ.pop("KRISTO_DISABLE_BACKGROUND_THREADS", None)

# ── Import the application (this initializes stores, wallet, etc.) ─────────
import main  # noqa: E402

# ── Shared stop event for graceful shutdown ────────────────────────────────
STOP_EVENT = threading.Event()


def _handle_signal(signum, _frame):
    """Graceful shutdown on SIGTERM/SIGINT."""
    sig_name = signal.Signals(signum).name
    log.info("Received %s — initiating graceful shutdown...", sig_name)
    STOP_EVENT.set()


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)


def main_loop():
    """Start background threads and wait for shutdown signal."""
    log.info("Kristo Intelligence 6 — Background Worker starting")
    log.info("PID: %d, threads will be daemons", os.getpid())

    # Start the same background threads that web mode would start
    # (main._start_background_threads already checks for worker mode and
    # runs unconditionally when KRISTO_WORKER_MODE=true)
    main._start_background_threads()

    log.info("All background loops started. Worker is now idle (waiting for SIGTERM).")
    log.info("Press Ctrl+C to stop.")

    # Block main thread until stop event is set
    while not STOP_EVENT.is_set():
        time.sleep(1)

    log.info("Shutdown complete. Exiting.")
    return 0


if __name__ == "__main__":
    sys.exit(main_loop())
