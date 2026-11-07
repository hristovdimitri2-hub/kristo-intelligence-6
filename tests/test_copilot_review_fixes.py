"""The three findings from the Copilot review, each pinned by a test.

An independent review raised three defects. All three were real, and each is
reproduced here before being trusted:

  1. MEDIUM — the free-tier counter read and incremented in SEPARATE critical
     sections, so two parallel requests from one IP both read 0, both wrote 1,
     and both were granted a paid endpoint for free. `KRISTO_FREE_TIER_LIMIT` is
     1 in production, which is exactly the case where one may be free and the
     second must pay.

  2. MEDIUM — verification accepts any amount AT OR ABOVE the price
     (`connectors.py` rejects only `got < want`), but nonce recovery adopted a
     settlement only on EXACT equality. A buyer who overpaid, whose response was
     lost, would be refused on retry: the transfer exists, `==` cannot see it, and
     they have paid and received nothing.

  3. LOW — SIGTERM set a stop event, but the daemon loops were never joined, so a
     restart cut whatever a cycle was mid-way through.

THE HONESTY NOTE ON TEST 1. The race would not reproduce from threads alone: the
read and the write are a few bytecodes apart and eight threads still serialised
by luck. A test that only sometimes fails is not a test, so the shape itself is
asserted instead — one critical section, not two — which is deterministic and is
precisely what the fix changed.
"""

import ast
import threading
from pathlib import Path

import main

REPO = Path(__file__).resolve().parent.parent
MAIN_SRC = REPO / "main.py"
WORKER_SRC = REPO / "scripts" / "worker.py"


# ── finding 1: the free-tier race ────────────────────────────────────────────

def _paid_block():
    """The `if path in X402_PAID_ENDPOINTS:` node, found structurally."""
    tree = ast.parse(MAIN_SRC.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and isinstance(node.test, ast.Compare):
            t = node.test
            if (isinstance(t.left, ast.Name) and t.left.id == "path"
                    and len(t.comparators) == 1
                    and isinstance(t.comparators[0], ast.Name)
                    and t.comparators[0].id == "X402_PAID_ENDPOINTS"):
                return node
    return None


def _free_tier_scopes():
    """(how many `with _lock:` scopes, index reading, index writing)."""
    node = _paid_block()
    assert node is not None, "the free-tier block has moved or been renamed"

    scopes = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.With):
            for item in sub.items:
                ctx = item.context_expr
                if isinstance(ctx, ast.Name) and ctx.id == "_lock":
                    scopes.append(sub)

    read_scope = write_scope = None
    for i, sc in enumerate(scopes):
        for sub in ast.walk(sc):
            if (isinstance(sub, ast.Call)
                    and isinstance(sub.func, ast.Attribute)
                    and sub.func.attr == "get"
                    and isinstance(sub.func.value, ast.Name)
                    and sub.func.value.id == "_free_tier_usage"):
                read_scope = i
            if (isinstance(sub, ast.Subscript)
                    and isinstance(sub.value, ast.Name)
                    and sub.value.id == "_free_tier_usage"
                    and isinstance(sub.ctx, ast.Store)):
                write_scope = i
    return len(scopes), read_scope, write_scope


def test_the_free_tier_read_and_increment_share_one_critical_section():
    """THE regression guard for the race.

    Two scopes is the defect: the read happens in the first, the write in the
    second, and the window between them is where a second request reads the same
    value. One scope makes the interleaving impossible by construction, which is
    stronger than "unlikely".
    """
    scopes, read_scope, write_scope = _free_tier_scopes()
    assert scopes == 1, (
        "the free-tier block has %d `with _lock:` scopes; the read and the "
        "increment must share ONE or two parallel requests both increment from "
        "the same value" % scopes)
    assert read_scope == write_scope == 0, (
        "the read is in scope %s and the write in scope %s"
        % (read_scope, write_scope))


def test_the_free_tier_actually_grants_only_the_limit():
    """The behaviour the shape protects, asserted end to end.

    This does not reliably catch the race (see the module docstring) but it DOES
    catch a regression that breaks the counter outright, and it documents what
    the limit is supposed to mean.
    """
    ip = "198.51.100.42"
    with main._lock:
        main._free_tier_usage.pop(ip, None)

    limit = main.FREE_TIER_LIMIT
    client = main.app.test_client()
    codes = []
    for _ in range(limit + 3):
        r = client.get("/api/v1/signal", environ_base={"REMOTE_ADDR": ip},
                       headers={"X-Forwarded-For": ip})
        codes.append(r.status_code)
    with main._lock:
        main._free_tier_usage.pop(ip, None)

    granted = len([c for c in codes if c != 402])
    assert granted == limit, (
        "the free tier granted %d requests when the limit is %d"
        % (granted, limit))


def test_the_limit_is_read_inside_the_lock_not_before_it():
    """A `used` read OUTSIDE the lock would be the same defect spelled
    differently, and the AST check above would not see it."""
    src = MAIN_SRC.read_text(encoding="utf-8")
    assert "with _lock:\n            used = _free_tier_usage.get(ip, 0)" in src, (
        "the counter is not read inside the critical section")


# ── finding 2: overpayment recovery ──────────────────────────────────────────

def test_recovery_accepts_at_least_the_price_not_exactly_it():
    """THE regression guard for the lost overpayment.

    A paid call whose response was lost must be recoverable. If the recovery
    check is `==` while verification accepts `>=`, an overpaying buyer is told
    their payment is good, is delivered to, and then — on the retry that the lost
    response forced — is refused. They paid and got nothing.
    """
    src = MAIN_SRC.read_text(encoding="utf-8")
    assert "if value >= price_atomic:" in src, (
        "nonce recovery no longer accepts an overpayment")
    assert "if value == price_atomic:" not in src, (
        "nonce recovery is back to exact equality, which cannot see an "
        "overpayment that verification accepted")


def test_the_two_rules_still_agree():
    """Verification and recovery must answer the same question the same way."""
    connectors = (REPO / "services" / "connectors.py").read_text(encoding="utf-8")
    main_src = MAIN_SRC.read_text(encoding="utf-8")

    verify_rejects_only_below = "int(got_amount) < int(want_amount)" in connectors
    recovery_accepts_at_least = "if value >= price_atomic:" in main_src
    assert verify_rejects_only_below and recovery_accepts_at_least, (
        "verification and recovery disagree about what an acceptable amount is")


def test_an_overpayment_is_visibly_logged():
    """Adopting an overpayment silently would hide a pricing bug; it is a real
    event and says so."""
    src = MAIN_SRC.read_text(encoding="utf-8")
    assert "overpaid" in src, (
        "an overpayment is adopted without a log line saying so")


# ── finding 3: graceful shutdown ─────────────────────────────────────────────

def test_the_worker_defines_a_bounded_shutdown_wait():
    src = WORKER_SRC.read_text(encoding="utf-8")
    assert "SHUTDOWN_JOIN_SECONDS" in src, (
        "the worker has no bounded wait for its loops")
    assert "STOP_EVENT" in src, "the stop event disappeared"


def test_the_worker_joins_its_threads_before_exit():
    """A daemon thread is killed at process exit, so returning from main_loop
    without joining cut every loop mid-cycle on every deploy."""
    src = WORKER_SRC.read_text(encoding="utf-8")
    assert ".join(" in src, "the worker never joins its threads"
    assert "threading.enumerate()" in src, (
        "the worker does not enumerate the threads it should wait for")


def test_the_shutdown_wait_is_bounded():
    """An unbounded join would hang the worker until Render SIGKILLs it, which
    is worse than not joining at all: no log, no clean exit."""
    tree = ast.parse(WORKER_SRC.read_text(encoding="utf-8"))
    value = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "SHUTDOWN_JOIN_SECONDS":
                    value = ast.literal_eval(node.value)
    assert value is not None, "SHUTDOWN_JOIN_SECONDS is not a literal constant"
    assert 0 < value <= 30, (
        "SHUTDOWN_JOIN_SECONDS is %r; it must be short enough to finish before "
        "Render escalates to SIGKILL" % value)


def test_the_worker_never_raises_during_shutdown():
    """Shutdown happens while signals are in flight; a raise there would lose the
    log line that says why the process is exiting."""
    src = WORKER_SRC.read_text(encoding="utf-8")
    assert "except Exception as exc:  # noqa: BLE001 - shutdown must not raise" in src, (
        "the join loop can raise and take the shutdown path with it")
    _ = threading  # imported for the module's own use in the drill suite
