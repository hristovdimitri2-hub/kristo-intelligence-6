"""No step of the payment rail may hold a worker indefinitely.

THE OUTAGE THIS PREVENTS, measured 08.11.2026. A request carrying a VALID payment
signature never completed. gunicorn runs with `--timeout 120`, so at 120 seconds
it KILLED the worker — taking every other request in flight with it. The log
filled with

    Background threads started (blockchain monitor + agent + ...)

lines, which are workers respawning, including a forty-minute stretch where the
service served no HTTP at all while its threads kept ticking.

`_local_recover_signer` is pure EIP-712 cryptography that costs 0.000s locally, and
it is where the trail stopped every time. The line that would have named the next
step died with the killed worker — which is why a deadline is also a DIAGNOSIS:
control returns to the living process, which logs the overrun itself.

THE TRADE, stated because it is deliberate: the overrunning thread is abandoned
(daemon, left running) rather than waited for. One leaked thread costs a thread;
waiting costs the worker and every request queued behind it. That is the same
trade `_run` already makes with its bounded lock wait — a stalled holder costs one
fast error rather than the process.
"""

import threading
import time

import main


# ── the helper's contract ───────────────────────────────────────────────────

def test_a_fast_call_passes_its_result_through():
    finished, result, error = main._bounded("probe", lambda: "VALUE", 2)
    assert finished is True
    assert result == "VALUE"
    assert error is None


def test_a_slow_call_is_refused_and_the_caller_is_released():
    """THE property. The caller must get control back, not wait."""
    started = time.monotonic()
    finished, result, error = main._bounded(
        "probe", lambda: time.sleep(30), 0.5)
    elapsed = time.monotonic() - started
    assert finished is False, "a slow step was reported as finished"
    assert result is None and error is None
    assert elapsed < 3, (
        "the caller waited %.1fs for a step bounded at 0.5s" % elapsed)


def test_a_raising_step_is_reported_not_swallowed():
    """A step that throws must not look like a step that passed."""
    def boom():
        raise ValueError("nope")

    finished, result, error = main._bounded("probe", boom, 2)
    assert finished is True          # it DID finish
    assert result is None
    assert isinstance(error, ValueError)


def test_an_unfinished_step_is_never_reported_as_passed():
    """The dangerous confusion: `finished=False` must not be read as success.

    Callers pattern-match on the trio, and a helper that returned (True, None,
    None) on timeout would make every caller silently approve a payment it never
    verified.
    """
    finished, result, error = main._bounded("probe", lambda: time.sleep(30), 0.3)
    assert finished is not True
    assert not (finished and result)      # cannot be read as a pass


def test_the_default_deadline_is_below_the_gunicorn_timeout():
    """The bound only helps if it fires before gunicorn kills the worker.

    gunicorn is started with `--timeout 120`. A step bound at or above that would
    never fire first, and the worker would still die.
    """
    assert main.X402_STEP_DEADLINE_SECONDS < 120, (
        "a %.0fs step deadline is at or above gunicorn's 120s timeout"
        % main.X402_STEP_DEADLINE_SECONDS)
    assert main.X402_STEP_DEADLINE_SECONDS >= 5, (
        "a deadline below 5s would refuse honest payments on a slow chain")


def test_an_abandoned_thread_does_not_stop_the_next_call():
    """One stuck payment must not poison the rail for the next one."""
    main._bounded("probe", lambda: time.sleep(30), 0.2)
    finished, result, error = main._bounded("probe2", lambda: "ALIVE", 2)
    assert finished is True and result == "ALIVE"


# ── the rail actually uses it ───────────────────────────────────────────────

def test_both_rail_steps_are_bounded():
    """THE regression guard: verify and settle must go through `_bounded`.

    Matched on whitespace flexibly. The first version of this test hard-coded
    eight spaces of indentation, found `verify` (8) and missed `settle` (12), and
    reported a real property as violated — a false alarm is its own kind of
    expensive, because it teaches people to distrust the guard.
    """
    import re
    from pathlib import Path as _P

    src = (_P(__file__).resolve().parent.parent / "main.py").read_text(
        encoding="utf-8")
    for step in ("verify_standard_payment", "settle_standard_payment"):
        assert re.search(r'_bounded\(\s*"%s"' % step, src), (
            "%s is not wrapped in _bounded — an unbounded step here gets the "
            "worker killed and takes every other request with it" % step)


def test_the_worker_is_released_even_when_verify_hangs(monkeypatch):
    """END TO END, and this is the outage in miniature.

    Make verification hang exactly as it did in production and call the rail
    itself, then assert it RETURNS — refusing with a reason — instead of holding
    until gunicorn kills the worker.

    IT CALLS THE RAIL DIRECTLY, deliberately. The first version sent a request to
    `/api/v1/signal` and got 200: a test client starts with a fresh free-tier
    counter, so the call was free and never reached the payment path at all. It
    proved nothing about the deadline while looking like it did.
    """
    from services import connectors

    monkeypatch.setattr(main, "X402_STEP_DEADLINE_SECONDS", 0.4)

    def hang(*_a, **_k):
        time.sleep(30)

    monkeypatch.setattr(connectors, "verify_standard_payment", hang)

    with main.app.test_request_context(
            "/api/v1/signal", headers={"PAYMENT-SIGNATURE": "not-a-payload"}):
        started = time.monotonic()
        result = main._try_consume_standard_payment("/api/v1/signal", 0.003, "1.2.3.4")
        elapsed = time.monotonic() - started

    assert result is False, "a payment that never verified was treated as paid"
    assert elapsed < 10, (
        "the rail held for %.1fs against a 0.4s step deadline — this is the "
        "call that used to get the worker killed" % elapsed)
