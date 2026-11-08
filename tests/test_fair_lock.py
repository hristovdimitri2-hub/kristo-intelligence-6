"""The shared-link lock must be FAIR, and the scan loop must not share the link.

WHY A FAIR LOCK, stated with the measurement rather than the theory.

`threading.Lock` is not fair: on release any waiter may win, and a background job
that re-acquires in a tight loop can win repeatedly. It does NOT starve anyone
permanently — a hog thread plus eight waiters delivered 8/8 on BOTH locks, every
run, and the first version of this file's subject claimed otherwise. What it costs
is LATENCY, because a waiter can lose the race again and again:

    holder holds 20ms, 8 waiters, worst observed wait
        threading.Lock   0.234s
        FairLock         0.015s

That matters because the wait is BOUNDED. `_run` refuses after
`KRISTO_PG_LOCK_WAIT_SECONDS`, so a caller that keeps losing the race does not
merely wait — it FAILS. Measured live on 08.11, `/health` answered in 2.3-2.7s,
which is the full timeout: it was being refused, and it looked healthy only
because it falls back to process memory.
"""

import threading
import time

from integrations.dashboard_store import FairLock

WAITERS = 8
HOLD_SECONDS = 0.02
#: Generous. The measured value is ~0.015s; anything near the 2s production
#: timeout means the queue is not working.
BOUND_SECONDS = 0.5


def _contend(lock, waiters=WAITERS, hold=HOLD_SECONDS, timeout=3.0):
    """Run `waiters` against a holder that re-acquires in a tight loop.

    Returns the waits, in the order they were granted.
    """
    served = []
    guard = threading.Lock()
    stop = threading.Event()

    def hog():
        while not stop.is_set():
            if lock.acquire(1.0):
                time.sleep(hold)
                lock.release()

    hog_thread = threading.Thread(target=hog, daemon=True)
    hog_thread.start()
    time.sleep(0.05)

    def waiter():
        t0 = time.monotonic()
        if lock.acquire(timeout):
            with guard:
                served.append(round(time.monotonic() - t0, 4))
            lock.release()

    threads = [threading.Thread(target=waiter) for _ in range(waiters)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    stop.set()
    hog_thread.join(timeout=2)
    return served


# ── correctness ─────────────────────────────────────────────────────────────

def test_it_is_a_real_mutual_exclusion_lock():
    """A lock that lets two threads in is worse than an unfair one."""
    lock = FairLock()
    inside = []
    errors = []

    def worker(n):
        for _ in range(50):
            if not lock.acquire(2.0):
                errors.append("acquire timed out")
                return
            inside.append(n)
            if inside[-1] != n:
                errors.append("two holders at once: %r" % inside)
            time.sleep(0.0005)
            inside.pop()
            lock.release()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors


def test_it_grants_without_a_timeout_when_uncontended():
    lock = FairLock()
    assert lock.acquire() is True
    lock.release()


def test_every_waiter_is_served_within_a_bounded_wait():
    """THE property. A bounded waiter must not lose the race until it expires."""
    served = _contend(FairLock())
    assert len(served) == WAITERS, (
        "only %d/%d waiters were served" % (len(served), WAITERS))
    worst = max(served)
    assert worst < BOUND_SECONDS, (
        "worst wait was %.3fs against a %.1fs bound; the queue is not FIFO"
        % (worst, BOUND_SECONDS))


def test_the_wait_stays_well_under_the_production_bound_under_contention():
    """THE RELIABLE HALF of the fairness claim, asserted; the rest is recorded.

    What the lock PROMISES is a bound: a waiter is served, and not after an
    unbounded wait. That is deterministic enough to assert.

    What it does NOT promise per-run is that it beats `threading.Lock` on a given
    afternoon. An earlier version of this file asserted exactly that, twice, and
    failed intermittently on a machine also running the full suite — the code was
    correct every time. The measurement that justifies the class is therefore kept
    here as a recorded fact rather than a flaky assertion:

        holder holds 20ms, 8 waiters, worst observed wait
            threading.Lock   0.234s
            FairLock         0.015s

    That gap is why the class exists: `_run` refuses after
    `KRISTO_PG_LOCK_WAIT_SECONDS`, so a caller that keeps losing the race does not
    merely wait, it FAILS. Measured live, `/health` answered in 2.3-2.7s — the
    full timeout — while looking healthy, because it falls back to process memory.
    """
    served = _contend(FairLock(), waiters=8, hold=0.02, timeout=3.0)
    assert len(served) == 8, "not every waiter was served: %d/8" % len(served)
    worst = max(served)
    assert worst < BOUND_SECONDS, (
        "worst wait %.3fs exceeded the %.1fs bound; the queue is not bounded"
        % (worst, BOUND_SECONDS))


# ── the abandonment path, which is the dangerous one ────────────────────────

def test_a_timed_out_waiter_never_wedges_the_queue():
    """A caller that gives up must not block everyone behind it.

    This is the failure mode a ticket lock introduces if it is written naively:
    the abandoned ticket is never released, so `_now_serving` can never reach the
    later tickets and the lock is dead for the life of the process.
    """
    lock = FairLock()
    hog_stop = threading.Event()

    def hog():
        while not hog_stop.is_set():
            if lock.acquire(1.0):
                time.sleep(0.05)
                lock.release()

    hog_thread = threading.Thread(target=hog, daemon=True)
    hog_thread.start()
    time.sleep(0.05)

    # A waiter that gives up almost immediately. It may legitimately WIN — the
    # holder is between statements for part of every cycle — and a winner must
    # release. An earlier version of this test ignored that and wedged the lock
    # itself, then reported the lock as broken.
    if lock.acquire(timeout=0.01):
        lock.release()

    # Now a patient one must still get in.
    got = lock.acquire(timeout=3.0)
    hog_stop.set()
    hog_thread.join(timeout=2)
    if got:
        lock.release()
    assert got, "the abandoned ticket wedged the queue"


def test_many_abandoned_tickets_do_not_wedge_the_queue():
    lock = FairLock()
    stop = threading.Event()

    def hog():
        while not stop.is_set():
            if lock.acquire(1.0):
                time.sleep(0.01)
                lock.release()

    h = threading.Thread(target=hog, daemon=True)
    h.start()
    time.sleep(0.05)
    for _ in range(20):
        if lock.acquire(timeout=0.001):
            lock.release()
    got = lock.acquire(timeout=3.0)
    stop.set()
    h.join(timeout=2)
    if got:
        lock.release()
    assert got, "20 abandoned tickets wedged the queue"


def test_the_queue_drains_once_the_contention_stops():
    lock = FairLock()
    served = _contend(lock)
    assert len(served) == WAITERS
    # And afterwards it behaves like an uncontended lock.
    assert lock.acquire(1.0) is True
    lock.release()


# ── the scan loop must not share the link either ────────────────────────────

def test_the_dashboard_scan_loop_uses_its_own_store():
    """THE regression guard for the fourth holder.

    The loop probes the replay lock, scans the chain for sales, and refreshes a
    listing state (a network call) every 60 seconds. Through the shared link the
    log named it:

        shared Postgres link busy for 2s; holder=dashboard-scan held=200s
    """
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent
           / "main.py").read_text(encoding="utf-8")
    assert 'scan_db = _isolated_store("dashboard-scan")' in src
    assert "scan_db.probe_replay_lock()" in src
    assert "scan_db.scan_increment()" in src
    assert "scan_db.save_payapi_state(" in src
    # And the durable reads that WERE on the shared link are gone.
    assert "dashboard_db.probe_replay_lock()" not in src
    assert "dashboard_db.scan_increment()" not in src
