"""Persistent dashboard store — single source of truth for the canonical
operations dashboard.

Nothing the dashboard shows lives in RAM, so deploys/restarts never reset the
numbers (priority-0 invariant: "deploy must not zero the counters").

WHERE THINGS LIVE (hybrid since 14.09):
  * DURABLE — PostgreSQL when DATABASE_URL is set, otherwise the SQLite file:
    the canonical MONEY table `onchain_sales`, the C1 replay lock
    `payment_guards` + its `guard_events` telemetry, and the request_log /
    whaleflow_events histories. All are owned by HistoryStore, written once and
    translated per dialect, so a deploy cannot zero or lose them.
  * LOCAL SQLite file — only the operational state whose loss is survivable:
    payapi_state and meta (scan watermarks).

Sources:
  * on-chain sales — real USDC transfers to the fee receiver, scanned from
    public RPC with the same read-only logic as scripts/competitor_recon.
    Payers are labelled: canary (Chet verification) / sampler (known market
    crawl infrastructure) / external (real customers).
  * request log — every request (after_request hook) with UA + funnel
    channel, persisted instead of the old RAM deques.
  * PayAPI listing state — reliability band + ranks for the 8 search terms.
  * CRM/Stripe — intentionally NOT stored here; it is read live from
    crm_store and must NEVER be mixed into on-chain totals.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

#: RPC providers embed the API key in the URL, e.g.
#: `https://base-mainnet.g.alchemy.com/v2/<KEY>`. Logging a raw httpx exception
#: (or our own "RPC not reachable: {url}") therefore writes the credential into
#: the log stream. Keep the host, drop the secret.
_RPC_KEY_RE = re.compile(
    r"(/v[0-9]+/|apikey=|api-key=|key=|token=)([A-Za-z0-9_\-]{6,})", re.I
)


def redact_rpc(text: Any) -> str:
    """Return `text` with any embedded RPC API key replaced by ***."""
    return _RPC_KEY_RE.sub(lambda m: m.group(1) + "***", str(text))


# ── Bounded waits on the shared Postgres link (outage 05.11) ───────────────
# HistoryStore keeps ONE Postgres connection behind ONE lock. Without bounds,
# a single slow or dead link is not a slow request — it is a dead service: the
# holder keeps `_pg_lock`, every caller queues, and with `--threads 8` eight
# queued callers are every worker there is, so /health fails too and Render
# answers 502. Measured on 05.11 before this change: /api/dashboard/data hung
# past 90s, and even the STATIC 402 challenge on /api/v1/whaleflow took 10.6s
# because request logging goes through the same lock.
#
# Three independent bounds, each addressing one link in that chain:
#   * connect timeout  — a reconnect to a slow/unreachable database gives up.
#   * statement timeout — the server cancels a runaway statement itself, so it
#     releases the lock instead of holding it until the client gives up.
#   * lock wait         — a caller refuses rather than queueing forever, which
#     turns a stalled lock into one fast error instead of an outage.
# Worst case per statement is now well under both the gunicorn timeout (120s)
# and Render's proxy patience, which is the whole point.
PG_CONNECT_TIMEOUT_SECONDS = max(
    1, int(os.getenv("KRISTO_PG_CONNECT_TIMEOUT", "5")))
PG_STATEMENT_TIMEOUT_MS = max(
    1000, int(os.getenv("KRISTO_PG_STATEMENT_TIMEOUT_MS", "8000")))
PG_LOCK_WAIT_SECONDS = max(
    1.0, float(os.getenv("KRISTO_PG_LOCK_WAIT_SECONDS", "15")))

#: How long a computed `request_log` summary may be replayed (seconds).
#:
#: The dashboard polls every 45s, so a value below that would recompute on
#: every single poll — the cost this exists to remove. The aggregates it
#: covers are all-time and day-grain, so a minute of age cannot make a number
#: wrong; it can only make `today` lag by up to a minute, which is invisible
#: on a 45-second refresh.
REQUEST_SUMMARY_TTL_SECONDS = max(
    5.0, float(os.getenv("KRISTO_REQUEST_SUMMARY_TTL_SECONDS", "60")))

#: How long the traffic summary may spend READING before the panels it has not
#: reached yet are reported as unreadable (seconds).
#:
#: The ten queries behind this summary are mostly full scans of `request_log`
#: (~783K rows, no retention). Measured live on 05.11 they took 10-21 SECONDS
#: each on this Postgres plan, and the first to hit the 8s statement timeout
#: raised QueryCanceled and failed the ENTIRE dashboard build — so the cache
#: never filled and every request built again. Bounding the TTL was not enough;
#: the read itself has to be survivable.
REQUEST_SUMMARY_BUDGET_SECONDS = max(
    1.0, float(os.getenv("KRISTO_REQUEST_SUMMARY_BUDGET_SECONDS", "6")))

#: The panels cheap enough to read live on a request path.
#:
#: The rule is BOUNDED vs UNBOUNDED, checked against the SQL rather than
#: guessed: `today` and `noise_today` are both `COUNT(*)` bounded by the indexed
#: day window, `recent` is an indexed `ORDER BY id DESC LIMIT 25`, the hourly
#: histogram is bounded by the same day window, the funnel is a grouped scan
#: that restricts itself with `path IN (...)` so `idx_request_log_path` serves
#: it, and `payment_attempts` does the same against `idx_payment_attempts_path_ts`
#: (see `payment_attempt_sql`). All six answer in milliseconds.
#:
#: Everything NOT here has no predicate at all or groups over every row
#: (`COUNT(*)` with no WHERE, `GROUP BY source / funnel / user_agent`, and an
#: all-time `GROUP BY path`) and took 10-21 SECONDS here — which is why it may
#: not run on the request path at any budget.
REQUEST_SUMMARY_FAST_PANELS = ("today", "recent", "hourly", "funnel",
                               "noise_today", "payment_attempts")

#: Where the heavy all-time panels are parked once computed.
REQUEST_SNAPSHOT_KEY = "requests_summary_snapshot_v1"

#: How long the BACKGROUND pass may spend reading the heavy panels (seconds).
#:
#: This is the whole point of the snapshot: a request path cannot spend 240s,
#: but a background thread can. Measured cost of the eight heavy reads is
#: ~100-210s total on this instance, so this budget fits the entire set with
#: room to spare, and a pass that still cannot finish simply keeps whatever it
#: did read and tries the rest next time (see `refresh_requests_snapshot`).
REQUEST_SNAPSHOT_BUDGET_SECONDS = max(
    30.0, float(os.getenv("KRISTO_REQUEST_SNAPSHOT_BUDGET_SECONDS", "240")))

#: How often the background pass re-reads the heavy panels (seconds).
#:
#: These numbers are all-time counts. Ten minutes of age cannot make one wrong,
#: and the page already labels the snapshot's age so a reader can tell how
#: fresh the all-time figures are.
REQUEST_SNAPSHOT_INTERVAL_SECONDS = max(
    60.0, float(os.getenv("KRISTO_REQUEST_SNAPSHOT_INTERVAL_SECONDS", "600")))

#: The statement timeout for the snapshot's OWN connection (milliseconds).
#:
#: THIS IS WHY THE ALL-TIME NUMBERS WERE UNREADABLE. Every read through `_run`
#: inherits `KRISTO_PG_STATEMENT_TIMEOUT_MS` (8s), so Postgres itself cancelled
#: every full scan of `request_log` at 8 seconds. No retry, no budget and no
#: index would have helped: the statement was killed by the server before it
#: could finish. Measured 05.11, `requests_summary` burned 21.5s and returned
#: `QueryCanceled` for `total`, `by_source`, `by_channel`, `noise_*` and the
#: funnel — while the same payload happily reported real numbers for the panels
#: that happen to be indexed.
#:
#: The snapshot pass therefore runs on a separate connection with its own,
#: generous ceiling. 300s is a bound, not an expectation: it exists so a
#: pathological plan cannot hold a backend open forever.
REQUEST_SNAPSHOT_STATEMENT_TIMEOUT_MS = max(
    10000,
    int(os.getenv("KRISTO_REQUEST_SNAPSHOT_STATEMENT_TIMEOUT_MS", "300000")))

#: The panel names (as they appear in `degraded`) that may NOT run on a request
#: path. Spelled out rather than derived from the SQL so that adding an
#: expensive panel to `_requests_summary_compute` cannot silently put it back on
#: the 45-second poll — the exact regression that took the board, and once the
#: whole service, down on 05.11.
REQUEST_SNAPSHOT_PANELS = (
    "by_path", "by_channel", "by_source", "by_source_clean",
    "top_user_agents", "noise_total", "total",
    # Parked as INSURANCE rather than as the only source: the funnel is bounded
    # by `idx_request_log_path` and is normally fast, but a
    # `CREATE INDEX CONCURRENTLY` that failed leaves an INVALID index behind and
    # `IF NOT EXISTS` then skips it for ever — after which the "fast" read is a
    # full scan that postgres cancels at 8s. Measured live on 05.11: the funnel
    # was in `degraded` on the request path while everything else answered.
    "funnel",
)

#: Keys read live FIRST and taken from the snapshot only when the live read
#: produced nothing. The live reading is the fresher one and wins when it exists;
#: the parked one exists so that a missing index costs a stale-but-real number
#: instead of a dash. Neither is ever invented.
REQUEST_SNAPSHOT_FALLBACK_KEYS = ("funnel",)

#: Keys the snapshot contributes to but that must be MERGED into the live result
#: instead of copied over it, because the request path already read part of them.
#: The override loop skips exactly these. Getting this wrong is not theoretical:
#: `internal_noise` was in the override loop, so the parked object — whose `today`
#: is None because the snapshot never reads the day half — replaced the live one
#: wholesale, and the board showed a real `today` beside a `today_clean` of „—"
#: with nothing marked degraded.
REQUEST_SNAPSHOT_MERGED_KEYS = REQUEST_SNAPSHOT_FALLBACK_KEYS + ("internal_noise",)

#: The served-summary keys that those panels produce. The serve path overlays
#: these from the snapshot; anything here that the snapshot has not read is
#: reported as unreadable rather than dropped or zeroed.
#:
#: `internal_noise` is overlaid by HALF and `today_clean` not at all. Both mix a
#: live reading with a parked one — today's keep-alive count and the day's total
#: are read on the request path, while the all-time counts are full scans — so
#: copying either wholesale would pair a fresh number with a stale one and
#: present the result as a single measurement.
REQUEST_SNAPSHOT_KEYS = (
    "total", "total_clean", "internal_noise", "by_source",
    "by_source_clean", "by_channel", "top_paths", "top_user_agents",
    # Parked so the fallback below can find it. It is deliberately SKIPPED by
    # the override loop, because for this key the live reading wins.
    "funnel",
)

# ── Payer taxonomy: KNOWN_PAYERS label → dashboard class ──────────────────
PAYER_CLASSES = {
    "chet_payapi_verification": "canary",
    "market_sampler_c59e": "sampler",
    "market_crawler_6777": "sampler",
    "market_crawler_54e1": "sampler",
    # 17.09: 0xA19F promoted from WATCHLIST to known crawl infrastructure —
    # 98 distinct receivers on the chain beat the "operator" label it carried
    # since 09.09. Class `sampler` = heartbeat, never a launch signal.
    "market_crawler_a19f": "sampler",
    # 17.09: 0xE3BA never got a customer label — the 30-day fingerprint found
    # 707 distinct receivers (threshold: 50), so it was a crawler from the
    # start. Class `sampler` = heartbeat, never a launch signal.
    "market_crawler_e3ba": "sampler",
    # 02.10: 0x4C29EC promoted — the 30-day fingerprint found **353 distinct
    # receivers in 13 days (≈197/week)** vs threshold 50, all payments relayed
    # (EIP-3009, no native txs) and seeded by the shared hub 0x6302d9e6.
    # Class `sampler` = heartbeat, never a launch signal (external humans stay
    # 0x4dB7 / 0x902dcf / 0xce4fbd).
    "market_crawler_4c29ec": "sampler",
}

USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
TRANSFER_TOPIC = (
    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
)
BLOCK_TIME_SECONDS = 2.0  # Base mainnet ~2s blocks


# ── Payment funnel: the paid routes whose 402→200 conversion we measure ───
# MUST stay in sync with X402_PAID_ENDPOINTS / REAL_X402_ROUTES in main.py —
# a paid route missing here is invisible in the funnel (the whale flow was
# exactly that gap until 13.09).
FUNNEL_ROUTES = [
    "/api/v1/signal",
    "/api/stats",
    "/api/sales",
    "/api/bot-status",
    "/api/arb/opportunities",
    "/api/v1/whaleflow",
    "/api/v1/verify-seller",
]

# ── Payment attempts: the four things that can happen to a presented payload ──
# Ordered by how far the buyer got, which is also the order the funnel renders
# them in. `settled` is the only one that is also a sale; the other three exist
# because "came with a signature and it did not work" is a different fact from
# "never came with a signature", and only one of those is worth calling a
# customer about.
PAYMENT_ATTEMPT_OUTCOMES = ("authorised", "rejected", "settle_failed", "settled")
# The subset that represents a buyer who actually tried, i.e. reached the rail.
_PAYMENT_ATTEMPT_OUTCOMES = frozenset(PAYMENT_ATTEMPT_OUTCOMES)

# Durable meta key holding the moment attempt recording began. It bounds the
# window over which the 401 SPLIT can be trusted — not the window abandonment is
# measured over, because abandonment is the 402 count and needs no table.
PAYMENT_ATTEMPTS_SINCE_KEY = "payment_attempts_since"


def payment_attempt_sql(since: str = "", until: str = "") -> Tuple[str, tuple]:
    """The one query that reads the attempt split, for both windows at once.

    Defined here, at module level, so the request path and the store method
    cannot drift into two different queries — the request path must go through
    the budgeted `q()` wrapper, and a second hand-written copy is exactly how an
    unbudgeted full-table scan gets reintroduced.

    `path IN (...)` is not decoration. `idx_payment_attempts_path_ts` is
    `(path, ts)`, so the predicate is what turns this into an index range instead
    of a scan of a table that only ever grows — and only the funnel's own routes
    are ever asked about. An unrestricted `GROUP BY path` here is the read that
    took the service down on 05.11; `test_the_request_path_never_reads_a_heavy_panel`
    enforces the difference.

    Both windows in one scan: `n` counts everything, `n_today` counts the rows
    inside `[since, until)`. Two queries would double this panel's cost on a path
    that runs on a query budget.
    """
    placeholders = ", ".join("?" for _ in FUNNEL_ROUTES)
    if since and until:
        sql = f"""SELECT path, outcome, COUNT(*) AS n,
                         SUM(CASE WHEN ts >= ? AND ts < ? THEN 1 ELSE 0 END)
                             AS n_today
                    FROM payment_attempts
                   WHERE path IN ({placeholders})
                   GROUP BY path, outcome"""
        return sql, (since, until, *FUNNEL_ROUTES)
    sql = f"""SELECT path, outcome, COUNT(*) AS n, COUNT(*) AS n_today
                FROM payment_attempts
               WHERE path IN ({placeholders})
               GROUP BY path, outcome"""
    return sql, tuple(FUNNEL_ROUTES)

# ── Whale flow defaults (env-regulatable, read at RUNTIME not import) ──────
WHALE_THRESHOLD_DEFAULT = 5_000_000.0   # USDC
# Raised from $50k on 18.09.2026 by the owner: at $50k the network-wide scan
# produced ~227,000 events/day on Base — that is market noise, not whale flow.
# At $5M it is ~53/day: a feed a human can actually read. The events themselves
# were always real (verified against on-chain USDC transfers), so this is a
# product decision about what "whale" means, not a data fix.
WHALE_RETENTION_DAYS_DEFAULT = 30       # rows older than this are deleted at boot
WHALE_WINDOW_HOURS_DEFAULT = 24      # rolling window served by the route
WHALE_BACKFILL_HOURS_DEFAULT = 24    # initial backfill on first run

# ── request_log retention (the fix for the 07.11 memory kill) ──────────────
# `request_log` had NO retention anywhere: it only ever grew, and by 07.11 it
# held ~1.1M+ rows. The traffic summary runs ten aggregates over it, and even
# with idx_request_log_path those reads are the heaviest thing this service
# does — measured at 10-21 SECONDS each on 05.11, against a server statement
# timeout of 8s. A panel that cannot be read is now reported as unreadable
# instead of failing the whole build, but the underlying cost only grows.
#
# WHY 30 DAYS IS SAFE. The only window any query opens on `request_log` is
# `timedelta(days=1)` — the traffic summary reads a rolling 24 hours. Nothing
# in the service reads a 7-day or 30-day slice of it. A 30-day horizon is
# therefore 30x more history than anything consumes, while still being a hard
# ceiling: the table can no longer grow without bound, which is what let a
# single slow panel take the whole service down.
#
# The horizon is a module constant, like WHALE_RETENTION_DAYS_DEFAULT above —
# so it is read once at import and a change needs a deploy, not a restart. That
# is deliberate: a retention pass deletes rows, and a number that could change
# under a running process would make an accidental short horizon impossible to
# audit afterwards.
REQUEST_LOG_RETENTION_DAYS_DEFAULT = 30


def whale_threshold() -> float:
    """Current whale threshold (USDC) — env WHALE_THRESHOLD, read live."""
    try:
        return max(1.0, float(os.getenv("WHALE_THRESHOLD", str(WHALE_THRESHOLD_DEFAULT))))
    except ValueError:
        return WHALE_THRESHOLD_DEFAULT


def _label_address(addr: str) -> str:
    """Honest label: known market infra / watchlisted operator by name,
    everything else literally 'unknown'. ZERO invention (SKU-cleanup rule)."""
    a = (addr or "").lower()
    try:
        from scripts.competitor_recon import KNOWN_PAYERS, WATCHLIST
    except Exception:
        KNOWN_PAYERS, WATCHLIST = {}, {}
    if a in KNOWN_PAYERS:
        return KNOWN_PAYERS[a]
    if a in {k.lower(): v for k, v in WATCHLIST.items()}:
        return WATCHLIST[a]
    return "unknown"


def default_db_path() -> str:
    base = Path(__file__).resolve().parent.parent / "data"
    base.mkdir(parents=True, exist_ok=True)
    return str(base / "dashboard_state.db")


def classify_payer(sender: str) -> Tuple[str, str]:
    """Return (payer_class, payer_label) for a sending address.

    canary   — known verification canary (Chet / PayAPI reviewer)
    sampler  — known market sampling/crawl infrastructure (heartbeat, not a
               launch signal)
    external — everything else (real customer until proven otherwise)
    """
    try:
        from scripts.competitor_recon import KNOWN_PAYERS
    except Exception:  # pragma: no cover - import fallback
        KNOWN_PAYERS = {}
    label = KNOWN_PAYERS.get((sender or "").lower(), "")
    if not label:
        return ("external", "external")
    return (PAYER_CLASSES.get(label, "sampler"), label)


def _norm_tx(tx_hash: str) -> str:
    tx = (tx_hash or "").strip().lower()
    return tx if tx.startswith("0x") else ("0x" + tx if tx else "")


def _failure_backoff_seconds() -> float:
    """Seconds to pause BEFORE retrying a refused getLogs window (10.10).

    The halving loop used to fire identical requests back-to-back; against a
    rate-limited public RPC that is a self-inflicted ban. Default 2s; tests
    set RPC_FAILURE_BACKOFF_SECONDS=0 to keep the suite fast.
    """
    try:
        return max(0.0, float(os.getenv("RPC_FAILURE_BACKOFF_SECONDS", "2.0")))
    except ValueError:
        return 2.0


def _is_fresh(iso_ts: Optional[str], max_age_seconds: float = 180.0) -> bool:
    """True when an ISO timestamp is 0..max_age_seconds old (10.10).

    Used to tell a LIVE failure from a stale one: the whale scanner records
    `whaleflow_last_attempt` at the start of every cycle, so an old timestamp
    means the scan is not running at all — and an old error string must not
    keep the dashboard red forever.
    """
    if not iso_ts:
        return False
    try:
        ts = datetime.fromisoformat(str(iso_ts))
    except ValueError:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - ts).total_seconds()
    return 0 <= age <= max_age_seconds


def _adaptive_get_logs(w3, from_block: int, to_block: int, topics: list,
                       chunk_blocks: int, pause_seconds: float,
                       handle_logs, address: str = USDC_BASE,
                       on_progress=None):
    """Chunked, PACED `eth_getLogs` with adaptive halving — THE one place that
    knows how to talk to a rate-limited / range-capped free RPC.

    Both the sales scan (`scan_window`) and the whale scan
    (`scan_whale_window`) go through this: the chunk/pacing/halving rules are
    a solved problem and must not be re-implemented per feature (free tiers
    answer `-32001 Block range too large: maximum allowed is 50 blocks` and
    `429 Too Many Requests`).

    A refused window is retried with HALF the span on the SAME start block
    (never skipping a range, never faking a gap); at span 1 a failure means
    the RPC is down and the walk stops so the caller's watermark retries it
    next cycle.

    Returns `(safe_end, effective_span)`: the last CONTIGUOUS scanned block
    (from_block - 1 when nothing was scanned) and the narrowest span the RPC
    actually accepted (ops telemetry).
    """
    import time as _time

    from web3 import Web3

    span = max(1, int(chunk_blocks))
    effective_span = span
    start = from_block
    safe_end = from_block - 1
    while start <= to_block:
        end = min(start + span - 1, to_block)
        try:
            logs = w3.eth.get_logs({
                "fromBlock": start,
                "toBlock": end,
                "address": Web3.to_checksum_address(address),
                "topics": topics,
            })
        except Exception as exc:
            # Telemetry (10.10): never swallow WHY a window was refused — a
            # rate-limited public RPC (HTTP 429) and a dead node looked
            # identical in this silent branch. Control flow is UNCHANGED.
            _resp = getattr(exc, "response", None)
            _status = getattr(_resp, "status_code", None)
            log.warning("getLogs %s..%s refused (span=%d%s): %s",
                        start, end, span,
                        f", HTTP {_status}" if _status is not None else "",
                        str(exc)[:200])
            if span > 1:
                # Adaptive back-off: halve and retry the SAME start block.
                span = max(1, span // 2)
                effective_span = min(effective_span, span)
                log.debug("getLogs %s.. refused — retry with span=%d",
                          start, span)
                # A longer pause before the retry (10.10): the halving loop
                # used to fire identical requests back-to-back, which turns a
                # rate-limited RPC into a self-inflicted ban. 0 in tests via
                # RPC_FAILURE_BACKOFF_SECONDS.
                if _failure_backoff_seconds() > 0:
                    _time.sleep(_failure_backoff_seconds())
                continue
            break
        safe_end = end
        effective_span = min(effective_span, span)
        handle_logs(logs)
        if on_progress is not None:
            try:
                # Called after every ACCEPTED chunk so a caller can persist
                # progress mid-walk. Telemetry must never break the walk.
                on_progress(safe_end, effective_span)
            except Exception:
                log.debug("progress callback failed (non-fatal)", exc_info=True)
        start = end + 1
        if start <= to_block:
            _time.sleep(pause_seconds)
    return safe_end, effective_span


# ── Durable store: request_log + whaleflow_events + onchain_sales ──────────
# These tables are HISTORIES, and losing them on every deploy was visible: the
# request log reset to zero and the PAID whale feed's all_time count fell from
# 20 478 to 598 after a single deploy. They follow DATABASE_URL exactly like the
# CRM does — with ONE implementation and two dialects (each query body is
# written once; only the placeholder and the conflict syntax differ), so the two
# backends cannot drift apart.
#
# onchain_sales JOINED THIS LIST on 14.09. It is the canonical MONEY table, and
# it was the last thing still living on Render's ephemeral disk — defended by a
# boot-time seed that had to re-insert the chain manifest after every deploy.
# That defence worked, but it was a rescue, not a design: the dashboard's
# numbers were re-created from a hand-written file instead of surviving. With
# the table on the durable backend the numbers simply persist, and the seed
# degrades to what it should always have been — a BOOTSTRAP for a genuinely
# empty database (first boot) plus a self-heal for a partially lost one. It is
# insert-only: it can never overwrite, relabel or delete a scan-discovered row.
#
# ONLINE-SAFETY NOTE (14.09): the C1/C2/H2 replay lock (`payment_guards`) and its
# telemetry (`guard_events`) moved here too. The lock used to live on the SQLite
# file, which meant a deploy REOPENED every consumed proof. It is the one table
# where "durable" and "fail-closed" must both hold, so `claim_payment_tx` REFUSES
# a payment when the backend cannot be reached — an unreachable lock is treated
# as a locked door, never as an open one.
class HistoryStore:
    """request_log + whaleflow_events + onchain_sales, SQLite or PostgreSQL."""

    def __init__(self, sqlite_connect, write_lock, database_url: str = ""):
        self._sqlite_connect = sqlite_connect
        self._lock = write_lock
        self.database_url = (database_url or "").strip()
        self.backend = "postgresql" if self.database_url else "sqlite"
        self._ph = "%s" if self.backend == "postgresql" else "?"
        self._pg_conn = None
        self._pg_lock = threading.Lock()
        # NEGATIVE-ONLY fast path for the C1 replay lock: a hash this process has
        # already claimed can never be claimable again, so a hit refuses without
        # touching the database. A MISS NEVER GRANTS — the row in the database is
        # the truth and is always consulted. Bounded: if it ever grows past the
        # cap it is cleared, which is safe precisely because it only denies.
        self._claimed_cache: set = set()
        self._claimed_cache_cap = 20000
        # Cached result of the C1 replay-lock liveness probe (F-04).
        #
        # The probe writes a sentinel row into `payment_guards` — the SAME table
        # and the SAME `_pg_lock` that `claim_payment_tx` uses to refuse replays.
        # It used to run on every call, and `/api/dashboard/data` is free and
        # unbounded, so an anonymous poller could drive unlimited INSERT/DELETE
        # churn and contend with a paying customer's replay claim. Worse, a
        # failed probe is exactly the fail-closed condition under which payments
        # start being refused — so the read path could help cause it.
        #
        # The probe is now TIME-driven, not request-driven: at most one probe per
        # `probe_ttl_seconds`, however many times the endpoint is polled. A
        # request can no longer amplify it, and the background dashboard loop
        # (main._dashboard_scan_loop) refreshes it so the route normally reads a
        # warm cache and writes nothing at all.
        self._probe_lock = threading.Lock()
        self._probe_at = 0.0
        self._probe_alive = None
        self._probe_error = ""
        # TTL cache for the all-time request aggregates (see requests_summary).
        # These eight unbounded counts and GROUP BYs are the most expensive
        # thing the dashboard does, they ran on every 45s poll, and they ran
        # behind the single shared Postgres lock — which is how one slow read
        # became a service-wide outage on 05.11. Guarded by its own lock so a
        # slow compute never blocks a warm read.
        self._summary_lock = threading.Lock()
        self._summary_value: Optional[Dict[str, Any]] = None
        self._summary_json = "{}"
        self._summary_at = 0.0
        self._summary_limit: Optional[int] = None
        # The heavy half of that summary: eight full scans that postgres was
        # cancelling at its 8s statement timeout, so they are computed on a
        # background pass with its own connection and parked here (and in
        # `dashboard_meta`, so a deploy does not blank them).
        self._snapshot_lock = threading.Lock()
        self._snapshot_value: Optional[Dict[str, Any]] = None
        self._snapshot_refreshing = False
        #: The EXCEPTION CLASS of the last pass that failed, or None. The class
        #: only: a driver message can carry the DSN. This exists because a pass
        #: that fails silently leaves the board saying "awaiting the snapshot"
        #: for ever while nothing anywhere says it is never going to arrive —
        #: which is exactly what happened when the pass died on `SET
        #: statement_timeout = %s` before reading a single row.
        self._snapshot_last_error: Optional[str] = None
        # BOTH dialects create their tables — idempotent CREATE TABLE IF NOT
        # EXISTS, so the schema cannot drift between the two backends either.
        self._ensure_schema()

    # ── plumbing ────────────────────────────────────────────────────────────
    def _q(self, sql: str) -> str:
        """Translate one query body to the active dialect.

        psycopg treats `%` as a placeholder marker, so a LITERAL percent — as in
        `user_agent LIKE 'Render/%'` — must be doubled to `%%`, and that has to
        happen BEFORE `?` becomes `%s`. Missing this turned every dashboard
        request into psycopg.ProgrammingError ("only '%s', '%b', '%t' are
        allowed as placeholders, got '%'"). Every body here uses `?` for
        parameters, never a raw `%s`, so the doubling cannot corrupt one.
        """
        if self.backend == "postgresql":
            return sql.replace("%", "%%").replace("?", "%s")
        return sql

    def _pg_connection(self):
        """The one shared Postgres link, rebuilt when it is not usable.

        `closed` alone is not enough. A connection the server has reaped, or
        one sitting on a socket that died without a FIN, reports
        `closed == False` and then blocks on the next statement with no timeout
        of its own — while holding `_pg_lock` and, through it, every other
        caller. `broken` catches that case and forces a reconnect.

        Two bounds make the reconnect safe to do from the hot path: libpq's
        `connect_timeout`, and a session-level `statement_timeout` so that no
        statement issued on this link can outlive the waiters.
        """
        conn = self._pg_conn
        if conn is None or conn.closed or getattr(conn, "broken", False):
            conn = self._pg_open(PG_STATEMENT_TIMEOUT_MS)
            self._pg_conn = conn
        return conn

    def _pg_open(self, statement_timeout_ms: int):
        """Open a Postgres link with the row factory and timeout this module needs.

        THE ONE PLACE a Postgres connection is created, because the two callers
        must agree and did not. Both facts below are dialect rules that a fake
        cursor cannot exercise, so each one has bitten exactly once:

          * `row_factory=dict_row`. Panel readers index rows by column name —
            `row["n"]` — because `sqlite3.Row` allows it too and this module
            serves both backends. psycopg's default factory returns plain
            tuples, so a connection opened without this raises
            `TypeError: tuple indices must be integers or slices, not str` on
            the first aggregate it reads. That killed the whole snapshot pass.

          * `set_config` rather than `SET`. The extended protocol cannot bind a
            parameter into a `SET`: psycopg sends `$1` and the server answers
            42601 syntax error at or near "$1". Interpolating the value instead
            would make this the one place the module built SQL by formatting.

        A private connection that forgot either would fail the same way the
        shared one did, silently, and the board would keep saying "awaiting the
        snapshot" for ever while nothing anywhere said why.
        """
        import psycopg
        from psycopg.rows import dict_row
        conn = psycopg.connect(
            self.database_url,
            row_factory=dict_row,
            connect_timeout=PG_CONNECT_TIMEOUT_SECONDS,
        )
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('statement_timeout', %s, false)",
                        (str(int(statement_timeout_ms)),))
        conn.commit()
        return conn

    def _run(self, sql: str, params: tuple = (), fetch: str = ""):
        """Execute one statement in either dialect. Returns (rows, rowcount)."""
        sql = self._q(sql)
        if self.backend == "sqlite":
            with self._lock, self._sqlite_connect() as conn:
                cur = conn.execute(sql, params)
                rows = (cur.fetchall() if fetch == "all"
                        else cur.fetchone() if fetch == "one" else None)
                rowcount = cur.rowcount
                conn.commit()
            return rows, rowcount
        # ONE shared link, so this lock is the throughput ceiling for every
        # Postgres read AND every request-log write. Waiting on it forever is
        # what turned a single slow statement into a whole-service outage: the
        # holder keeps the lock, callers pile up behind it, and eight of them
        # are every worker there is. Bounded wait instead — a stalled holder
        # now costs one fast error rather than the process.
        if not self._pg_lock.acquire(timeout=PG_LOCK_WAIT_SECONDS):
            raise TimeoutError(
                "shared Postgres link busy for %.0fs; refusing instead of "
                "queueing every caller behind it" % PG_LOCK_WAIT_SECONDS)
        try:
            try:
                conn = self._pg_connection()
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    rows = (cur.fetchall() if fetch == "all"
                            else cur.fetchone() if fetch == "one" else None)
                    rowcount = cur.rowcount
                conn.commit()
                return rows, rowcount
            except Exception:
                # A dropped/aborted transaction must not poison the shared
                # connection for every later caller.
                try:
                    self._pg_conn.close()
                except Exception:
                    pass
                self._pg_conn = None
                raise
        finally:
            self._pg_lock.release()

    def _ensure_schema(self) -> None:
        """Create every durable table — idempotent, on first use.

        The CRM taught this lesson the hard way: assuming a table already exists
        turned a correctly provisioned database into HTTP 500 for the whole
        dashboard.
        """
        id_type = ("BIGSERIAL PRIMARY KEY" if self.backend == "postgresql"
                   else "INTEGER PRIMARY KEY AUTOINCREMENT")
        real = "DOUBLE PRECISION" if self.backend == "postgresql" else "REAL"
        self._run(
            f"""CREATE TABLE IF NOT EXISTS request_log (
                    id          {id_type},
                    ts          TEXT,
                    method      TEXT,
                    path        TEXT,
                    source      TEXT,
                    status_code INTEGER,
                    user_agent  TEXT,
                    referer     TEXT,
                    funnel      TEXT
                )"""
        )
        self._run(
            f"""CREATE TABLE IF NOT EXISTS whaleflow_events (
                    tx_hash      TEXT,
                    log_index    INTEGER,
                    ts           TEXT,
                    token        TEXT,
                    amount_usdc  {real},
                    from_addr    TEXT,
                    to_addr      TEXT,
                    block_number BIGINT,
                    recorded_at  TEXT,
                    PRIMARY KEY (tx_hash, log_index)
                )"""
        )
        self._run("CREATE INDEX IF NOT EXISTS idx_request_log_ts "
                  "ON request_log (ts)")
        self._run("CREATE INDEX IF NOT EXISTS idx_whaleflow_ts "
                  "ON whaleflow_events (ts)")
        self._ensure_whaleflow_indexes()
        # Path index for the payment funnel / top-paths queries (option B,
        # double-door 11.10) — see _ensure_request_log_path_index().
        self._ensure_request_log_path_index()
        # The canonical MONEY table (moved here 14.09 — see the class comment).
        # `block_number` is BIGINT: Base has been above the 2^31 range for a
        # while and SQLite's INTEGER is 64-bit anyway.
        self._run(
            f"""CREATE TABLE IF NOT EXISTS onchain_sales (
                    tx_hash      TEXT PRIMARY KEY,
                    block_number BIGINT,
                    ts           TEXT,
                    sender       TEXT,
                    amount_usdc  {real},
                    payer_class  TEXT,
                    payer_label  TEXT,
                    source       TEXT,
                    recorded_at  TEXT
                )"""
        )
        self._run("CREATE INDEX IF NOT EXISTS idx_onchain_sales_ts "
                  "ON onchain_sales (ts)")
        # ── C1 replay lock: a tx hash may unlock EXACTLY ONE paid call, and that
        # fact must outlive restarts/deploys (the old in-RAM set did not, and the
        # local SQLite file was wiped by every deploy).
        self._run(
            f"""CREATE TABLE IF NOT EXISTS payment_guards (
                    tx_hash      TEXT PRIMARY KEY,
                    endpoint     TEXT,
                    payer        TEXT,
                    amount_usdc  {real},
                    consumed_at  TEXT,
                    block_number BIGINT,
                    block_hash   TEXT
                )"""
        )
        # ── Finality anchor (21.09, from Miguel's feedback) ──────────────────
        # Depth alone cannot see a reorg that KEEPS the height and changes the
        # hash. We store the confirming block's number and hash so the chain can
        # be re-read later and compared. The confirmation THRESHOLD is untouched:
        # this is an extra check on top, not a replacement for depth.
        self._ensure_column("payment_guards", "block_number", "BIGINT")
        self._ensure_column("payment_guards", "block_hash", "TEXT")
        # Delivery state (audit #4, 22.09): C1 locks the PAYMENT, not the
        # product. `delivered_at` is stamped only when a 2xx/3xx response was
        # actually produced, so a claim whose response errored stays
        # recoverable, while a delivered one stays a permanent replay-refusal.
        # `retry_claimed_at` is the single-flight slot that keeps ONE recovery
        # attempt in at a time instead of a stampede of duplicates.
        self._ensure_column("payment_guards", "delivered_at", "TEXT")
        self._ensure_column("payment_guards", "retry_claimed_at", "TEXT")
        # ── Guard rejections (C1 replay / C2 depth / H2 binding) — so the
        # dashboard section proves the guards are ALIVE from a table instead of
        # guessing it from log lines.
        self._run(
            f"""CREATE TABLE IF NOT EXISTS guard_events (
                    id      {id_type},
                    ts      TEXT,
                    kind    TEXT,
                    endpoint TEXT,
                    tx_hash  TEXT,
                    detail   TEXT
                )"""
        )
        self._run("CREATE INDEX IF NOT EXISTS idx_guard_events_ts "
                  "ON guard_events (ts)")
        # ── Payment attempts (07.11) — the funnel's missing middle ────────────
        # WHY THIS TABLE EXISTS. The payment funnel derived everything from
        # `request_log`: `status_code = 402` counted as a challenge, `200` as a
        # paid retry. That cannot tell two very different buyers apart, because
        # a buyer who ARRIVES WITH A VALID SIGNATURE and whose settlement then
        # fails also gets a 402. So "1,779 agents looked at the price and walked
        # away" and "1,779 agents tried to pay and the rail refused them" render
        # as the same number — and those two facts call for opposite work.
        #
        # This table records the attempt itself, at the moment the signature
        # arrives, before any outcome is known. `request_log` keeps recording
        # responses; this records INTENT.
        #
        # The four outcomes are deliberately distinct:
        #   authorised    — a payload arrived and verified against our terms
        #   rejected      — a payload arrived and did NOT verify
        #   settle_failed — verified, but the facilitator could not settle it
        #   settled       — verified and settled (also lands in onchain_sales)
        #
        # Anything not in the table is, by construction, a buyer who never
        # presented a signature at all. That is the `abandoned` figure, and it
        # is DERIVED rather than stored, so it cannot drift from the 402 count
        # it is derived from.
        self._run(
            f"""CREATE TABLE IF NOT EXISTS payment_attempts (
                    id          {id_type},
                    ts          TEXT,
                    path        TEXT,
                    outcome     TEXT,
                    payer       TEXT,
                    amount_usdc {real},
                    detail      TEXT,
                    tx_hash     TEXT
                )"""
        )
        self._run("CREATE INDEX IF NOT EXISTS idx_payment_attempts_ts "
                  "ON payment_attempts (ts)")
        # (path, ts) serves the per-route split; the funnel already groups by
        # path, so a lone ts index would force a scan per route.
        self._run("CREATE INDEX IF NOT EXISTS idx_payment_attempts_path_ts "
                  "ON payment_attempts (path, ts)")
        # WHEN attempt recording began. Written ONCE and never overwritten, so a
        # redeploy cannot move the window forward and quietly shrink it.
        #
        # This exists because the table starts empty on the deploy that adds it,
        # and `abandoned` is DERIVED (402s minus the attempts that were not
        # abandonment). For every 402 recorded BEFORE this moment we have no
        # attempt data at all, so subtracting zero would publish "all of those
        # buyers walked away" — a claim about the past we never measured.
        # Recording the epoch instead lets the funnel report abandonment only
        # over the window it actually observed, and say so. The row is written
        # AFTER dashboard_meta exists, further down this method — doing it here
        # failed with "no such table: dashboard_meta" on the schema pass, because
        # the durable meta table is created a few statements below.
        # ── Durable operational meta (18.09) ──────────────────────────────────
        # The whale scan watermarks used to live in the LOCAL file, which Render
        # wipes on every deploy — and auto-deploy is on, so every push re-scanned
        # 24 hours of chain: ~900 getLogs calls on the free RPC and ~35 minutes in
        # which the PAID feed's freshness lagged reality. Watermarks belong with
        # the data they describe.
        self._run(
            """CREATE TABLE IF NOT EXISTS dashboard_meta (
                   key        TEXT PRIMARY KEY,
                   value      TEXT,
                   updated_at TEXT
               )"""
        )
        # The payment-attempt epoch (see the note above payment_attempts).
        # Insert-only on purpose: ON CONFLICT DO NOTHING means a redeploy can
        # never move the window forward and quietly shrink what we claim to have
        # measured.
        self._run(
            """INSERT INTO dashboard_meta (key, value, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT (key) DO NOTHING""",
            (PAYMENT_ATTEMPTS_SINCE_KEY, datetime.now(timezone.utc).isoformat(),
             datetime.now(timezone.utc).isoformat()))
        self._run(
            """CREATE TABLE IF NOT EXISTS vip_invites (
                   code       TEXT PRIMARY KEY,
                   wallet     TEXT,
                   tx_hash    TEXT,
                   chat_id    TEXT,
                   created    TEXT,
                   used       INTEGER DEFAULT 0,
                   source     TEXT
               )"""
        )
        self._run("CREATE INDEX IF NOT EXISTS idx_vip_invites_wallet "
                  "ON vip_invites (wallet)")
        self._run(
            """CREATE TABLE IF NOT EXISTS signal_history (
                   id                TEXT PRIMARY KEY,
                   asset             TEXT,
                   action            TEXT,
                   confidence        REAL,
                   issued_at         TEXT,
                   price_at_issue    REAL,
                   vol_threshold     REAL,
                   price_at_24h      REAL,
                   move_pct          REAL,
                   outcome           TEXT,
                   resolved_at       TEXT,
                   resolution_source TEXT,
                   frozen_on         TEXT
               )"""
        )
        self._run("CREATE INDEX IF NOT EXISTS idx_signal_history_issued "
                  "ON signal_history (issued_at)")
        # ── Sentinel PR watcher baseline (27.09) ──────────────────────────────
        # The watcher kept the last seen PR status only in memory, so every
        # deploy restarted it blind (a merge during a deploy produced no alert)
        # and a brand-new PR was indistinguishable from a transition. Baseline
        # belongs where payment_guards is: in the durable store.
        self._run(
            """CREATE TABLE IF NOT EXISTS pr_watch_state (
                   pr_key          TEXT PRIMARY KEY,
                   status          TEXT,
                   mergeable_state TEXT,
                   updated_at      TEXT
               )"""
        )
        log.info("Durable store ready (%s): request_log + whaleflow_events + "
                 "onchain_sales + payment_guards + guard_events + dashboard_meta "
                 "+ vip_invites + signal_history + pr_watch_state.",
                 self.backend)

    # ── request log ─────────────────────────────────────────────────────────
    def _ensure_column(self, table: str, column: str, decl: str) -> None:
        """Add a column if it is missing — idempotent, on BOTH backends.

        SQLite has no `ALTER TABLE … ADD COLUMN IF NOT EXISTS`, so the existing
        columns are inspected first; Postgres could do it in one statement but
        sharing one path keeps the dialects honest.
        """
        try:
            if self.backend == "sqlite":
                rows = self._sqlite_connect().execute(
                    "PRAGMA table_info(%s)" % table).fetchall()
                existing = {row[1] for row in rows}
            else:
                rows = self._run(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = ?", (table,), "all")[0]
                existing = {row["column_name"] for row in (rows or [])}
            if column not in existing:
                self._run("ALTER TABLE %s ADD COLUMN %s %s"
                          % (table, column, decl))
                log.info("Durable store: added %s.%s", table, column)
        except Exception as exc:      # never break a boot over a migration
            log.warning("Could not ensure %s.%s: %s", table, column, exc)

    def record_request(self, method: str, path: str, source: str,
                       status_code: int, user_agent: str = "",
                       referer: str = "", funnel: Optional[str] = None) -> None:
        self._run(
            """INSERT INTO request_log
                   (ts, method, path, source, status_code,
                    user_agent, referer, funnel)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now(timezone.utc).isoformat(),
                method,
                path,
                source,
                int(status_code or 0),
                (user_agent or "")[:120],
                (referer or "")[:160],
                funnel,
            ),
        )

    # ── whale flow events ───────────────────────────────────────────────────
    def record_whale_event(self, tx_hash: str, log_index: int, ts: str,
                           token: str, amount_usdc: float, from_addr: str,
                           to_addr: str, block_number: int) -> int:
        """Insert one whale row. Returns 1 when new, 0 when it was duplicate."""
        sql = """INSERT INTO whaleflow_events
                     (tx_hash, log_index, ts, token, amount_usdc, from_addr,
                      to_addr, block_number, recorded_at)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"""
        if self.backend == "postgresql":
            sql += " ON CONFLICT (tx_hash, log_index) DO NOTHING"
        else:
            sql = sql.replace("INSERT INTO", "INSERT OR IGNORE INTO", 1)
        _rows, rowcount = self._run(
            sql,
            (tx_hash, int(log_index), ts, token, round(float(amount_usdc), 6),
             from_addr, to_addr, int(block_number),
             datetime.now(timezone.utc).isoformat()),
        )
        return max(0, int(rowcount or 0))

    def _ensure_whaleflow_indexes(self) -> None:
        """Index the whale-feed reads — the 40-second dashboard build (05.11).

        `whale_rows` runs two reads that `idx_whaleflow_ts (ts)` cannot serve:

            SELECT … FROM whaleflow_events
             WHERE ts >= ? AND amount_usdc >= ?
             ORDER BY ts DESC, block_number DESC LIMIT ?
            SELECT COUNT(*), MAX(ts), MAX(block_number)
              FROM whaleflow_events WHERE amount_usdc >= ?     <-- the expensive one

        The second filters on `amount_usdc`, which had NO index at all, so
        Postgres had to read the entire table to count matching rows. This
        module already records that `whaleflow_events` reached 427 MB in under
        five days at the old $50k threshold, and the threshold is now lower —
        so "the entire table" means hundreds of MB, read on every dashboard
        build, behind the single shared Postgres link.

        That is where the 40 seconds went. It also explains the shape of the
        05.11 outage exactly: /health and the static `/` answered in ~400ms
        because they never touch this table, while /api/dashboard/data ran for
        40+ seconds and eventually returned 500 — and the audit's F-22 had
        already measured the same thing as "5 full scans (~41 s live)".

        (amount_usdc, ts, block_number) answers the aggregate from the index
        alone; (ts DESC, block_number DESC) lets the windowed read walk in the
        order it was asked for instead of sorting. Idempotent, and on
        PostgreSQL built CONCURRENTLY so it never takes a write lock on a table
        this size — the same double-door the request_log path index uses.
        """
        stmts = (
            ("idx_whaleflow_amount",
             "whaleflow_events (amount_usdc, ts, block_number)"),
            ("idx_whaleflow_ts_block",
             "whaleflow_events (ts DESC, block_number DESC)"),
        )
        if self.backend == "postgresql":
            try:
                import psycopg
                with psycopg.connect(self.database_url, autocommit=True,
                                     connect_timeout=5) as conn:
                    for name, target in stmts:
                        conn.execute(
                            "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
                            f"{name} ON {target}")
                return
            except Exception:
                # Fall back to the transactional path; an index problem must
                # never block boot (same rule as the request_log path index).
                pass
        for name, target in stmts:
            self._run(f"CREATE INDEX IF NOT EXISTS {name} ON {target}")

    def _ensure_request_log_path_index(self) -> None:
        """Create idx_request_log_path (option B, double-door 11.10).

        Serves `WHERE path IN (…)` (payment funnel) and the by_path top-10 —
        both were full scans over request_log (~783K rows). Idempotent both
        ways. On PostgreSQL prefer CONCURRENTLY (no write lock on the table)
        via a short autocommit side connection — CREATE INDEX CONCURRENTLY
        cannot run inside the regular transactional _run. The plain CREATE
        INDEX IF NOT EXISTS is the SQLite path and the PostgreSQL fallback;
        an index problem must never block boot.
        """
        ddl = ("CREATE INDEX IF NOT EXISTS idx_request_log_path "
               "ON request_log (path)")
        if self.backend == "postgresql":
            try:
                import psycopg
                with psycopg.connect(self.database_url, autocommit=True,
                                     connect_timeout=5) as conn:
                    conn.execute(
                        "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
                        "idx_request_log_path ON request_log (path)")
                return
            except Exception:
                try:
                    self._run(ddl)
                except Exception:
                    pass
            return
        self._run(ddl)

    def requests_summary(self, recent_limit: int = 25) -> Dict[str, Any]:
        """The traffic summary the board is served: live where it can be, parked where it cannot.

        WHY THIS SHAPE. `request_log` has no retention, so it only grows; on
        05.11 the ten aggregates behind this summary ran over ~783K rows behind
        ONE shared Postgres link, and the first to exceed the server's 8s
        statement timeout raised QueryCanceled, which failed the ENTIRE
        dashboard build — so the cache never filled and every 45-second poll
        built again. One slow panel took the whole board, and for a while the
        whole service, down.

        Three things had to change, and each one is load-bearing:

        1. A panel that cannot be read is REPORTED as unreadable rather than
           failing the build (`_requests_summary_compute`).
        2. The unbounded aggregates never run on a request path at all. A
           request cannot spend 240 seconds; the background pass can.
        3. That pass uses its OWN Postgres connection. `_run` holds the shared
           link's lock for the whole statement, so routing 20-second reads
           through it would queue the fast panels behind them and rebuild the
           outage by hand.

        The numbers here are all-time or day-grain. None of them becomes more
        correct when recomputed on every request, so the heavy half is read at
        most once per `REQUEST_SNAPSHOT_INTERVAL_SECONDS` and replayed in
        between, with its age published so a reader can judge it.

        `None` means "we could not read this". It is NEVER a stand-in zero: a
        zero here is a factual claim about traffic, and inventing one is worse
        than admitting the gap.
        """
        limit = int(recent_limit)
        now = time.time()
        ttl = REQUEST_SUMMARY_TTL_SECONDS
        with self._summary_lock:
            fresh = (self._summary_value is not None
                     and self._summary_limit == limit
                     and (now - self._summary_at) < ttl)
            if fresh:
                # A deep copy through JSON: the caller gets its own lists, so
                # nothing it does downstream can reach back into the cache.
                return json.loads(self._summary_json)
        value = self._requests_summary_serve(recent_limit=limit)
        blob = json.dumps(value, default=str)
        with self._summary_lock:
            self._summary_value = value
            self._summary_json = blob
            self._summary_at = now
            self._summary_limit = limit
        return json.loads(blob)

    def _requests_summary_serve(self, recent_limit: int = 25) -> Dict[str, Any]:
        """Live bounded panels, unbounded panels overlaid from the snapshot.

        The split is by measured cost, not by topic. `today`, `noise_today`,
        `recent`, the hourly histogram and the funnel are all bounded by an
        index and answer in milliseconds; everything else scans the table and
        may only come from the parked snapshot.
        """
        live = self._requests_summary_compute(
            recent_limit=int(recent_limit),
            budget_seconds=REQUEST_SUMMARY_BUDGET_SECONDS,
            panels=REQUEST_SUMMARY_FAST_PANELS)

        snapshot = self.snapshot_state() or {}
        parked = snapshot.get("value") or {}
        computed_at = snapshot.get("computed_at")
        # What the background pass TRIED and could not read, versus what it has
        # not reached yet. A panel named in neither was read successfully, and
        # that — not the mere presence of a key — is what makes it resolved.
        snap_failed = {d.split(":")[0] for d in snapshot.get("degraded", ())}
        snap_skipped = set(snapshot.get("skipped", ()))

        for key in REQUEST_SNAPSHOT_KEYS:
            # MERGED keys are excluded here and handled below. `internal_noise`
            # is one of them, and leaving it in this loop was a real defect: the
            # parked object replaced the live one, taking the day half with it.
            if key in REQUEST_SNAPSHOT_MERGED_KEYS:
                continue
            if key in parked:
                live[key] = parked[key]

        # `internal_noise` is HALF live: today's keep-alive count is bounded by
        # the indexed day window and is read on the request path, while the
        # all-time count scans the table and comes from the snapshot. Replacing
        # the object wholesale would put a stale number where a fresh one was —
        # and so would a plain `update()`, which is what this did first. The
        # snapshot does not read the day half at all, so its `today` is None, and
        # `update()` copied that absence straight over the live reading. Measured
        # on the live board: `internal_noise.today` was None and `today_clean`
        # rendered „—" WHILE `today` was a real 22277 and `degraded` was empty,
        # because the panel HAD been read. An absence must never overwrite a
        # number we hold.
        parked_noise = parked.get("internal_noise")
        if isinstance(parked_noise, dict):
            noise = dict(live.get("internal_noise") or {})
            for key, value in parked_noise.items():
                if value is not None:
                    noise[key] = value
            live["internal_noise"] = noise

        # Live-first keys. A dash next to a value we actually hold is its own
        # kind of lie, so when the live read produced nothing and the snapshot
        # has a real number, use it — and drop the live failure marker with it,
        # since the panel is no longer unreadable. Its age is published
        # alongside.
        #
        # The test is the DEGRADED marker, not `is None`: the funnel is a map of
        # routes, so a failed read leaves a dict whose four values are all None
        # rather than a bare None. Testing `is None` therefore never fired, and
        # a real parked reading stayed invisible — which is the exact shape of
        # the defect this fallback exists to close.
        live_failed = {d.split(":")[0] for d in live.get("degraded", [])}
        borrowed = set()
        for key in REQUEST_SNAPSHOT_FALLBACK_KEYS:
            if not (key in live_failed or live.get(key) is None):
                continue
            if parked.get(key) is None:
                continue
            live[key] = parked[key]
            borrowed.add(key)

        # A panel the background pass has not read yet is not "empty" and not
        # "zero" — it is unreadable, and the payload says which one it was. A
        # panel that FAILED there is reported as a failure, not as "waiting":
        # those are different states with different remedies.
        degraded = [d for d in live.get("degraded", [])
                    if d.split(":")[0] not in borrowed]
        for panel in live.get("skipped", ()):
            if panel not in REQUEST_SNAPSHOT_PANELS:
                continue
            if panel in snap_failed:
                degraded.append(panel)
            elif panel in snap_skipped or not parked:
                degraded.append(panel + ":awaiting_snapshot")
        live["degraded"] = sorted(set(degraded))
        live["available"] = not live["degraded"]
        if borrowed:
            live["served_from_snapshot"] = sorted(borrowed)

        # Recomputed rather than copied: both halves are live now, and the
        # snapshot's own difference was taken against the day-count as it stood
        # at snapshot time.
        noise = live.get("internal_noise") or {}
        today, noise_today = live.get("today"), noise.get("today")
        live["today_clean"] = (None if today is None or noise_today is None
                               else max(0, today - noise_today))

        live["snapshot_age_seconds"] = (
            None if computed_at is None
            else max(0, int(time.time() - float(computed_at))))
        live["snapshot_computed_at"] = computed_at
        # The CLASS of the last failed pass, never its message: a reader who sees
        # "awaiting" for ever deserves to know whether it is still coming or has
        # been failing, and an operator needs something to grep for. The text of
        # a driver error can carry a DSN, so it stays in the log.
        live["snapshot_error"] = self._snapshot_last_error
        live.pop("skipped", None)
        return live

    # ── the heavy half, computed out of band ────────────────────────────────
    @contextlib.contextmanager
    def _private_runner(self):
        """A statement runner that does NOT use the shared Postgres link.

        Two reasons, and either one alone would be enough:

        `_run` holds `_pg_lock` for the whole statement. The snapshot pass reads
        eight full scans at up to minutes each, so routing them through it would
        queue every fast dashboard panel behind them and re-create the 05.11
        outage deliberately.

        And the shared connection carries `KRISTO_PG_STATEMENT_TIMEOUT_MS` (8s),
        which is what was actually killing these reads — postgres cancelled
        `total` and friends at 8 seconds, so no budget on our side could ever
        have read them. This connection carries the snapshot's own, longer
        ceiling.

        Same door `_ensure_whaleflow_indexes` already uses for its
        `CREATE INDEX CONCURRENTLY`. On SQLite there is no shared link to
        contend for, so the ordinary runner is fine and the tests stay simple.
        """
        if self.backend != "postgresql":
            yield self._run
            return
        conn = None
        try:
            # Through `_pg_open`, the one place a Postgres link is made, so this
            # connection cannot drift from the shared one on the two dialect
            # rules that must hold for both: the dict row factory the panel
            # readers index by name, and the `set_config` form of the statement
            # timeout. Opening it by hand here is what let it drift once already
            # and killed the pass with a TypeError before it read a row.
            conn = self._pg_open(REQUEST_SNAPSHOT_STATEMENT_TIMEOUT_MS)

            def runner(sql, params=(), fetch=""):
                with conn.cursor() as cur:
                    cur.execute(self._q(sql), params)
                    rows = (cur.fetchall() if fetch == "all"
                            else cur.fetchone() if fetch == "one" else None)
                    rowcount = cur.rowcount
                conn.commit()
                return rows, rowcount

            yield runner
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    def snapshot_state(self) -> Dict[str, Any]:
        """The parked heavy panels and when they were read.

        Memory first, then the durable row: this instance restarts often, and
        re-reading eight full scans from cold after every deploy would leave the
        board showing dashes for minutes each time.

        Returns `{}` when nothing has ever been computed — an empty snapshot is
        reported as unreadable panels, never as zero traffic.
        """
        with self._snapshot_lock:
            if self._snapshot_value is not None:
                return self._snapshot_value
        raw = None
        try:
            raw = self.get_durable_meta(REQUEST_SNAPSHOT_KEY)
        except Exception as exc:
            log.warning("requests snapshot unreadable (%s)", type(exc).__name__)
            return {}
        if not raw:
            return {}
        try:
            loaded = json.loads(raw)
        except Exception:
            log.warning("requests snapshot is not JSON — ignored")
            return {}
        if not isinstance(loaded, dict) or "value" not in loaded:
            return {}
        with self._snapshot_lock:
            self._snapshot_value = loaded
        return loaded

    def refresh_requests_snapshot(self, runner=None) -> Dict[str, Any]:
        """Read the heavy panels on a private connection and park them.

        Returns the parked snapshot. Never raises for a slow or failed read: a
        pass that dies part-way keeps whatever the store already had, so the
        board degrades to the previous all-time numbers instead of to dashes.
        Re-entrant calls are refused (single-flight) — two of these passes at
        once would double the load the snapshot exists to remove.

        `runner` overrides where the statements go, and exists so a caller that
        already has a working link can reuse it. The background warmer passes
        nothing and gets the private connection; a test whose backend is faked
        passes the store's own runner, so it exercises this exact parking logic
        without needing a socket to a database that is not there.
        """
        with self._snapshot_lock:
            if self._snapshot_refreshing:
                return self._snapshot_value or {}
            self._snapshot_refreshing = True
        try:
            try:
                if runner is not None:
                    full = self._requests_summary_compute(
                        recent_limit=25,
                        budget_seconds=REQUEST_SNAPSHOT_BUDGET_SECONDS,
                        panels=REQUEST_SNAPSHOT_PANELS,
                        runner=runner)
                else:
                    with self._private_runner() as private:
                        full = self._requests_summary_compute(
                            recent_limit=25,
                            budget_seconds=REQUEST_SNAPSHOT_BUDGET_SECONDS,
                            panels=REQUEST_SNAPSHOT_PANELS,
                            runner=private)
            except Exception as exc:
                # Remembered as a CLASS so the board can say "this has been
                # failing" instead of "this is still coming". Both look like a
                # dash, and only one of them is worth waiting for.
                self._snapshot_last_error = type(exc).__name__
                log.warning(
                    "requests snapshot pass failed (%s) — keeping the previous "
                    "one rather than blanking the board", type(exc).__name__)
                return self.snapshot_state()

            self._snapshot_last_error = None

            parked = {k: full.get(k) for k in REQUEST_SNAPSHOT_KEYS if k in full}
            # Panels this pass could not read are recorded BESIDE the values, so
            # the serve path can say "unreadable" for them instead of serving a
            # previous number as if it were current.
            parked_degraded = [p for p in full.get("degraded", ())
                               if p.split(":")[0] in REQUEST_SNAPSHOT_PANELS]
            parked_skipped = [p for p in full.get("skipped", ())
                              if p in REQUEST_SNAPSHOT_PANELS]
            payload = {
                "value": parked,
                "degraded": parked_degraded,
                "skipped": parked_skipped,
                "computed_at": time.time(),
            }
            try:
                self.set_durable_meta(REQUEST_SNAPSHOT_KEY,
                                      json.dumps(payload, default=str))
            except Exception as exc:
                log.warning("requests snapshot not persisted (%s) — kept in "
                            "memory only", type(exc).__name__)
            with self._snapshot_lock:
                self._snapshot_value = payload
            # Drop the served-summary TTL cache: it is holding the answer from
            # BEFORE these numbers existed, and replaying it for up to
            # REQUEST_SUMMARY_TTL_SECONDS would keep the board showing dashes
            # after the pass that filled them has already finished. A cache that
            # outlives the data it was cached alongside is just a delay.
            self._summary_value = None
            self._summary_at = 0.0
            return payload
        finally:
            with self._snapshot_lock:
                self._snapshot_refreshing = False

    def _requests_summary_compute(
            self, recent_limit: int = 25,
            budget_seconds: Optional[float] = None,
            panels: Optional[tuple] = None,
            runner=None) -> Dict[str, Any]:
        """today/total + channel (/f/<name>) + source breakdown.

        The internal keep-alive traffic (UA 'Render/1.0' — our own /health pings
        plus Render health checks) is counted SEPARATELY so the clean
        customer/agent-facing numbers light up on their own. Also aggregates the
        payment FUNNEL per paid route (402 challenges -> paid follow-ups,
        today + total) — the "caught by the hand" metric.
        """
        one = "one"
        all_ = "all"
        now = datetime.now(timezone.utc)
        today = now.strftime("%Y-%m-%d")
        tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
        # Sargable day window (option B, double-door 11.10): ts is a TEXT ISO
        # string, so the lexicographic range [today, tomorrow) matches exactly
        # the rows substr(ts, 1, 10) = today used to match — but lets
        # idx_request_log_ts serve the predicate instead of forcing a scan.
        day_params = (today, tomorrow)
        internal_sql = "user_agent LIKE 'Render/%'"

        degraded: List[str] = []
        # Panels deliberately NOT attempted on this pass. Kept separate from
        # `degraded` because they did not FAIL — the caller is going to supply
        # them from somewhere else (the snapshot). Conflating the two would
        # report a panel as broken when it was never asked for.
        skipped: List[str] = []
        # The snapshot pass hands in a runner on its OWN connection (see
        # `_private_runner`); everything else uses the shared link.
        run = runner if runner is not None else self._run
        deadline = time.monotonic() + (
            REQUEST_SUMMARY_BUDGET_SECONDS if budget_seconds is None
            else float(budget_seconds))

        def wanted(name) -> bool:
            """Is this panel being read on THIS pass?

            `panels=None` means every panel (the background snapshot pass, and
            the direct calls the tests make). A tuple restricts the pass to the
            panels that are cheap enough for the path it runs on.
            """
            return panels is None or name in panels

        def q(name, sql, params=(), fetch=one, default=None, budgeted=True):
            """Read ONE panel of the traffic summary, tolerantly.

            WHY THIS IS NOT A PLAIN `_run`. On 05.11 this method issued ten
            queries over `request_log` (~783K rows, and no retention anywhere).
            Several — `COUNT(*)` with no WHERE, and every GROUP BY — are full
            scans, and on this Postgres plan they ran for 10-21 SECONDS each.
            The first one to hit the 8s statement_timeout raised QueryCanceled,
            which failed the ENTIRE dashboard build, which meant the cache never
            filled, which meant every single request built again. That is how one
            slow panel took the whole board — and, for a while, the whole
            service — down.

            So a panel that cannot be read is REPORTED as unreadable. The rest of
            the board renders from real numbers and the payload names what is
            missing. `None` means "we could not read this"; it is NEVER a
            stand-in zero, because a zero here is a factual claim about traffic
            that we would be inventing.
            """
            if not wanted(name):
                skipped.append(name)
                return default
            if budgeted and time.monotonic() > deadline:
                degraded.append(name + ":out_of_budget")
                return default
            try:
                return run(sql, params, fetch)[0]
            except Exception as exc:
                degraded.append(name)
                log.warning(
                    "requests_summary[%s] unavailable (%s) — reported as "
                    "missing rather than taking the board down",
                    name, type(exc).__name__)
                return default

        def count(name, sql, params=(), default=None):
            """One COUNT(*) panel. Returns None when it could not be read.

            Subscripted rather than `.get()`-ed because the SQLite backend hands
            back `sqlite3.Row`, which has no `.get`.
            """
            row = q(name, sql, params, one)
            if row is None:
                return default
            try:
                return row["n"]
            except Exception:
                return default

        # Cheap and load-bearing first, so the board always has today's traffic,
        # the funnel and the recent log even if the all-time aggregates timeout.
        today_row = count("today", "SELECT COUNT(*) AS n FROM request_log "
                                   "WHERE ts >= ? AND ts < ?", day_params)
        recent = q("recent",
                   """SELECT ts, method, path, source, status_code, user_agent,
                             funnel
                      FROM request_log ORDER BY id DESC LIMIT ?""",
                   (recent_limit,), all_, []) or []
        hourly = q("hourly",
                   """SELECT substr(ts, 12, 2) AS hour, COUNT(*) AS n,
                             SUM(CASE WHEN user_agent LIKE 'Render/%'
                                      THEN 1 ELSE 0 END) AS noise
                      FROM request_log
                      WHERE ts >= ? AND ts < ?
                      GROUP BY substr(ts, 12, 2) ORDER BY hour""",
                   day_params, all_, []) or []
        by_path = q("by_path",
                    """SELECT path, COUNT(*) AS n FROM request_log
                       GROUP BY path ORDER BY n DESC LIMIT 10""",
                    (), all_, []) or []
        # ── what happened to the credentials that WERE presented (07.11) ─────
        # Read HERE, deliberately, and not next to the funnel it feeds.
        #
        # Every `q()` above and below spends from the same 6-second budget, and
        # the heavy all-time scans over request_log spend all of it. Reading this
        # panel where it is logically used put it LAST, where it was reported
        # `payment_attempts:out_of_budget` on the first live deploy of e3b3f65 —
        # the panel was never slow, it simply arrived after the money was gone.
        #
        # It is the cheapest read in this method: `path IN (...)` against
        # `idx_payment_attempts_path_ts` on a table that only ever holds attempts,
        # not traffic. So it goes early, where it always gets its turn.
        #
        # ONE read for both windows. `None` means the read FAILED; `[]` would mean
        # the table is empty, which is a measurement.
        _attempt_sql, _attempt_params = payment_attempt_sql(*day_params)
        attempt_rows = q("payment_attempts", _attempt_sql, _attempt_params,
                         all_, None)
        attempts_read = attempt_rows is not None
        by_channel = q("by_channel",
                       """SELECT funnel AS channel, COUNT(*) AS n
                          FROM request_log
                          WHERE funnel IS NOT NULL AND funnel <> ''
                          GROUP BY funnel ORDER BY n DESC""",
                       (), all_, []) or []
        by_source = q("by_source",
                      """SELECT source, COUNT(*) AS n FROM request_log
                         GROUP BY source ORDER BY n DESC""",
                      (), all_, []) or []
        by_source_clean = q("by_source_clean",
                            f"""SELECT source, COUNT(*) AS n FROM request_log
                                WHERE NOT ({internal_sql})
                                GROUP BY source ORDER BY n DESC""",
                            (), all_, []) or []
        top_user_agents = q("top_user_agents",
                            f"""SELECT user_agent, COUNT(*) AS n
                                FROM request_log
                                WHERE user_agent <> '' AND NOT ({internal_sql})
                                GROUP BY user_agent ORDER BY n DESC LIMIT 10""",
                            (), all_, []) or []
        noise_today = count("noise_today",
                            f"SELECT COUNT(*) AS n FROM request_log "
                            f"WHERE ts >= ? AND ts < ? AND {internal_sql}",
                            day_params)
        # The two unconditional counts are the worst offenders: COUNT(*) with no
        # WHERE cannot use any index, on any Postgres, ever. They go last.
        noise_total = count("noise_total",
                            f"SELECT COUNT(*) AS n FROM request_log "
                            f"WHERE {internal_sql}")
        total = count("total", "SELECT COUNT(*) AS n FROM request_log")

        # ── payment funnel per paid route: 402 challenges vs paid retries ──
        # One grouped scan instead of two full scans per route (option B,
        # double-door 11.10): 12 scans over request_log -> 1, served by
        # idx_request_log_path. Same numbers as the old per-path loop —
        # including the 13.09 bugfix where "today" must come from the TODAY
        # predicate, not from the all-time totals.
        # `abandoned` is derived from the 402 count, and the table that makes it
        # derivable did not exist before this moment. Read the epoch BEFORE the
        # query, because the window it defines is one of the things the query
        # counts: 402s recorded before it are 402s we cannot interpret.
        attempts_since = self.payment_attempts_since()
        placeholders = ", ".join("?" for _ in FUNNEL_ROUTES)

        def _f(row, key):
            """One column of a funnel row, tolerating a column that is absent.

            A PARKED SNAPSHOT IS WRITTEN BY THE PREVIOUS BUILD. `autoDeploy` is
            on, so every deploy restarts the service with a snapshot in Postgres
            that predates whatever columns this build just added — and a bare
            `row[key]` then raises KeyError and takes the whole panel down on
            boot. Absent means "that build never measured it", which is None, not
            zero.

            `.get()` cannot be used: the SQLite backend hands back `sqlite3.Row`,
            which has no `.get`.
            """
            if row is None:
                return None
            try:
                return row[key]
            except (KeyError, IndexError, TypeError):
                return None

        # ── what each status code actually means on the rail (verified 07.11) ──
        # The paywall is explicit about this and the funnel used to ignore it:
        #   402  NO credential was presented      -> the canonical challenge
        #   401  a credential WAS presented and we refused it (bad signature,
        #        or a settlement we could not take) — main.py:4092
        #   425  a settlement is on-chain but our node has not caught up (:4076)
        #   200  paid
        # So 402 isolates abandonment ALREADY, and the number that was missing is
        # the split of the 401s: a bad signature is routine, a settlement we
        # failed to take is a lost sale we caused.
        funnel_rows = q(
            "funnel",
            f"""SELECT path,
                       SUM(CASE WHEN status_code = 402 THEN 1 ELSE 0 END)
                           AS challenges,
                       SUM(CASE WHEN status_code = 200 THEN 1 ELSE 0 END)
                           AS paid,
                       SUM(CASE WHEN status_code = 402 AND ts >= ? AND ts < ?
                                THEN 1 ELSE 0 END) AS challenges_today,
                       SUM(CASE WHEN status_code = 200 AND ts >= ? AND ts < ?
                                THEN 1 ELSE 0 END) AS paid_today,
                       SUM(CASE WHEN status_code = 402 AND ts >= ?
                                THEN 1 ELSE 0 END) AS challenges_since,
                       SUM(CASE WHEN status_code IN (401, 425) AND ts >= ?
                                                      AND ts < ?
                                THEN 1 ELSE 0 END) AS credentials_today
                FROM request_log
                WHERE path IN ({placeholders})
                GROUP BY path""",
            (*day_params, *day_params, attempts_since or "9999-99-99",
             *day_params, *FUNNEL_ROUTES), all_, []) or []
        funnel_by_path = {r["path"]: r for r in funnel_rows}
        # An empty result and an unread result are NOT the same thing. If the
        # query was answered and a route is absent, that route genuinely has no
        # requests. If the query was never answered, reporting zeros would claim
        # nobody has ever paid on that route — a revenue statement we did not
        # measure.
        funnel_read = "funnel" not in degraded
        # `attempts_read` was set by the early read above; nothing to do here.

        def _bucket(rows, key):
            # `_f`, not `.get()`: a row read on the request path arrives as a
            # `sqlite3.Row`, which has no `.get`. `_f` also tolerates a column
            # this build added but the row's query did not select.
            out: Dict[str, Dict[str, int]] = {}
            for row in (rows or []):
                out.setdefault(_f(row, "path") or "", {})[
                    _f(row, "outcome") or ""] = int(_f(row, key) or 0)
            return out

        all_attempts = _bucket(attempt_rows, "n")
        today_attempts = _bucket(attempt_rows, "n_today")

        def _counts(bucket: Dict[str, int]) -> Dict[str, Optional[int]]:
            """The four outcomes for one route, or all None when unread."""
            if not (attempts_read and funnel_read):
                return {k: None for k in
                        ("presented", "authorised", "settled", "rejected",
                         "settle_failed")}
            return {
                "presented": sum(int(bucket.get(o) or 0)
                                 for o in PAYMENT_ATTEMPT_OUTCOMES),
                "authorised": int(bucket.get("authorised") or 0),
                "settled": int(bucket.get("settled") or 0),
                "rejected": int(bucket.get("rejected") or 0),
                "settle_failed": int(bucket.get("settle_failed") or 0),
            }

        funnel = {}
        for path in FUNNEL_ROUTES:
            cur = funnel_by_path.get(path)
            at_all = _counts(all_attempts.get(path, {}))
            at_today = _counts(today_attempts.get(path, {}))

            if cur is None and not funnel_read:
                # The 402 count could not be read, so abandonment — which IS
                # that count — is unknown. Report EVERY field unread rather than
                # a zero, which would state that nobody walked away from a route
                # we failed to measure.
                #
                # Including `measured_since`, even though that date was readable:
                # the panel is one reading, and a lone date beside a column of
                # dashes invites the reader to attach it to a number that is not
                # there. `test_the_parked_funnel_is_never_used_to_invent_zero`
                # enforces this — an unread panel reports nothing but None.
                funnel[path] = {
                    "challenges_total": None, "paid_total": None,
                    "challenges_today": None, "paid_today": None,
                    "presented_total": None,
                    "presented_today": None,
                    "authorised_today": None,
                    "settled_total": None,
                    "settled_today": None,
                    "rejected_today": None,
                    "settle_failed_today": None,
                    "abandoned_today": None,
                    "abandoned_total": None,
                    "credentials_today": None,
                    "unrecorded_today": None,
                    "measured_since": None,
                    "challenges_since": None,
                }
                continue

            challenges_today = _f(cur, "challenges_today") or 0
            challenges_total = _f(cur, "challenges") or 0
            # 402s from the moment attempts started being recorded — the window
            # over which the attempt split below can be trusted.
            challenges_since = _f(cur, "challenges_since") or 0
            credentials_today = _f(cur, "credentials_today") or 0

            # ── abandonment, read straight off the status code ───────────────
            # A 402 means NO credential was presented: the paywall issues it at
            # main.py:4127, on the path taken only when neither the standard
            # header nor a legacy proof was present. So the 402 count already IS
            # the abandonment count, and it needs no attempt data to interpret.
            #
            # This is deliberately NOT `challenges - rejected - settle_failed`.
            # Those two outcomes answer 401 (main.py:4092), so they were never
            # inside the 402 count — subtracting them would UNDER-count
            # abandonment by exactly the number of buyers who tried. The first
            # draft of this block did that; the rail tests caught it.
            abandoned_today = challenges_today
            abandoned_total = challenges_total

            # ── the reconciliation ───────────────────────────────────────────
            # `credentials_today` counts the 401/425 responses in request_log —
            # requests that DID carry a credential. Every one of them should have
            # produced exactly one attempt row. A gap means a call site on the
            # rail stopped recording, which would quietly flatten this panel, so
            # the gap is published rather than hidden.
            #
            # Only meaningful once recording covers the whole day; before that
            # the gap is unmeasured history, not a defect.
            unrecorded_today = None
            if attempts_read and attempts_since and attempts_since <= today:
                if at_today["presented"] is not None:
                    unrecorded_today = max(
                        0, credentials_today - at_today["presented"])

            funnel[path] = {
                "challenges_total": challenges_total,
                "paid_total": _f(cur, "paid") or 0,
                "challenges_today": challenges_today,
                "paid_today": _f(cur, "paid_today") or 0,
                # ── the missing middle ──────────────────────────────────────
                # How many DID present a credential, and how each one ended.
                # This is the part `request_log` could never say: 401 covers
                # both "your signature was wrong" (routine) and "we could not
                # take your valid payment" (a sale we lost).
                "presented_total": at_all["presented"],
                "presented_today": at_today["presented"],
                "authorised_today": at_today["authorised"],
                "settled_total": at_all["settled"],
                "settled_today": at_today["settled"],
                "rejected_today": at_today["rejected"],
                "settle_failed_today": at_today["settle_failed"],
                "abandoned_today": abandoned_today,
                "abandoned_total": abandoned_total,
                # 401/425 responses seen by request_log today, and how many of
                # them have no attempt row behind them.
                "credentials_today": credentials_today,
                "unrecorded_today": unrecorded_today,
                # The window the attempt split is measured over.
                "measured_since": attempts_since,
                "challenges_since": challenges_since,
            }

        def diff(a, b):
            """`a - b`, or None when either side could not be read.

            Deliberately not clamped to zero on missing input: `max(0, None - 3)`
            is not a number, and a zero here would be an invented claim about
            traffic rather than a missing one.
            """
            if a is None or b is None:
                return None
            return max(0, a - b)

        return {
            "today_date": today,
            "today": today_row,
            "total": total,
            "today_clean": diff(today_row, noise_today),
            "total_clean": diff(total, noise_total),
            # Named so the page can say "not read" instead of "no traffic".
            "degraded": degraded,
            "available": not degraded,
            # Panels this pass did not attempt because they are not cheap enough
            # for the path it runs on. The serve layer fills them from the
            # snapshot, or reports them unreadable if the snapshot has none.
            "skipped": skipped,
            "internal_noise": {
                "today": noise_today,
                "total": noise_total,
                "label": "вътрешен keep-alive (Render/1.0) — не е клиентски трафик",
            },
            "by_source": [dict(r) for r in by_source],
            "by_source_clean": [dict(r) for r in by_source_clean],
            "by_channel": [dict(r) for r in by_channel],
            "top_paths": [dict(r) for r in by_path],
            "top_user_agents": [dict(r) for r in top_user_agents],
            "hourly": [dict(r) for r in hourly],
            "funnel": funnel,
            "recent": [dict(r) for r in recent],
        }

    # ── whale flow reads ─────────────────────────────────────────────────────
    def purge_old_whale_events(self, days: int = WHALE_RETENTION_DAYS_DEFAULT) -> int:
        """Retention: delete whale rows older than `days` (idempotent).

        Runs at boot (main.py) next to the payer reclassify. Whale events are a
        ROLLING feed — the paid route serves a 24h window — so rows older than
        the retention horizon are ballast. This also bounds the table on the free
        Postgres plan: at the previous $50k threshold it reached 427 MB in under
        five days and would have hit the 1 GB cap in about a week.
        Returns the number of rows removed (0 on a second call = idempotent).
        """
        cutoff = (datetime.now(timezone.utc)
                  - timedelta(days=max(1, int(days)))).isoformat()
        _rows, rowcount = self._run(
            "DELETE FROM whaleflow_events WHERE ts < ?", (cutoff,))
        return max(0, rowcount)

    def purge_old_requests(self, days: int = REQUEST_LOG_RETENTION_DAYS_DEFAULT
                           ) -> int:
        """Retention: delete request_log rows older than `days` (idempotent).

        The counterpart of purge_old_whale_events, for the same reason and with
        a different justification for the horizon.

        `request_log` is an append-only traffic ledger, and it had no retention
        at all: it grew from the day the service started and never shrank. By
        07.11 it was the largest thing in the database, and the ten aggregates
        the dashboard runs over it were the single most expensive reads in the
        service — 10-21 seconds each, against an 8-second server statement
        timeout. That is what made one slow panel able to fail the whole board.

        WHY THE HORIZON IS SAFE HERE. The only window any query opens on this
        table is 24 hours (`timedelta(days=1)` — the traffic summary). Nothing
        reads a 7-day or 30-day slice. A 30-day horizon therefore deletes
        nothing that any surface would have shown, while giving the table the
        hard ceiling it never had.

        Batched, because the first run must delete a very large number of rows
        on a small database: one unbounded DELETE would hold a long lock and
        could itself exhaust memory, which is the failure this is meant to fix.
        `max(1, int(days))` mirrors the whale pass, so a 0 or negative value
        cannot mean "delete everything".

        Returns the number of rows removed (0 on a second call = idempotent).
        """
        horizon = (datetime.now(timezone.utc)
                   - timedelta(days=max(1, int(days)))).isoformat()
        removed = 0
        batch = 5000
        while True:
            _rows, rowcount = self._run(
                "DELETE FROM request_log WHERE id IN ("
                "  SELECT id FROM request_log WHERE ts < ? "
                "  ORDER BY id LIMIT ?)",
                (horizon, batch))
            rowcount = max(0, int(rowcount or 0))
            removed += rowcount
            if rowcount < batch:
                break
        return removed

    def whale_rows(self, window_hours: int, limit: int,
                   threshold: float) -> Dict[str, Any]:
        """The rolling whale window plus the honest empty-vs-all-time context."""
        cutoff = (datetime.now(timezone.utc)
                  - timedelta(hours=window_hours)).isoformat()
        rows = self._run(
            """SELECT ts, token, amount_usdc, from_addr, to_addr,
                      tx_hash, block_number
               FROM whaleflow_events
               WHERE ts >= ? AND amount_usdc >= ?
               ORDER BY ts DESC, block_number DESC LIMIT ?""",
            (cutoff, threshold, limit), "all")[0]
        all_time = self._run(
            """SELECT COUNT(*) AS n, MAX(ts) AS last_ts,
                      MAX(block_number) AS last_block
               FROM whaleflow_events WHERE amount_usdc >= ?""",
            (threshold,), "one")[0]
        whales = []
        for r in rows:
            whales.append({
                "ts": r["ts"],
                "token": r["token"],
                "amount_usdc": round(float(r["amount_usdc"]), 6),
                "from": r["from_addr"],
                "to": r["to_addr"],
                "from_label": _label_address(r["from_addr"]),
                "to_label": _label_address(r["to_addr"]),
                "tx_hash": r["tx_hash"],
                "block": r["block_number"],
            })
        return {
            "whales": whales,
            "all_time_count": all_time["n"] if all_time else 0,
            "last_event_at": all_time["last_ts"] if all_time else None,
            "last_event_block": (int(all_time["last_block"])
                                 if all_time and all_time["last_block"]
                                 else None),
        }

    # ── on-chain sales: the canonical MONEY table ───────────────────────────
    def record_sale(self, tx_hash: str, amount_usdc: float, sender: str = "",
                    block_number: int = 0, ts: Optional[datetime] = None,
                    source: str = "live") -> bool:
        """Insert one confirmed on-chain sale. True when it was new.

        Deduplicated by normalized tx hash (`ON CONFLICT (tx_hash) DO
        NOTHING` — valid in BOTH dialects, so there is one body and no drift):
        the settle path, the monitor and the seed can all see the same transfer
        and only the first insert counts.
        """
        tx = _norm_tx(tx_hash)
        if not tx:
            return False
        ts = ts or datetime.now(timezone.utc)
        payer_class, payer_label = classify_payer(sender)
        _, rowcount = self._run(
            """INSERT INTO onchain_sales
                   (tx_hash, block_number, ts, sender, amount_usdc,
                    payer_class, payer_label, source, recorded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (tx_hash) DO NOTHING""",
            (
                tx,
                int(block_number or 0),
                ts.astimezone(timezone.utc).isoformat(),
                (sender or "").lower(),
                round(float(amount_usdc), 6),
                payer_class,
                payer_label,
                source,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        return rowcount > 0

    def seed_verified_sales(
        self, rows: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """BOOTSTRAP the chain-verified manifest. Deliberately NOT a cover-up.

        Every row in `integrations.verified_sales.VERIFIED_SALES` came off the
        chain (full 66-char hashes, cross-verified against RPC receipts by
        scripts/_verify_seed_chain.py), so writing them is legitimate. What is
        NOT legitimate is a seed that papers over reality, so this method has
        three properties and no others:

          1. BOOTSTRAP: an empty table (first boot, or a fresh database after
             the move to a durable backend) gets every manifest row. On Render
             this runs at import time in main.py, i.e. BEFORE the app accepts a
             single connection — so the dashboard cannot serve a sub-$0.031
             number even for one request.
          2. SELF-HEAL, NOT OVERWRITE: on a partially lost table only the
             MISSING rows are restored. Present rows are left exactly as they
             are, including their `source`, so a scan-discovered row always wins
             over this file. A stale hand-written manifest can never roll back
             what the chain actually said.
          3. NO DELETE, NO UPDATE, EVER: the only statement this method runs is
             the insert inside `record_sale`. There is no code path here that
             removes or edits a row.

        Returns {"inserted", "present", "total_usdc", "external_payers",
        "mode"} where mode is "bootstrap" | "self_heal" | "already_complete".
        The sales scan watermark is deliberately NOT touched.
        """
        if rows is None:
            from integrations.verified_sales import VERIFIED_SALES as rows  # type: ignore
        before = self.sales_summary(history_limit=1)["total_count"]
        inserted = 0
        for r in rows or []:
            ts = r.get("ts")
            if ts is None and r.get("ts_unix") is not None:
                ts = datetime.fromtimestamp(
                    int(r["ts_unix"]), tz=timezone.utc
                )
            if self.record_sale(
                tx_hash=r["tx_hash"],
                amount_usdc=float(r["amount_usdc"]),
                sender=r.get("sender", ""),
                block_number=int(r.get("block_number") or 0),
                ts=ts,
                source="seed_recovery",
            ):
                inserted += 1
        summary = self.sales_summary(history_limit=1)
        mode = ("bootstrap" if before == 0 and inserted
                else "self_heal" if inserted else "already_complete")
        log.info("Verified-sales seed [%s, %s]: %d inserted, %d present, "
                 "$%.6f USDC, %d external payers (insert-only: nothing "
                 "overwritten, relabelled or deleted).",
                 mode, self.backend, inserted, summary["total_count"],
                 summary["total_usdc"], summary["external_payers"])
        return {
            "inserted": inserted,
            "present": summary["total_count"],
            "total_usdc": summary["total_usdc"],
            "external_payers": summary["external_payers"],
            "mode": mode,
        }

    def reclassify_known_payers(self) -> int:
        """Re-apply the payer taxonomy to stored sales rows.

        The taxonomy evolves as new market infrastructure is fingerprinted;
        rows recorded before a wallet entered KNOWN_PAYERS keep their original
        (external) class until this runs. Returns the number of rows updated.
        """
        try:
            from scripts.competitor_recon import KNOWN_PAYERS
        except Exception:  # pragma: no cover - import fallback
            return 0
        updated = 0
        for sender, label in KNOWN_PAYERS.items():
            _, rowcount = self._run(
                """UPDATE onchain_sales
                   SET payer_class = ?, payer_label = ?
                   WHERE lower(sender) = ? AND payer_label <> ?""",
                (
                    PAYER_CLASSES.get(label, "sampler"),
                    label,
                    (sender or "").lower(),
                    label,
                ),
            )
            updated += max(0, rowcount)
        return updated
    def set_durable_meta(self, key: str, value: str) -> None:
        """Persist small operational state in the DURABLE store (see dashboard_meta)."""
        self._run(
            """INSERT INTO dashboard_meta (key, value, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT (key) DO UPDATE SET value = excluded.value,
                                               updated_at = excluded.updated_at""",
            (key, str(value), datetime.now(timezone.utc).isoformat()))

    def get_durable_meta(self, key: str,
                         default: Optional[str] = None) -> Optional[str]:
        """Read back durable operational state, or `default` when unset."""
        row = self._run("SELECT value FROM dashboard_meta WHERE key = ?",
                        (key,), "one")[0]
        return row["value"] if row else default

    # ── Sentinel PR watcher baseline (27.09, durable) ────────────────────────
    def get_pr_watch_state(self, pr_key: str) -> Optional[dict]:
        """Last observed `{status, mergeable_state}` for one watched PR.

        A MISSING row is a missing baseline — the watcher records the current
        state WITHOUT sending a message (this covers a brand-new PR added to
        WATCHED_PRS and a store that cannot be reached). Never invents a
        transition from nothing.
        """
        row = self._run(
            "SELECT status, mergeable_state FROM pr_watch_state "
            "WHERE pr_key = ?",
            (pr_key,), "one")[0]
        return dict(row) if row else None

    def set_pr_watch_state(self, pr_key: str, status: str,
                           mergeable_state: str = "") -> None:
        """Upsert the observed PR state — survives deploys (like payment_guards)."""
        self._run(
            """INSERT INTO pr_watch_state
                   (pr_key, status, mergeable_state, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT (pr_key) DO UPDATE SET
                   status = excluded.status,
                   mergeable_state = excluded.mergeable_state,
                   updated_at = excluded.updated_at""",
            (pr_key, status, mergeable_state or "",
             datetime.now(timezone.utc).isoformat()))

    def record_vip_invite(self, code: str, wallet: str, tx_hash: str = "",
                          chat_id: str = "", source: str = "onchain") -> bool:
        """Persist one VIP invite — 18.09: they lived in RAM and died with every
        deploy, so an invite issued minutes before a deploy vanished while the
        sale that paid for it stayed in Postgres. Same rule as the money: durable."""
        _rows, rowcount = self._run(
            """INSERT INTO vip_invites
                   (code, wallet, tx_hash, chat_id, created, used, source)
               VALUES (?, ?, ?, ?, ?, 0, ?)
               ON CONFLICT (code) DO NOTHING""",
            (code, (wallet or "").lower(), (tx_hash or "").lower(),
             str(chat_id or ""), datetime.now(timezone.utc).isoformat(), source))
        return rowcount > 0

    def vip_invite_by_code(self, code: str) -> Optional[dict]:
        row = self._run("SELECT code, wallet, tx_hash, chat_id, created, used, "
                        "source FROM vip_invites WHERE code = ?",
                        (code,), "one")[0]
        return dict(row) if row else None

    def vip_invite_for_wallet(self, wallet: str) -> Optional[dict]:
        """The invite issued to a wallet, if any (drives the 'already VIP' check)."""
        row = self._run("SELECT code, wallet, tx_hash, chat_id, created, used, "
                        "source FROM vip_invites WHERE wallet = ? "
                        "ORDER BY created DESC LIMIT 1",
                        ((wallet or "").lower(),), "one")[0]
        return dict(row) if row else None

    def mark_vip_invite_used(self, code: str) -> bool:
        _rows, rowcount = self._run(
            "UPDATE vip_invites SET used = 1 WHERE code = ? AND used = 0",
            (code,))
        return rowcount > 0

    def vip_invites_summary(self) -> Dict[str, Any]:
        """Counts for the status surfaces — durable, so a deploy cannot zero them."""
        total = self._run("SELECT COUNT(*) AS n FROM vip_invites", (), "one")[0]
        used = self._run("SELECT COUNT(*) AS n FROM vip_invites WHERE used = 1",
                         (), "one")[0]
        wallets = self._run("SELECT COUNT(DISTINCT wallet) AS n FROM vip_invites "
                            "WHERE wallet != ''", (), "one")[0]
        return {"total": total["n"] if total else 0,
                "used": used["n"] if used else 0,
                "wallets": wallets["n"] if wallets else 0}

    # ── public track record: signal_history (frozen rules, 18.09) ────────────
    _SIGNAL_COLS = ("id, asset, action, confidence, issued_at, price_at_issue, "
                    "vol_threshold, price_at_24h, move_pct, outcome, resolved_at, "
                    "resolution_source, frozen_on")

    def record_signal_issue(self, record_id: str, asset: str, action: str,
                            confidence: Any, issued_at: str,
                            price_at_issue: Optional[float],
                            vol_threshold: Optional[float],
                            outcome: str = "pending",
                            frozen_on: str = "") -> bool:
        """Write ONE immutable issue record (rules 2/4): the volatility is stored
        as computed at issue time and is never recomputed — a record whose
        threshold could move after the fact is not a track record."""
        _rows, rowcount = self._run(
            """INSERT INTO signal_history
                   (id, asset, action, confidence, issued_at, price_at_issue,
                    vol_threshold, price_at_24h, move_pct, outcome, resolved_at,
                    resolution_source, frozen_on)
               VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, NULL, NULL, ?)
               ON CONFLICT (id) DO NOTHING""",
            (record_id, (asset or "").lower(), action, confidence, issued_at,
             price_at_issue, vol_threshold, outcome, frozen_on))
        return rowcount > 0

    def signal_history_total(self) -> int:
        """EVERY row in the table, regardless of age or outcome (21.09).

        The public feed's `issued` counter used to be `rows + not_scored`, which
        counted fresh non-directional rows but not fresh directional ones — two
        meanings in one number. It is now the plain table count: how many signals
        were issued, full stop. The ≥24h filter decides what is SERVED, never what
        was ISSUED.
        """
        row = self._run("SELECT COUNT(*) AS n FROM signal_history", (), "one")[0]
        return row["n"] if row else 0

    def signal_history_exists(self, record_id: str) -> bool:
        """Is this asset+day already recorded? Cheap, and it lets the caller skip
        the expensive volatility fetch entirely — 4 CoinGecko calls a day instead
        of 4 every 5-minute cycle, which is what caused the 429 storm on 18.09."""
        row = self._run("SELECT 1 AS n FROM signal_history WHERE id = ?",
                        (record_id,), "one")[0]
        return bool(row)

    def signal_history_due(self, older_than_iso: str, limit: int = 50) -> List[dict]:
        """Records still unresolved whose 24h window has passed (rules 1/3)."""
        rows = self._run(
            "SELECT %s FROM signal_history WHERE outcome = 'pending' "
            "AND issued_at <= ? ORDER BY issued_at LIMIT ?" % self._SIGNAL_COLS,
            (older_than_iso, limit), "all")[0]
        return [dict(r) for r in (rows or [])]

    def resolve_signal(self, record_id: str, outcome: str,
                       price_at_24h: Optional[float], move_pct: Optional[float],
                       resolution_source: str, resolved_at: str) -> bool:
        """Fill in the verdict — only for a `pending` row, so a resolution is
        written once and never rewritten."""
        _rows, rowcount = self._run(
            """UPDATE signal_history
                  SET outcome = ?, price_at_24h = ?, move_pct = ?,
                      resolution_source = ?, resolved_at = ?
                WHERE id = ? AND outcome = 'pending'""",
            (outcome, price_at_24h, move_pct, resolution_source, resolved_at,
             record_id))
        return rowcount > 0

    def signal_history_rows(self, older_than_iso: str,
                            limit: int = 500) -> List[dict]:
        """The PUBLIC feed's rows: issued at least 24h ago, newest first."""
        rows = self._run(
            "SELECT %s FROM signal_history WHERE issued_at <= ? "
            "AND outcome != 'not_scored' ORDER BY issued_at DESC LIMIT ?"
            % self._SIGNAL_COLS, (older_than_iso, limit), "all")[0]
        return [dict(r) for r in (rows or [])]

    def signal_history_not_scored(self) -> int:
        """Issued signals with no direction: counted, never scored (rule 2)."""
        row = self._run("SELECT COUNT(*) AS n FROM signal_history "
                        "WHERE outcome = 'not_scored'", (), "one")[0]
        return row["n"] if row else 0

    def sale_by_tx(self, tx_hash: str) -> Optional[dict]:
        """The recorded sale for one tx hash, or None — used by the Telegram VIP
        claim path (18.09): a buyer who already paid sends their tx hash, and the
        bot must be able to say whether our monitor actually recorded it."""
        row = self._run(
            "SELECT tx_hash, amount_usdc, sender, ts, block_number, payer_class, "
            "payer_label, source FROM onchain_sales WHERE tx_hash = ?",
            ((tx_hash or "").lower(),), "one")[0]
        if not row:
            return None
        # Backend-agnostic: SQLite hands back sqlite3.Row, Postgres dict_row. A
        # positional zip() silently produced {column: column} on Postgres, i.e.
        # the VIP claim path would have answered "not found" for every real sale.
        return dict(row)



    def track_record(self, now: Optional[datetime] = None) -> Dict[str, Any]:
        """The business clock and its three numbers — DERIVED, never typed.

        The clock starts at the FIRST EXTERNAL payment: a human paying for a real
        product — not a canary (our own verification wallet) and not a market
        crawler. In our data that is 06.09.2026, tx 0xb881f9dcdd0d… from
        0x4db7aafbe7. Everything below is read from `onchain_sales`, the
        chain-verified money table, so the date cannot drift into "today" and no
        number can be hand-edited:

          * months_live      — months since that first external payment
          * paying_strangers — DISTINCT external senders, each with the date of
                               their first payment
          * retention        — payers who came back a SECOND time. Today nobody
                               has, so the answer is the literal "N/A" WITH the
                               reason attached: a blank or hidden retention field
                               would read as a good number, which is exactly the
                               class of phantom this dashboard exists to prevent.
        """

        def _parse(value: Optional[str]) -> Optional[datetime]:
            if not value:
                return None
            try:
                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except ValueError:
                return None
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

        def _short(addr: str) -> str:
            return ("%s…%s" % (addr[:6], addr[-4:])) if len(addr or "") > 12 else (addr or "")

        now = now or datetime.now(timezone.utc)
        rows = self._run(
            "SELECT ts, sender, tx_hash, amount_usdc FROM onchain_sales "
            "WHERE payer_class = 'external' ORDER BY ts", (), "all")[0] or []

        started = _parse(rows[0]["ts"]) if rows else None
        # Calendar days, not 24h blocks: "06.09 → 18.09" is 12 days to a human,
        # while (now - started).days would say 11 because the first payment landed
        # at 06:41 and the clock is read before that hour.
        days_live = max(0, (now.date() - started.date()).days) if started else 0

        payers: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            ts, sender = row["ts"], row["sender"]
            tx_hash, amount = row["tx_hash"], row["amount_usdc"]
            entry = payers.setdefault((sender or "").lower(), {
                "sender": (sender or "").lower(), "payments": 0,
                "first_paid_at": ts, "first_tx": tx_hash, "total_usdc": 0.0})
            entry["payments"] += 1
            entry["total_usdc"] = round(entry["total_usdc"] + float(amount or 0), 6)

        repeat = [p for p in payers.values() if p["payments"] > 1]
        if repeat:
            retention = "%d от %d" % (len(repeat), len(payers))
            retention_note = "повторна покупка: %s" % ", ".join(
                _short(p["sender"]) for p in repeat)
        else:
            retention = "N/A"
            retention_note = ("още нямаме втори път от нито един от %d-мата "
                              "платили непознати — показваме N/A, не 0%%"
                              % len(payers))

        return {
            "started_at": rows[0]["ts"] if rows else None,
            "started_date": started.strftime("%d.%m.%Y") if started else None,
            "started_payer": rows[0]["sender"] if rows else None,
            "started_tx": rows[0]["tx_hash"] if rows else None,
            "days_live": days_live,
            "months_live": round(days_live / 30.44, 1),
            "paying_strangers": len(payers),
            "payers": [
                {
                    "sender": p["sender"],
                    "short": _short(p["sender"]),
                    "first_paid_at": p["first_paid_at"],
                    "first_paid_date": (_parse(p["first_paid_at"]).strftime(
                        "%d.%m.%Y") if _parse(p["first_paid_at"]) else None),
                    "first_tx": p["first_tx"],
                    "payments": p["payments"],
                    "total_usdc": p["total_usdc"],
                }
                for p in payers.values()
            ],
            "retention": retention,
            "retention_note": retention_note,
            "repeat_payers": len(repeat),
            "sentence": (
                "Public track record started: %s (първото външно плащане, %s)"
                % (started.strftime("%d.%m.%Y") if started else "—",
                   _short(rows[0]["sender"]) if rows else "—")
            ),
        }

    def sales_summary(self, history_limit: int = 100) -> Dict[str, Any]:
        """Aggregate on-chain sales straight from the durable table."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        totals = self._run(
            """SELECT COUNT(*) AS n,
                      COALESCE(SUM(amount_usdc), 0.0) AS total
               FROM onchain_sales""", (), "one")[0]
        today_row = self._run(
            """SELECT COUNT(*) AS n,
                      COALESCE(SUM(amount_usdc), 0.0) AS total
               FROM onchain_sales WHERE substr(ts, 1, 10) = ?""",
            (today,), "one")[0]
        by_class = self._run(
            """SELECT payer_class, COUNT(*) AS n,
                      COALESCE(SUM(amount_usdc), 0.0) AS total
               FROM onchain_sales GROUP BY payer_class""", (), "all")[0]
        external_payers = self._run(
            """SELECT COUNT(DISTINCT sender) AS n FROM onchain_sales
               WHERE payer_class = 'external'""", (), "one")[0]
        history = self._run(
            """SELECT tx_hash, block_number, ts, sender, amount_usdc,
                      payer_class, payer_label, source
               FROM onchain_sales ORDER BY ts DESC, tx_hash DESC LIMIT ?""",
            (history_limit,), "all")[0]

        classes: Dict[str, Dict[str, Any]] = {}
        for row in by_class:
            classes[row["payer_class"]] = {
                "count": row["n"],
                "total_usdc": round(row["total"], 6),
            }
        return {
            "total_usdc": round(totals["total"], 6),
            "total_count": totals["n"],
            "today_usdc": round(today_row["total"], 6),
            "today_count": today_row["n"],
            "today_date": today,
            "by_class": classes,
            "external_payers": external_payers["n"],
            "history": [dict(r) for r in history],
        }

    def client_sales_rows(self) -> Tuple[list, list]:
        """(per-payer aggregates, per-payment detail) for EXTERNAL payers.

        Exposed separately because the route evidence lives in a second table,
        `payment_guards` (the granted claims), which is read through
        `guard_endpoint_map()` — the caller joins the two instead of this class
        pretending they are one.

        `GROUP BY sender` (NOT `lower(sender)`) because PostgreSQL requires every
        bare selected column to be grouped: selecting `sender` while grouping by
        `lower(sender)` raised psycopg GroupingError and turned
        /api/dashboard/data into HTTP 500 in production on 14.09 (SQLite silently
        allows it, which is exactly why the move exposed it). Grouping by the raw
        column is safe and case-insensitive-by-construction: `record_sale` stores
        the sender lowercased.
        """
        rows = self._run(
            """SELECT sender, COUNT(*) AS n,
                      COALESCE(SUM(amount_usdc), 0.0) AS total,
                      MIN(ts) AS first_ts, MAX(ts) AS last_ts
               FROM onchain_sales WHERE payer_class = 'external'
               GROUP BY sender
               ORDER BY total DESC, last_ts DESC""", (), "all")[0]
        detail = self._run(
            """SELECT tx_hash, sender, amount_usdc, ts, block_number,
                      payer_class
               FROM onchain_sales WHERE payer_class = 'external'
               ORDER BY ts ASC, block_number ASC""", (), "all")[0]
        return [dict(r) for r in rows], [dict(r) for r in detail]

    # ── C1 replay lock (fail-CLOSED) ────────────────────────────────────────
    def _remember_claim(self, tx: str) -> None:
        """Add a hash to the negative-only cache (never used to GRANT)."""
        if len(self._claimed_cache) >= self._claimed_cache_cap:
            self._claimed_cache.clear()
        self._claimed_cache.add(tx)

    def guard_claims_with_blocks(self, limit: int = 25) -> List[dict]:
        """Consumed claims that carry a finality anchor (block number + hash).

        Added 21.09 (Miguel's feedback): depth cannot see a reorg that keeps the
        height and changes the hash, so the confirming block is remembered and
        re-read later. Only rows with both fields are returned.
        """
        rows = self._run(
            "SELECT tx_hash, endpoint, block_number, block_hash, consumed_at "
            "FROM payment_guards WHERE block_number > 0 AND block_hash != '' "
            "ORDER BY consumed_at DESC LIMIT ?", (int(limit),), "all")[0]
        return [dict(r) for r in (rows or [])]

    def claim_payment_tx(self, tx_hash: str, endpoint: str = "",
                         payer: str = "", amount_usdc: float = 0.0,
                         block_number: int = 0, block_hash: str = "") -> bool:
        """Atomically CLAIM a settlement tx hash for exactly one paid call.

        Returns True only for the FIRST consumer of the hash. A replay — the same
        hash again, or the same hash re-pointed at another endpoint (H2) — is
        False, no matter which process asks.

        THREE PROPERTIES, in order of importance:

          1. FAIL-CLOSED. If the lock cannot be read or written, this returns
             False and the payment is REFUSED. An unreachable lock is a locked
             door: serving a request on an unverifiable replay proof is exactly
             the failure this guard exists to prevent.
          2. THE DATABASE IS THE TRUTH. The `INSERT ... ON CONFLICT DO NOTHING`
             row is authoritative and survives deploys, so a restart cannot
             resurrect a consumed proof.
          3. THE IN-RAM SET IS ONLY A FAST PATH. A cache HIT refuses immediately
             (no round-trip); a cache MISS still asks the database. The cache can
             therefore never grant access on its own — clearing or losing it is
             always safe.
        """
        tx = _norm_tx(tx_hash)
        if not tx:
            return False
        if tx in self._claimed_cache:          # fast path: already spent here
            return False
        row = (
            tx,
            (endpoint or "").strip(),
            (payer or "").lower(),
            round(float(amount_usdc or 0.0), 6),
            datetime.now(timezone.utc).isoformat(),
            int(block_number or 0),
            (block_hash or "").lower(),
        )
        try:
            _, rowcount = self._run(
                """INSERT INTO payment_guards
                       (tx_hash, endpoint, payer, amount_usdc, consumed_at,
                        block_number, block_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT (tx_hash) DO NOTHING""",
                row,
            )
        except Exception as exc:
            # FAIL-CLOSED. Say it loudly: every paid call is now refused, which
            # is the safe direction but is also an outage the owner must see.
            log.error("C1 replay lock UNREACHABLE (%s) — refusing every payment "
                      "until it recovers (fail-closed): %s", self.backend, exc)
            return False
        if rowcount > 0:
            self._remember_claim(tx)
            return True                            # we are the first consumer
        # Someone else holds it (another worker, or an earlier request): replay.
        self._remember_claim(tx)
        return False

    # ── C1 delivery state: a paid call stays recoverable until DELIVERED ────
    # Audit #4 / F3. C1 locks the PAYMENT (one tx, one call); the delivery
    # stamp decides whether a refused attempt is a TRUE replay (the product
    # went out → 401) or an owed retry (the response errored → admit one).
    def payment_guard_row(self, tx_hash: str) -> Optional[dict]:
        """The claim row for this tx, or None when it was never consumed."""
        tx = _norm_tx(tx_hash)
        if not tx:
            return None
        try:
            rows = self._run(
                "SELECT tx_hash, endpoint, payer, consumed_at, "
                "delivered_at, retry_claimed_at "
                "FROM payment_guards WHERE tx_hash = ?", (tx,), "all")[0]
        except Exception as exc:
            log.warning("payment_guard_row unavailable (%s): %s",
                        self.backend, exc)
            return None
        if not rows:
            return None
        row = dict(rows[0])                       # Row → dict: sweep-safe
        return {
            "tx_hash": row["tx_hash"],
            "endpoint": row["endpoint"],
            "payer": row["payer"],
            "consumed_at": row["consumed_at"],
            "delivered_at": row["delivered_at"],
            "retry_claimed_at": row["retry_claimed_at"],
        }

    def mark_payment_delivered(self, tx_hash: str) -> bool:
        """Stamp `delivered_at` — ONLY when a 2xx/3xx response was produced.

        First stamp wins (idempotent). A failed stamp is logged, never raised:
        the product is read-only data, so a missed stamp can at worst cost one
        duplicate delivery attempt — never money.
        """
        tx = _norm_tx(tx_hash)
        if not tx:
            return False
        try:
            _, rowcount = self._run(
                "UPDATE payment_guards SET delivered_at = ? "
                "WHERE tx_hash = ? AND delivered_at IS NULL",
                (datetime.now(timezone.utc).isoformat(), tx))
        except Exception as exc:
            log.warning("mark_payment_delivered failed (%s): %s",
                        self.backend, exc)
            return False
        return int(rowcount or 0) > 0

    def claim_payment_retry_slot(self, tx_hash: str, token: str) -> bool:
        """Atomically take THE recovery slot for an undelivered claim.

        The whole guard is one UPDATE: `delivered_at IS NULL AND
        retry_claimed_at IS NULL`. Two concurrent duplicates both observe a
        NULL slot, but only one UPDATE can match → at most ONE recovery
        attempt per payment in flight, and a delivered claim can never be
        taken back (fail-closed replay protection stays intact).
        """
        tx = _norm_tx(tx_hash)
        if not tx or not token:
            return False
        try:
            _, rowcount = self._run(
                "UPDATE payment_guards SET retry_claimed_at = ? "
                "WHERE tx_hash = ? AND delivered_at IS NULL "
                "AND retry_claimed_at IS NULL",
                (token, tx))
        except Exception as exc:
            log.warning("claim_payment_retry_slot unavailable (%s): %s",
                        self.backend, exc)
            return False                          # fail-closed on recovery too
        return int(rowcount or 0) > 0

    def release_payment_retry_slot(self, tx_hash: str, token: str) -> bool:
        """Free the slot when an attempt produced NO delivery (4xx/5xx)."""
        tx = _norm_tx(tx_hash)
        if not tx or not token:
            return False
        try:
            _, rowcount = self._run(
                "UPDATE payment_guards SET retry_claimed_at = NULL "
                "WHERE tx_hash = ? AND retry_claimed_at = ? "
                "AND delivered_at IS NULL",
                (tx, token))
        except Exception as exc:
            log.warning("release_payment_retry_slot failed (%s): %s",
                        self.backend, exc)
            return False
        return int(rowcount or 0) > 0

    def payment_guard_stats(self) -> Dict[str, Any]:
        """Guard telemetry for the dashboard / ops (no PII).

        READ-ONLY and RESILIENT: a broken backend must not take the dashboard
        down — on 14.09 exactly that happened (a GroupingError on the sales
        aggregate turned /api/dashboard/data into HTTP 500). It reports the
        failure instead of pretending the numbers are zero.
        """
        base: Dict[str, Any] = {
            # Say WHERE the lock lives: "the lock is durable" holds only when this
            # is postgresql.
            "lock_backend": self.backend,
            "lock_durable": self.backend == "postgresql",
        }
        try:
            n = self._run("SELECT COUNT(*) AS n FROM payment_guards",
                          (), "one")[0]
            by_ep = self._run(
                """SELECT endpoint, COUNT(*) AS n FROM payment_guards
                   GROUP BY endpoint""", (), "all")[0]
            last = self._run(
                """SELECT consumed_at, endpoint FROM payment_guards
                   ORDER BY consumed_at DESC LIMIT 1""", (), "one")[0]
        except Exception as exc:
            log.warning("payment_guard_stats unavailable (%s): %s",
                        self.backend, exc)
            return {**base, "consumed_total": None, "by_endpoint": {},
                    "last_claim_at": None, "last_claim_endpoint": None,
                    "stats_error": str(exc)[:200]}
        return {
            **base,
            "consumed_total": n["n"] if n else 0,
            "by_endpoint": {(r["endpoint"] or "unknown"): r["n"]
                            for r in by_ep},
            "last_claim_at": last["consumed_at"] if last else None,
            "last_claim_endpoint": last["endpoint"] if last else None,
            "stats_error": None,
        }

    def record_guard_event(self, kind: str, endpoint: str = "",
                           tx_hash: str = "", detail: str = "") -> None:
        """Persist a guard rejection (C1 replay / C2 depth / H2 binding).

        Deliberately separate from `payment_guards` (which records GRANTED
        claims): the dashboard needs to prove the guards are alive, and a
        blocked attempt is the only positive evidence that they fired.
        Never raises — telemetry must not affect a payment decision.
        """
        try:
            self._run(
                """INSERT INTO guard_events
                       (ts, kind, endpoint, tx_hash, detail)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    datetime.now(timezone.utc).isoformat(),
                    (kind or "")[:40],
                    (endpoint or "")[:120],
                    _norm_tx(tx_hash)[:80],
                    (detail or "")[:300],
                ),
            )
        except Exception as exc:  # pragma: no cover - telemetry only
            log.debug("guard event not recorded (%s): %s", kind, exc)

    def record_payment_attempt(self, path: str, outcome: str, payer: str = "",
                               amount_usdc: float = 0.0, detail: str = "",
                               tx_hash: str = "") -> None:
        """Record that a buyer PRESENTED a payment credential, and how it went.

        This is the funnel's missing middle. `request_log` records the RESPONSE,
        and the paywall answers 401 both to a garbage signature and to a valid
        signature whose settlement failed. Two opposite facts — the client is
        buggy, versus WE dropped a sale — collapse into one status code, and only
        this table can tell them apart.

        Four outcomes, deliberately distinct:

          authorised    — credential arrived and verified; outcome undetermined
          rejected      — credential arrived and did NOT verify
          settle_failed — verified, but the facilitator could not settle it
          settled       — verified and settled

        `settle_failed` is the one that matters: it is a lost sale we caused.
        `rejected` is routine and mostly noise.

        ABANDONMENT IS NOT RECORDED HERE. A 402 means no credential was
        presented at all, so the funnel reads abandonment straight off the 402
        count in `request_log` — which also means it survives this table breaking
        entirely. An earlier draft derived abandonment by subtracting these
        outcomes from the 402 count; because they answer 401 and were never in
        that count, the subtraction under-counted it. See PAYMENT_ATTEMPT_OUTCOMES.

        Outcome is validated against the known set: an unrecognised string is
        recorded as `rejected` rather than trusted, because a typo silently
        creating a fifth state would corrupt every later aggregate.

        Never raises — telemetry must not be able to fail a payment.
        """
        outcome = (outcome or "").strip().lower()
        if outcome not in _PAYMENT_ATTEMPT_OUTCOMES:
            log.debug("payment attempt outcome %r not recognised; recording as "
                      "rejected", outcome)
            outcome = "rejected"
        try:
            self._run(
                """INSERT INTO payment_attempts
                       (ts, path, outcome, payer, amount_usdc, detail, tx_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    datetime.now(timezone.utc).isoformat(),
                    (path or "")[:120],
                    outcome,
                    (payer or "")[:80],
                    float(amount_usdc or 0.0),
                    (detail or "")[:300],
                    _norm_tx(tx_hash)[:80],
                ),
            )
        except Exception as exc:  # pragma: no cover - telemetry only
            log.debug("payment attempt not recorded (%s): %s", outcome, exc)

    def payment_attempt_rows(self, since: str = "",
                             until: str = "") -> Optional[List[dict]]:
        """Per-path, per-outcome attempt counts for BOTH windows, or None.

        Returns rows carrying `path`, `outcome`, `n` (all time) and `n_today`
        (inside `since`/`until`). One scan rather than two, because the request
        path runs on a query BUDGET — three extra reads for one panel is how the
        05.11 outage started.

        RESTRICTED TO FUNNEL_ROUTES. An unrestricted `GROUP BY path` over an
        ever-growing table is the exact read that took the service down: it can
        use no index and scans every row. `path IN (...)` is served by
        `idx_payment_attempts_path_ts`, and the funnel only ever asks about those
        routes anyway. `tests/test_request_summary_degradation.py` enforces this
        and caught the first draft without it.

        Returns None — NOT `[]` — when the read fails. `[]` means "the table was
        read and is empty", which is a measurement; None means we could not look.
        Collapsing those two is the defect this whole file keeps closing.

        NOTE: the request path does NOT call this. It issues the same SQL through
        the budgeted `q()` wrapper in `requests_summary`, because a read that
        skips the budget is the shape of the 05.11 outage. Keep the SQL in
        `payment_attempt_sql` so the two cannot drift.
        """
        sql, params = payment_attempt_sql(since, until)
        try:
            return [dict(r) for r in (self._run(sql, params, "all")[0] or [])]
        except Exception as exc:
            log.debug("payment attempt read failed: %s", exc)
            return None

    def payment_attempts_readable(self) -> bool:
        """Whether `payment_attempts` can actually be read.

        Separate from `payment_attempt_rows() == []` on purpose: an empty result
        and an unreadable table are the two states this whole codebase keeps
        insisting must never be collapsed. The funnel marks the panel unread
        rather than reporting a zero.
        """
        return self.payment_attempt_rows() is not None

    def payment_attempts_since(self) -> Optional[str]:
        """When attempt recording began, or None if that was never recorded.

        The window the ATTEMPT SPLIT is measured over, not the window
        abandonment is measured over: abandonment is the 402 count and does not
        depend on this table. Before this moment, `request_log` still saw the
        401s but nothing recorded what was behind them, so the reconciliation
        between the two must stay silent rather than report a recording defect.
        """
        try:
            row = self._run("SELECT value FROM dashboard_meta WHERE key = ?",
                            (PAYMENT_ATTEMPTS_SINCE_KEY,), "one")[0]
            return (row["value"] or None) if row else None
        except Exception as exc:
            log.debug("payment attempts epoch read failed: %s", exc)
            return None

    def probe_replay_lock(self, force: bool = False,
                          probe_ttl_seconds: float = 600.0) -> bool:
        """Prove the C1 replay lock can still write. Returns whether it can.

        Writes a sentinel row into `payment_guards`, reads it back and removes
        it, so a broken / locked / read-only lock reports red instead of silently
        letting every replay through. A failure here is also exactly the
        condition under which `claim_payment_tx` starts refusing payments
        (fail-closed), so the dashboard shows that state instead of hiding it.

        The probe is deliberately TIME-driven, not request-driven (F-04): at most
        one probe per `probe_ttl_seconds`, no matter how often the caller asks.
        `/api/dashboard/data` is free and unbounded, so a probe that ran per call
        let an anonymous poller churn INSERT/DELETE on the replay table and
        contend for the very lock a paying customer needs. With a TTL, more
        polling cannot produce more writing.

        `force=True` is for the background loop and for scripts that want a fresh
        answer; the read path never forces one.
        """
        now = time.monotonic()
        with self._probe_lock:
            fresh = (self._probe_alive is not None
                     and (now - self._probe_at) < probe_ttl_seconds)
            if fresh and not force:
                return bool(self._probe_alive)

            alive = False
            error = ""
            sentinel = "__lock_probe__"
            try:
                self._run("DELETE FROM payment_guards WHERE tx_hash = ?",
                          (sentinel,))
                self._run(
                    """INSERT INTO payment_guards
                           (tx_hash, endpoint, payer, amount_usdc, consumed_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (sentinel, "", "", 0.0,
                     datetime.now(timezone.utc).isoformat()),
                )
                row = self._run(
                    "SELECT COUNT(*) AS n FROM payment_guards WHERE tx_hash = ?",
                    (sentinel,), "one")[0]
                alive = bool(row and row["n"] == 1)
                self._run("DELETE FROM payment_guards WHERE tx_hash = ?",
                          (sentinel,))
            except Exception as exc:
                error = str(exc)[:200]

            self._probe_at = now
            self._probe_alive = alive
            self._probe_error = error
            return alive

    def guard_stats(self, recent_limit: int = 5) -> Dict[str, Any]:
        """Live health of the C1 replay lock + the blocked attempts it made.

        `lock_alive` comes from `probe_replay_lock()`, which is real but cached
        for a TTL — see that method for why the probe must not run per request.
        The rest of this method is read-only.
        """
        alive = self.probe_replay_lock()
        probe_error = self._probe_error

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            by_kind = self._run(
                """SELECT kind, COUNT(*) AS n FROM guard_events
                   GROUP BY kind ORDER BY n DESC""", (), "all")[0]
            # "Blocked" must mean REFUSED (21.09). It used to be COUNT(*) of every
            # guard event, which counted `waited_and_accepted` — an ACCEPTANCE that
            # the lag fix rescued — as a block. Two meanings in one number, the same
            # disease `totals.issued` had. The two families are counted separately:
            #   * blocked  = a refusal (C2 depth, node lag that survived the wait,
            #                C1 replay, H2 binding)
            #   * accepted = the clock was re-read/waited and the payment let in
            # Any NEW kind lands in neither, and stays visible in `by_kind`.
            _refusal = ("kind LIKE 'c2_insufficient%' OR kind LIKE 'node_lagging%' "
                        "OR kind = 'c1_replay' OR kind LIKE 'h2_%'")
            _accepted = "kind LIKE '%_and_accepted'"
            totals = dict(self._run(
                "SELECT SUM(CASE WHEN %s THEN 1 ELSE 0 END) AS blocked, "
                "SUM(CASE WHEN %s THEN 1 ELSE 0 END) AS accepted, "
                "COUNT(*) AS total FROM guard_events" % (_refusal, _accepted),
                (), "one")[0] or {})
            today_row = dict(self._run(
                "SELECT SUM(CASE WHEN %s THEN 1 ELSE 0 END) AS blocked, "
                "SUM(CASE WHEN %s THEN 1 ELSE 0 END) AS accepted, "
                "COUNT(*) AS total FROM guard_events WHERE substr(ts, 1, 10) = ?"
                % (_refusal, _accepted), (today,), "one")[0] or {})
            # dict(row) is not cosmetic: SQLite hands back sqlite3.Row, Postgres a
            # dict, and Row has NO .get() — reading these positionally (or via
            # .get) silently took the whole section down to zeros. Same lesson as
            # sale_by_tx earlier the same day.
            total_blocked = {"n": totals.get("blocked") or 0}
            blocked_today = {"n": today_row.get("blocked") or 0}
            lag_accepted_total = totals.get("accepted") or 0
            lag_accepted_today = today_row.get("accepted") or 0
            recent = self._run(
                """SELECT ts, kind, endpoint, tx_hash, detail FROM guard_events
                   ORDER BY id DESC LIMIT ?""", (recent_limit,), "all")[0]
        except Exception as exc:  # pragma: no cover - display only
            log.debug("guard event stats unavailable: %s", exc)
            by_kind, total_blocked, blocked_today, recent = [], None, None, []
            lag_accepted_total = lag_accepted_today = 0
        return {
            "lock_alive": alive,
            "lock_probe_error": probe_error or None,
            "lock_backend": self.backend,
            "lock_durable": self.backend == "postgresql",
            "blocked_total": total_blocked["n"] if total_blocked else 0,
            "blocked_today": blocked_today["n"] if blocked_today else 0,
            # The OTHER half of the same ledger: payments the clock re-read or the
            # wait rescued — served, not blocked (21.09).
            "lag_accepted_total": lag_accepted_total,
            "lag_accepted_today": lag_accepted_today,
            "by_kind": {r["kind"]: r["n"] for r in by_kind},
            "recent_blocks": [dict(r) for r in recent],
        }

    def guard_endpoint_map(self) -> Dict[str, str]:
        """{tx_hash → endpoint} for every GRANTED claim (route evidence).

        Used to name the route a payment was consumed on. Read from the same
        backend as the lock itself — reading it from a different database is how
        the CLIENTS section silently loses its evidence.
        """
        rows = self._run(
            "SELECT tx_hash, endpoint FROM payment_guards", (), "all")[0]
        return {(r["tx_hash"] or "").lower(): (r["endpoint"] or "")
                for r in rows}


class DashboardStore:
    """Canonical dashboard store (one connection per call, like CRMStore).

HYBRID since 14.09:
  * DURABLE (PostgreSQL when DATABASE_URL is set, SQLite otherwise) — the
    canonical MONEY table `onchain_sales`, the C1 replay lock `payment_guards`
    (+ `guard_events` telemetry) and the request_log / whaleflow_events
    histories, all owned by HistoryStore. A deploy can neither zero the numbers
    nor reopen a consumed payment proof.
  * LOCAL SQLite file — only the operational state whose loss is survivable:
    payapi_state and meta (scan watermarks).
"""

    def __init__(self, file_path: str | Path | None = None):
        self.file_path = Path(
            file_path or os.getenv("KRISTO_DASHBOARD_DB") or default_db_path()
        )
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.Lock()
        self._ensure_db()
        # request_log + whaleflow_events + onchain_sales + payment_guards follow
        # DATABASE_URL (PostgreSQL when set, SQLite otherwise), so HISTORY, THE
        # MONEY TABLE and THE REPLAY LOCK all survive a deploy — see HistoryStore.
        # The on-chain numbers used to be re-created from the seed manifest on
        # every boot; they now simply persist, and the seed is only the first-boot
        # bootstrap. The lock used to be reopened by every deploy.
        self.history = HistoryStore(
            self._connect, self._write_lock,
            os.getenv("DATABASE_URL", ""),
        )

    @property
    def backend(self) -> str:
        """Which engine owns the DURABLE tables: `"postgresql"` or `"sqlite"`.

        The dashboard used to label the request log `"постоянен лог (SQLite)"`
        hard-coded, which described the fallback as if it were the live engine.
        On production the durable store has been PostgreSQL since 14.09
        (`Durable store ready (postgresql)` at boot), so the label told the
        operator that the traffic history lived in a file that a deploy could
        erase — the opposite of why the table was moved there.

        The label is derived from the store rather than repeated as a literal so
        it cannot go stale again: if `DATABASE_URL` ever goes missing, the
        dashboard says SQLite because that is then the truth.
        """
        return self.history.backend

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.file_path), timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_db(self) -> None:
        # Only the LOCAL, survivable tables live here: the PayAPI listing state
        # and the scan watermarks. request_log, whaleflow_events, onchain_sales,
        # payment_guards and guard_events are ALL owned by HistoryStore (both
        # dialects), so there is exactly ONE definition of each and the backends
        # cannot drift — including a dead empty table shadowing the real one.
        with self._connect() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS payapi_state (
                    key        TEXT PRIMARY KEY,
                    value      TEXT,
                    updated_at TEXT
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS meta (
                    key   TEXT PRIMARY KEY,
                    value TEXT
                )"""
            )
            conn.commit()

    # ── meta (watermarks, flags) ──────────────────────────────────────────────
    def reclassify_known_payers(self) -> int:
        """Re-apply the payer taxonomy — see HistoryStore.reclassify_known_payers.

        Kept as a thin wrapper (14.09) so every call site keeps working now that
        the sales rows live in the durable store rather than the local file.
        """
        return self.history.reclassify_known_payers()

    def purge_old_whale_events(self, days: int = WHALE_RETENTION_DAYS_DEFAULT) -> int:
        """Retention pass — see HistoryStore.purge_old_whale_events (30 days)."""
        return self.history.purge_old_whale_events(days)

    def purge_old_requests(self,
                           days: int = REQUEST_LOG_RETENTION_DAYS_DEFAULT) -> int:
        """Retention pass — see HistoryStore.purge_old_requests (30 days).

        The traffic ledger is the other unbounded table. The whale feed needed
        retention because it was a storage hazard; this one needs it because the
        dashboard's ten aggregates over it were the slowest reads in the
        service, and a table that only ever grows makes that worse every day.
        """
        return self.history.purge_old_requests(days)

    #: Meta keys that MUST survive a deploy. Render wipes the local file, and
    #: auto-deploy is on: every push used to reset the whale watermark, which
    #: re-scanned 24h of chain (~900 getLogs) and left the PAID feed ~35 minutes
    #: behind reality. These live in the durable store; the local file is kept in
    #: sync as a fallback (and for the ephemeral-disk deployments).
    DURABLE_META_KEYS = ("whaleflow_last_block", "whaleflow_safe_scanned_block",
                         "whaleflow_effective_chunk")

    def get_meta(self, key: str, default: Optional[str] = None) -> Optional[str]:
        if key in self.DURABLE_META_KEYS:
            try:
                value = self.history.get_durable_meta(key)
                if value not in (None, ""):
                    return value
            except Exception as exc:            # never break a read over this
                log.debug("durable meta read failed for %s: %s", key, exc)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM meta WHERE key = ?", (key,)
            ).fetchone()
        return row["value"] if row else default

    def set_meta(self, key: str, value: str) -> None:
        if key in self.DURABLE_META_KEYS:
            try:
                self.history.set_durable_meta(key, value)
            except Exception as exc:            # the local write below still runs
                log.debug("durable meta write failed for %s: %s", key, exc)
        with self._write_lock, self._connect() as conn:
            conn.execute(
                """INSERT INTO meta (key, value) VALUES (?, ?)
                   ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
                (key, str(value)),
            )
            conn.commit()

    # ── on-chain sales ────────────────────────────────────────────────────────
    def record_sale(
        self,
        tx_hash: str,
        amount_usdc: float,
        sender: str = "",
        block_number: int = 0,
        ts: Optional[datetime] = None,
        source: str = "live",
    ) -> bool:
        """Insert one confirmed on-chain sale — see HistoryStore.record_sale.

        Thin wrapper (14.09): the MONEY table moved to the durable store (same
        backend as request_log/whaleflow_events) so a deploy cannot zero it, and
        the settle path / monitor / scanner keep calling the same method.
        """
        return self.history.record_sale(
            tx_hash, amount_usdc, sender=sender, block_number=block_number,
            ts=ts, source=source,
        )

    def seed_verified_sales(self, rows: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """BOOTSTRAP the chain-verified manifest — see HistoryStore.

        Thin wrapper (14.09). On the durable backend this runs on a genuinely
        EMPTY database (first boot) or to self-heal missing rows; it is
        insert-only, so it can never overwrite, relabel or delete a row that a
        live chain scan discovered.
        """
        return self.history.seed_verified_sales(rows)

    # ── C1: replay guard (durable, deploy-safe) ───────────────────────────────
    def claim_payment_tx(
        self,
        tx_hash: str,
        endpoint: str = "",
        payer: str = "",
        amount_usdc: float = 0.0,
        block_number: int = 0,
        block_hash: str = "",
    ) -> bool:
        """Claim a settlement tx hash for exactly one paid call.

        Thin wrapper (14.09) — see HistoryStore.claim_payment_tx. The lock now
        lives in the durable store and is FAIL-CLOSED: if the lock cannot be
        reached, this returns False and the payment is REFUSED rather than served
        on an unverifiable replay proof.

        `block_number`/`block_hash` (21.09) are the finality anchor: the
        confirming block, remembered so a later re-read can prove it was not
        reorganised away. Optional — an older caller simply stores no anchor.
        """
        return self.history.claim_payment_tx(
            tx_hash, endpoint=endpoint, payer=payer, amount_usdc=amount_usdc,
            block_number=block_number, block_hash=block_hash,
        )

    def payment_guard_row(self, tx_hash: str) -> Optional[dict]:
        """Claim row incl. delivery state — see HistoryStore.payment_guard_row."""
        return self.history.payment_guard_row(tx_hash)

    def mark_payment_delivered(self, tx_hash: str) -> bool:
        """Delivery stamp — see HistoryStore.mark_payment_delivered."""
        return self.history.mark_payment_delivered(tx_hash)

    def claim_payment_retry_slot(self, tx_hash: str, token: str) -> bool:
        """Single-flight recovery slot — see HistoryStore.claim_payment_retry_slot."""
        return self.history.claim_payment_retry_slot(tx_hash, token)

    # ── Sentinel PR watcher baseline (27.09) ─────────────────────────────────
    def get_pr_watch_state(self, pr_key: str) -> Optional[dict]:
        """Durable PR-watch baseline — see HistoryStore.get_pr_watch_state."""
        return self.history.get_pr_watch_state(pr_key)

    def set_pr_watch_state(self, pr_key: str, status: str,
                           mergeable_state: str = "") -> None:
        """Record the observed PR state — see HistoryStore.set_pr_watch_state."""
        self.history.set_pr_watch_state(pr_key, status, mergeable_state)

    def release_payment_retry_slot(self, tx_hash: str, token: str) -> bool:
        """Free the slot on a non-delivery — see HistoryStore."""
        return self.history.release_payment_retry_slot(tx_hash, token)

    def guard_claims_with_blocks(self, limit: int = 25) -> List[dict]:
        """Claims carrying a finality anchor — see HistoryStore."""
        return self.history.guard_claims_with_blocks(limit)

    def payment_guard_stats(self) -> Dict[str, Any]:
        """Guard telemetry — see HistoryStore.payment_guard_stats."""
        return self.history.payment_guard_stats()

    # ── guard events: durable record of what the guards BLOCKED ───────────────
    def record_guard_event(self, kind: str, endpoint: str = "",
                           tx_hash: str = "", detail: str = "") -> None:
        """Persist a guard rejection — see HistoryStore.record_guard_event.

        Telemetry only: it never raises and never changes a payment decision.
        """
        return self.history.record_guard_event(kind, endpoint=endpoint,
                                               tx_hash=tx_hash, detail=detail)

    def record_payment_attempt(self, path: str, outcome: str, payer: str = "",
                               amount_usdc: float = 0.0, detail: str = "",
                               tx_hash: str = "") -> None:
        """Record a presented payment payload — see HistoryStore.

        Telemetry only: it never raises and never changes a payment decision.
        Called from the rail at the moment the signature is seen, so the funnel
        can tell "came with a signature and it failed" apart from "never came
        with a signature" — both of which render as a 402 in `request_log`.
        """
        return self.history.record_payment_attempt(
            path, outcome, payer=payer, amount_usdc=amount_usdc,
            detail=detail, tx_hash=tx_hash)

    def payment_attempt_rows(self, since: str = "",
                             until: str = "") -> List[dict]:
        """Per-path attempt counts — see HistoryStore.payment_attempt_rows."""
        return self.history.payment_attempt_rows(since, until)

    def payment_attempts_readable(self) -> bool:
        """Whether the attempt table can be read — see HistoryStore."""
        return self.history.payment_attempts_readable()

    def payment_attempts_since(self) -> Optional[str]:
        """When attempt recording began — see HistoryStore."""
        return self.history.payment_attempts_since()

    def probe_replay_lock(self, force: bool = False,
                          probe_ttl_seconds: float = 600.0) -> bool:
        """Prove the replay lock can still write — see HistoryStore.

        TTL-gated on purpose (F-04): the read path must not be able to turn
        polling into writes on the table it shares with `claim_payment_tx`.
        """
        return self.history.probe_replay_lock(force, probe_ttl_seconds)

    def guard_stats(self, recent_limit: int = 5) -> Dict[str, Any]:
        """Lock health + blocked attempts — see HistoryStore.guard_stats.

        Includes `lock_backend` / `lock_durable` so the on-screen СТАЖИ section
        states WHERE the replay lock lives instead of implying durability.
        """
        return self.history.guard_stats(recent_limit)

    def guard_endpoint_map(self) -> Dict[str, str]:
        """{tx_hash → endpoint} — see HistoryStore.guard_endpoint_map.

        Route evidence for the ON-CHAIN SALES table (14.10): the granted claim
        is the only honest answer to "which route did this TX pay for" — the
        same join the CLIENTS section already relies on.
        """
        return self.history.guard_endpoint_map()

    def sale_by_tx(self, tx_hash: str) -> Optional[dict]:
        """Sale lookup — see HistoryStore.sale_by_tx (Telegram VIP claim path)."""
        return self.history.sale_by_tx(tx_hash)

    def track_record(self, now: Optional[datetime] = None) -> Dict[str, Any]:
        """Business clock + three numbers — see HistoryStore.track_record."""
        return self.history.track_record(now)

    def record_vip_invite(self, code: str, wallet: str, tx_hash: str = "",
                          chat_id: str = "", source: str = "onchain") -> bool:
        """VIP invite persistence — see HistoryStore.record_vip_invite."""
        return self.history.record_vip_invite(code, wallet, tx_hash, chat_id, source)

    def vip_invite_by_code(self, code: str) -> Optional[dict]:
        """VIP invite lookup — see HistoryStore.vip_invite_by_code."""
        return self.history.vip_invite_by_code(code)

    def vip_invite_for_wallet(self, wallet: str) -> Optional[dict]:
        """'Already VIP?' check — see HistoryStore.vip_invite_for_wallet."""
        return self.history.vip_invite_for_wallet(wallet)

    def mark_vip_invite_used(self, code: str) -> bool:
        """Mark a code consumed — see HistoryStore.mark_vip_invite_used."""
        return self.history.mark_vip_invite_used(code)

    def vip_invites_summary(self) -> Dict[str, Any]:
        """Invite counts — see HistoryStore.vip_invites_summary."""
        return self.history.vip_invites_summary()

    # ── public track record (frozen rules, 18.09) ─────────────────────────────
    def record_signal_issue(self, record_id: str, asset: str, action: str,
                            confidence: Any, issued_at: str,
                            price_at_issue: Optional[float],
                            vol_threshold: Optional[float],
                            outcome: str = "pending",
                            frozen_on: str = "") -> bool:
        """See HistoryStore.record_signal_issue (immutable at issue)."""
        return self.history.record_signal_issue(
            record_id, asset, action, confidence, issued_at, price_at_issue,
            vol_threshold, outcome, frozen_on)

    def signal_history_total(self) -> int:
        """See HistoryStore.signal_history_total (every row, any age/outcome)."""
        return self.history.signal_history_total()

    def signal_history_exists(self, record_id: str) -> bool:
        """See HistoryStore.signal_history_exists (skips the volatility fetch)."""
        return self.history.signal_history_exists(record_id)

    def signal_history_due(self, older_than_iso: str, limit: int = 50) -> List[dict]:
        """See HistoryStore.signal_history_due."""
        return self.history.signal_history_due(older_than_iso, limit)

    def resolve_signal(self, record_id: str, outcome: str,
                       price_at_24h: Optional[float], move_pct: Optional[float],
                       resolution_source: str, resolved_at: str) -> bool:
        """See HistoryStore.resolve_signal (write-once)."""
        return self.history.resolve_signal(record_id, outcome, price_at_24h,
                                           move_pct, resolution_source,
                                           resolved_at)

    def signal_history_rows(self, older_than_iso: str,
                            limit: int = 500) -> List[dict]:
        """See HistoryStore.signal_history_rows (≥24h old only)."""
        return self.history.signal_history_rows(older_than_iso, limit)

    def signal_history_not_scored(self) -> int:
        """See HistoryStore.signal_history_not_scored."""
        return self.history.signal_history_not_scored()

    def sales_summary(self, history_limit: int = 100) -> Dict[str, Any]:
        """Aggregate on-chain sales — see HistoryStore.sales_summary.

        Thin wrapper (14.09): the aggregation runs against the durable table, so
        /api/dashboard/data, /api/dashboard-stats and /api/sales cannot disagree
        with each other (they all call this) and cannot lose rows on a deploy.
        """
        return self.history.sales_summary(history_limit)

    # ── clients: the real external payers (basis for operator deals) ──────────
    def clients_summary(self,
                        price_map: Optional[Dict[str, float]] = None
                        ) -> Dict[str, Any]:
        """One row per EXTERNAL payer: wallet, payments, total, last buy, route.

        ROUTE HONESTY: a route is only claimed as FACT when a `payment_guards`
        row exists for that tx (the guard stores the endpoint the proof was
        bound to / consumed on). Otherwise the amount is matched against the
        published price list and the row reports the CANDIDATES plus an
        explicit `route_evidence: "price_ambiguous"` — because today $0.003
        is BOTH /api/v1/signal and /api/v1/whaleflow, and $0.005 covers four
        routes. Guessing one of them would be a phantom number on screen.
        """
        price_map = {k: round(float(v), 6) for k, v in (price_map or {}).items()}
        # Both halves now come from the durable store, but from TWO TABLES on
        # purpose: the sales rows and the granted claims. The claim is the only
        # honest evidence of WHICH route a payment was consumed on, so this joins
        # them instead of guessing a route from the amount (14.09: the lock moved
        # to PostgreSQL too — reading it from the local file would have silently
        # emptied this evidence in production).
        rows, detail = self.history.client_sales_rows()
        guards = self.history.guard_endpoint_map()
        by_sender: Dict[str, List[dict]] = {}
        for d in detail:
            by_sender.setdefault((d["sender"] or "").lower(), []).append(dict(d))

        clients = []
        for r in rows:
            sender = (r["sender"] or "").lower()
            payments = by_sender.get(sender, [])
            routes: Dict[str, Any] = {}
            for p in payments:
                amount = round(float(p["amount_usdc"] or 0), 6)
                bound = guards.get((p["tx_hash"] or "").lower())
                if bound:
                    routes.setdefault(bound, {"route": bound, "evidence":
                                              "payment_guard", "payments": 0})
                    routes[bound]["payments"] += 1
                    continue
                candidates = sorted(
                    k for k, v in price_map.items() if abs(v - amount) < 1e-9
                )
                key = "|".join(candidates) if candidates else f"${amount}"
                entry = routes.setdefault(key, {
                    "route": candidates[0] if len(candidates) == 1 else None,
                    "candidates": candidates,
                    "evidence": ("price_unique" if len(candidates) == 1
                                 else "price_ambiguous" if candidates
                                 else "unknown"),
                    "amount_usdc": amount,
                    "payments": 0,
                })
                entry["payments"] += 1
            clients.append({
                "wallet": sender,
                "payments": r["n"],
                "total_usdc": round(r["total"], 6),
                "first_ts": r["first_ts"],
                "last_ts": r["last_ts"],
                "routes": list(routes.values()),
                "tx_hashes": [p["tx_hash"] for p in payments],
            })
        return {
            "clients": clients,
            "count": len(clients),
            "potentially_new": [c["wallet"] for c in clients
                                if (c["payments"] == 1
                                    and c["total_usdc"] <= 0.005)],
            "route_price_map": price_map,
        }

    # ── request log ───────────────────────────────────────────────────────────
    def record_request(
        self,
        method: str,
        path: str,
        source: str,
        status_code: int,
        user_agent: str = "",
        referer: str = "",
        funnel: Optional[str] = None,
    ) -> None:
        """Persist one request — history lives in HistoryStore now."""
        self.history.record_request(method, path, source, status_code,
                                    user_agent, referer, funnel)

    def requests_summary(self, recent_limit: int = 25) -> Dict[str, Any]:
        # Persisted request analytics. History lives in HistoryStore now, so
        # the numbers survive a deploy (DATABASE_URL -> PostgreSQL) instead of
        # resetting to zero on every restart.
        return self.history.requests_summary(recent_limit)
    # ── PayAPI listing state ──────────────────────────────────────────────────
    def save_payapi_state(self, state: Dict[str, Any]) -> None:
        with self._write_lock, self._connect() as conn:
            conn.execute(
                """INSERT INTO payapi_state (key, value, updated_at)
                   VALUES ('listing', ?, ?)
                   ON CONFLICT(key) DO UPDATE SET
                       value = excluded.value,
                       updated_at = excluded.updated_at""",
                (
                    json.dumps(state, ensure_ascii=False),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()

    def get_payapi_state(self) -> Dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value, updated_at FROM payapi_state WHERE key = 'listing'"
            ).fetchone()
        if not row:
            return {
                "available": False,
                "reason": "no scan yet (baseline)",
                "updated_at": None,
            }
        try:
            state = json.loads(row["value"])
        except (TypeError, ValueError):
            return {"available": False, "reason": "corrupt state", "updated_at": None}
        return {
            "available": True,
            "reliability": state.get("reliability"),
            "ranks": state.get("ranks") or {},
            "updated_at": row["updated_at"],
        }

    # ── chain scanning (read-only, same logic as competitor_recon) ───────────
    def _block_timestamps(self, w3, blocks: List[int]) -> Dict[int, datetime]:
        """Block timestamps via the DEFAULT public RPC (mainnet.base.org) —
        get_block works fine there even when the scan RPC (e.g. pokt) is
        rate-limited. A missing timestamp must NOT silently become now().

        PRIORITY-0 FIX (13.09): `Web3` was used here without being imported in
        this scope (`scan_window` imports it for ITS OWN frame only), so the
        very FIRST sale ever found raised NameError, which propagated out of
        `scan_window` before the watermark was written. Net effect: the RPC
        could return the transfer, and the dashboard still recorded nothing
        and never advanced — the second half of the "0 sales" bug.
        """
        from web3 import Web3

        out: Dict[int, datetime] = {}
        tw3 = Web3(Web3.HTTPProvider(
            "https://mainnet.base.org", request_kwargs={"timeout": 30}))
        for b in dict.fromkeys(blocks):
            for attempt in range(3):
                try:
                    block = tw3.eth.get_block(b)
                    out[b] = datetime.fromtimestamp(
                        block["timestamp"], tz=timezone.utc)
                    break
                except Exception:
                    if attempt < 2:
                        import time as _time
                        _time.sleep(1)
        return out

    def scan_window(
        self,
        from_block: int,
        to_block: int,
        rpc_url: str = "",
        chunk_size: int = 0,
        pause_seconds: float = 0.15,
    ) -> int:
        """Scan a block range for incoming USDC transfers and persist them.

        Read-only RPC scan (eth_getLogs), chunked and paced.
        chunk_size: 0 = env SALES_CHUNK_BLOCKS (default 5000 — BUT drpc/pokt
        free tiers silently return EMPTY (or 400) for large recipient-filtered
        ranges; 10 is the verified-safe width on both).

        PRIORITY-0 FIX (13.09): the old `max(50, ...)` floor silently CLAMPED
        SALES_CHUNK_BLOCKS=10 up to 50 — the one width that is known to fail
        on the free tiers. The floor is now 1 and the scan is ADAPTIVE: a
        failed chunk halves its own span (50→25→12→6→3→1) and retries the
        SAME start block instead of giving up, so the watermark can no longer
        stall behind a chunk size the RPC refuses. Returns the number of NEW
        sales recorded. Watermark is NOT updated here — the caller owns it.
        """
        try:
            chunk_size = max(1, int(os.getenv("SALES_CHUNK_BLOCKS",
                                              str(chunk_size or 5000))))
        except ValueError:
            chunk_size = 5000
        if to_block < from_block:
            return 0
        from web3 import Web3

        rpc_url = rpc_url or os.getenv("BASE_RPC_URL", "https://mainnet.base.org")
        receiver = os.getenv("BASE_FEE_RECEIVER", "")
        if not receiver:
            try:
                from config import get_base_fee_receiver
                receiver = get_base_fee_receiver()
            except Exception:
                receiver = ""
        if not receiver:
            return 0

        w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
        if not w3.is_connected():
            # AUDIT (13.09): `is_connected()` is a web3_clientVersion probe, and
            # a rate-limited provider (Alchemy answers 429 under load) makes it
            # return False even though get_logs still works. Raising here threw
            # away the WHOLE scan cycle instead of letting the per-chunk halving
            # cope — live logs showed repeated "RPC not reachable" while the
            # scans were otherwise healthy. Proceed: a genuinely dead RPC fails
            # the first chunk and the halving loop stops at span 1 by itself.
            log.debug("is_connected() false for %s — proceeding anyway",
                      redact_rpc(rpc_url))

        padded = "0x" + "0" * 24 + receiver.lower().replace("0x", "")
        transfers: List[dict] = []

        def _collect(logs):
            for lg in logs:
                try:
                    sender = "0x" + bytes(lg["topics"][1]).hex()[-40:]
                    raw = lg["data"]
                    if hasattr(raw, "hex"):
                        raw = raw.hex()
                    amount = int(raw or "0", 16) / 1e6
                    transfers.append({
                        "tx_hash": Web3.to_hex(lg["transactionHash"]),
                        "payer": sender,
                        "amount_usdc": amount,
                        "block_number": lg["blockNumber"],
                    })
                except Exception:
                    continue

        # Chunking / pacing / halving live in ONE shared helper — the same
        # machine the whale scan uses (free-tier range caps + rate limits are
        # a solved problem; never solved twice).
        safe_end, effective_span = _adaptive_get_logs(
            w3, from_block, to_block, [TRANSFER_TOPIC, None, padded],
            chunk_size, pause_seconds, _collect,
        )

        # Ops telemetry: the effective width actually accepted by the RPC.
        self.set_meta("sales_effective_chunk", str(effective_span))
        if not transfers:
            # Even with zero transfers the range WAS scanned up to safe_end —
            # record it so the watermark advances honestly (no fake gaps).
            self.set_meta("sales_safe_scanned_block", str(max(0, safe_end)))
            return 0
        stamps = self._block_timestamps(
            w3, [t["block_number"] for t in transfers]
        )
        added = 0
        for t in transfers:
            if self.record_sale(
                tx_hash=t["tx_hash"],
                amount_usdc=t["amount_usdc"],
                sender=t["payer"],
                block_number=t["block_number"],
                ts=stamps.get(t["block_number"]),
                source="scan",
            ):
                added += 1
        # Record the last CONTIGUOUS scanned block — failed chunks are retried
        # next cycle instead of skipped (honesty rule).
        self.set_meta("sales_safe_scanned_block", str(max(0, safe_end)))
        return added

    def retro_scan(self, days: int = 30, rpc_url: str = "") -> int:
        """First-run backfill: scan the last `days` days of incoming transfers.

        This is what makes the very first external payment (day zero) visible
        in the dashboard history immediately after deploy.
        """
        self.reclassify_known_payers()
        from web3 import Web3

        rpc_url = rpc_url or os.getenv("BASE_RPC_URL", "https://mainnet.base.org")
        w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
        latest = w3.eth.block_number
        from_block = max(1, latest - int(days * 86400 / BLOCK_TIME_SECONDS))
        added = self.scan_window(from_block, latest, rpc_url=rpc_url)
        # Watermark = last CONTIGUOUS safe block — a broken chunk is retried
        # next cycle, never silently skipped (honesty rule). If the scan
        # failed entirely (safe = 0/None), the watermark stays BELOW the
        # start so the whole range is retried on the next cycle.
        safe = int(self.get_meta("sales_safe_scanned_block", "0") or 0)
        self.set_meta("last_scanned_block",
                      str(min(safe, latest) if safe else from_block - 1))
        return added

    def scan_increment(self, rpc_url: str = "", max_blocks: int = 20000) -> int:
        """Scan new blocks since the persisted watermark (deploy-safe)."""
        # Taxonomy may have evolved since the last cycle — re-apply first so
        # the dashboard classes stay honest even when the RPC is flaky.
        self.reclassify_known_payers()
        from web3 import Web3

        rpc_url = rpc_url or os.getenv("BASE_RPC_URL", "https://mainnet.base.org")
        w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
        latest = w3.eth.block_number
        last = int(self.get_meta("last_scanned_block", "0") or 0)
        if last <= 0:
            # No watermark: retro_scan owns the backfill — do NOT mark latest
            # as scanned (that would skip the 30d history permanently).
            return 0
        from_block = last + 1
        to_block = min(latest, from_block + max_blocks)
        if to_block < from_block:
            return 0
        added = self.scan_window(from_block, to_block, rpc_url=rpc_url)
        safe = int(self.get_meta("sales_safe_scanned_block", "0") or 0)
        self.set_meta("last_scanned_block",
                      str(min(safe, to_block) if safe else from_block - 1))
        return added

    # ── whale flow (network-wide big USDC transfers on Base) ─────────────────
    def scan_whale_window(self, from_block: int, to_block: int,
                          rpc_url: str = "", chunk_blocks: int = 0,
                          pause_seconds: float = 0.2) -> int:
        """Network-wide scan: ALL USDC Transfer logs on Base, keep only
        transfers >= the current WHALE_THRESHOLD. Read-only RPC,
        chunked/paced. Watermark is the caller's job.
        Returns the number of NEW whale events recorded.

        AUDIT FIX (Табло 2.0): this function carried the SAME `max(50, …)`
        floor that broke the sales scan, with a 250-block default. Measured
        against the public Base RPC: a network-wide (unfiltered) getLogs
        window of 250 blocks answers **HTTP 500**, while <=100 blocks answers
        fine and contains real data (100 blocks -> 5,072 transfers, 701 of
        them >= $50k). So every whale chunk failed on the first call and the
        promoted, PAID /api/v1/whaleflow route could never serve a single row.
        The floor is gone and a refused window is now retried with HALF the
        span (same start block, never skipped), exactly like the sales scan.

        chunk_blocks: 0 = env WHALEFLOW_CHUNK_BLOCKS (default 100 — the widest
        window measured to work network-wide).
        """
        if to_block < from_block:
            return 0
        threshold = whale_threshold()
        try:
            chunk_blocks = max(1, int(os.getenv("WHALEFLOW_CHUNK_BLOCKS",
                                                str(chunk_blocks or 100))))
        except ValueError:
            chunk_blocks = 100
        from web3 import Web3

        rpc_url = rpc_url or os.getenv("BASE_RPC_URL", "https://mainnet.base.org")
        w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
        if not w3.is_connected():
            # Same reasoning as the sales scan: a 429 makes this probe lie, and
            # raising discarded the whole whale cycle.
            log.debug("is_connected() false for %s — proceeding anyway",
                      redact_rpc(rpc_url))
        added = 0
        # The attempt is recorded when it STARTS, not when it ends: the first
        # network-wide scan walks minutes, and the dashboard must say "scanning"
        # during it rather than "the scan has not started".
        self.set_meta("whaleflow_last_attempt",
                      datetime.now(timezone.utc).isoformat())

        def _collect(logs):
            """Whale filter + persistence for one accepted chunk."""
            nonlocal added
            stamps = {}
            for lg in logs:
                try:
                    raw = lg["data"]
                    if hasattr(raw, "hex"):
                        raw = raw.hex()
                    amount = int(raw or "0", 16) / 1e6
                    if amount < threshold:
                        continue
                    frm = "0x" + bytes(lg["topics"][1]).hex()[-40:]
                    to = "0x" + bytes(lg["topics"][2]).hex()[-40:]
                    tx = Web3.to_hex(lg["transactionHash"])
                    ln = int(lg["logIndex"])
                    block = lg["blockNumber"]
                    if block not in stamps:
                        try:
                            blk = w3.eth.get_block(block)
                            stamps[block] = datetime.fromtimestamp(
                                blk["timestamp"], tz=timezone.utc)
                        except Exception:
                            stamps[block] = datetime.now(timezone.utc)
                    added += self.history.record_whale_event(
                        tx, ln, stamps[block].isoformat(), "USDC", amount,
                        frm.lower(), to.lower(), block)
                except Exception:
                    continue

        # SAME chunk/pacing/halving machine as the sales scan — the network-wide
        # query is simply a wider topic filter, not a second implementation.
        def _progress(safe: int, span: int) -> None:
            # The watermark moves DURING the walk (18.09). A boot backfill walks
            # hours of chain, and the dashboard used to say "scanned until:
            # nothing" for that entire hour — a truthful-looking blank is still a
            # lie about the feed's freshness. It also means a crash resumes from
            # the last COMPLETED chunk instead of re-scanning the whole window.
            self.set_meta("whaleflow_safe_scanned_block", str(max(0, safe)))
            self.set_meta("whaleflow_last_block", str(max(0, safe)))
            self.set_meta("whaleflow_effective_chunk", str(span))

        safe_end, effective_span = _adaptive_get_logs(
            w3, from_block, to_block, [TRANSFER_TOPIC, None, None],  # all
            chunk_blocks, pause_seconds, _collect, on_progress=_progress,
        )

        # Record the last CONTIGUOUS scanned block — failed chunks are retried
        # next cycle instead of being skipped (honesty: we never serve a range
        # that was not actually scanned).
        covered_all = safe_end >= to_block
        self.set_meta("whaleflow_effective_chunk", str(effective_span))
        self.set_meta("whaleflow_safe_scanned_block", str(max(0, safe_end)))
        if covered_all:
            # A complete range clears any previous failure — the feed is
            # healthy again and the dashboard must stop saying otherwise.
            self.set_meta("whaleflow_last_error", "")
        else:
            # Honest progress (10.10): the old "scanned X-Y" printed the
            # FROZEN watermark as Y = from_block - 1 when nothing landed,
            # which reads as a reversed range ("52343009-52343008"). Report
            # the real covered block count instead.
            scanned_count = max(0, safe_end - from_block + 1)
            progress = (f"scanned {scanned_count} blocks ending at "
                        f"{max(0, safe_end)}" if scanned_count
                        else f"scanned 0 blocks (nothing completed "
                             f"from {from_block})")
            self.set_meta(
                "whaleflow_last_error",
                f"{progress} of {to_block} "
                f"(RPC refused a {effective_span}-block window; the next cycle "
                f"retries from the watermark)",
            )
        return added

    def whaleflow_backfill(self, hours: int = WHALE_BACKFILL_HOURS_DEFAULT,
                           rpc_url: str = "") -> int:
        """Initial backfill: last `hours` network-wide, keep whale-sized.
        Sets the whale watermark."""
        self.reclassify_known_payers()
        from web3 import Web3

        rpc_url = rpc_url or os.getenv("BASE_RPC_URL", "https://mainnet.base.org")
        w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
        latest = w3.eth.block_number
        # HOURS, honestly (18.09): this line used to read `hours * 86400 / …`, i.e.
        # it treated the parameter as DAYS while the name, the env var and the
        # docstring all said hours. Measured live: WHALEFLOW_BACKFILL_HOURS=1
        # scanned 39,051 blocks (~22 h) instead of 1,800, and the default (24)
        # would have walked ~24 DAYS of chain. Same behaviour as the day it was
        # found (the boot backfill is meant to fill the 24h window the paid route
        # serves), but now the knob does what it says.
        from_block = max(1, latest - int(hours * 3600 / BLOCK_TIME_SECONDS))
        # RESUME from the durable watermark (18.09). A COLD start (no watermark)
        # still fills the whole rolling window, but a restart after a deploy
        # continues where the scan stopped. Without this the durable watermark was
        # decorative: auto-deploy is ON, so every push re-walked a full day of
        # chain (~900 getLogs on the free RPC) and the PAID feed lagged reality by
        # ~35 minutes — six times on 18.09 alone.
        watermark = int(self.get_meta("whaleflow_last_block", "0") or 0)
        if watermark > from_block:
            from_block = min(watermark, latest)
        added = self.scan_whale_window(from_block, latest, rpc_url=rpc_url)
        # Watermark = last CONTIGUOUS safe block (failed chunks retry next cycle)
        safe = int(self.get_meta("whaleflow_safe_scanned_block", "0") or 0)
        self.set_meta("whaleflow_last_block", str(min(safe, latest) if safe else latest))
        return added

    def whaleflow_increment(self, rpc_url: str = "",
                            max_blocks: int = 10000) -> int:
        """Network-wide whale scan since the persisted whale watermark."""
        self.reclassify_known_payers()
        from web3 import Web3

        rpc_url = rpc_url or os.getenv("BASE_RPC_URL", "https://mainnet.base.org")
        w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
        latest = w3.eth.block_number
        last = int(self.get_meta("whaleflow_last_block", "0") or 0)
        if last <= 0:
            self.set_meta("whaleflow_last_block", str(latest))
            return 0
        from_block = last + 1
        to_block = min(latest, from_block + max_blocks)
        if to_block < from_block:
            return 0
        added = self.scan_whale_window(from_block, to_block, rpc_url=rpc_url)
        safe = int(self.get_meta("whaleflow_safe_scanned_block", "0") or 0)
        self.set_meta("whaleflow_last_block",
                      str(min(safe, to_block) if safe else to_block))
        return added

    def whaleflow_summary(self, window_hours: int = WHALE_WINDOW_HOURS_DEFAULT,
                          limit: int = 50,
                          threshold: float | None = None) -> Dict[str, Any]:
        """Fresh whale events in the rolling window, newest first, filtered
        by the CURRENT threshold (env-regulatable at read time). Honest
        labels: known/watchlisted names or literally 'unknown'."""
        threshold = whale_threshold() if threshold is None else threshold
        scanned_until = self.get_meta("whaleflow_safe_scanned_block") or self.get_meta("whaleflow_last_block")
        # Honesty: a BROKEN scan must never look like a healthy empty feed.
        last_attempt = self.get_meta("whaleflow_last_attempt")
        last_error = self.get_meta("whaleflow_last_error")
        effective_chunk = self.get_meta("whaleflow_effective_chunk")
        # Rows and the all-time context come from the history backend, so the
        # PAID feed's history survives a deploy instead of resetting to zero.
        h = self.history.whale_rows(window_hours, limit, threshold)
        whales = h["whales"]
        return {
            "whales": whales,
            "count": len(whales),
            "window_hours": window_hours,
            "threshold_usdc": threshold,
            "scanned_until_block": int(scanned_until or 0) or None,
            "all_time_count": h["all_time_count"],
            "last_event_at": h["last_event_at"],
            "last_event_block": h["last_event_block"],
            # "awaiting_whale" is a TRUTHFUL empty: the scan is running
            # (watermark advancing) and simply found nothing >= threshold.
            # "scan_failed" is the opposite: the scanner itself is broken, and
            # showing "чакаме кит" for it would hide a dead paid feed.
            # "scanning" covers the first (minutes-long) network-wide walk.
            # "scan_paused_by_owner" is a DELIBERATE stop (17.09: the scan was
            # burning a paid RPC) — first in precedence, because it is the only
            # state where the reason for an empty feed is a human decision,
            # not a fault.
            # A stale error must not keep the panel red forever (10.10):
            # "scan_failed" means the scanner is ACTIVELY failing — its last
            # attempt is recent. An old error string with no fresh attempt
            # means the scan is not running at all; the ladder below reports
            # that honestly instead of a permanent alarm.
            "state": ("scan_paused_by_owner"
                      if (self.get_meta("whaleflow_state")
                          == "scan_paused_by_owner")
                      else "live_data" if whales
                      else "scan_failed" if (last_error
                                             and _is_fresh(last_attempt))
                      else "awaiting_whale" if scanned_until
                      else "scanning" if last_attempt
                      else "scan_not_started"),
            "paused_at": (self.get_meta("whaleflow_state_at") or None)
            if self.get_meta("whaleflow_state") == "scan_paused_by_owner"
            else None,
            "last_attempt_at": last_attempt or None,
            "last_error": last_error or None,
            "effective_chunk_blocks": (int(effective_chunk)
                                       if effective_chunk else None),
        }