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

import json
import logging
import os
import re
import sqlite3
import threading
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
]

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
        except Exception:
            if span > 1:
                # Adaptive back-off: halve and retry the SAME start block.
                span = max(1, span // 2)
                effective_span = min(effective_span, span)
                log.debug("getLogs %s.. refused — retry with span=%d",
                          start, span)
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
        import psycopg
        from psycopg.rows import dict_row
        if self._pg_conn is None or self._pg_conn.closed:
            self._pg_conn = psycopg.connect(self.database_url,
                                            row_factory=dict_row)
        return self._pg_conn

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
        with self._pg_lock:                  # one shared, serialised link
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
                    tx_hash     TEXT PRIMARY KEY,
                    endpoint    TEXT,
                    payer       TEXT,
                    amount_usdc {real},
                    consumed_at TEXT
                )"""
        )
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
        log.info("Durable store ready (%s): request_log + whaleflow_events + "
                 "onchain_sales + payment_guards + guard_events.",
                 self.backend)

    # ── request log ─────────────────────────────────────────────────────────
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

    def requests_summary(self, recent_limit: int = 25) -> Dict[str, Any]:
        """today/total + channel (/f/<name>) + source breakdown.

        The internal keep-alive traffic (UA 'Render/1.0' — our own /health pings
        plus Render health checks) is counted SEPARATELY so the clean
        customer/agent-facing numbers light up on their own. Also aggregates the
        payment FUNNEL per paid route (402 challenges -> paid follow-ups,
        today + total) — the "caught by the hand" metric.
        """
        one = "one"
        all_ = "all"
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        internal_sql = "user_agent LIKE 'Render/%'"

        total = self._run(
            "SELECT COUNT(*) AS n FROM request_log", (), one)[0]["n"]
        today_row = self._run(
            "SELECT COUNT(*) AS n FROM request_log WHERE substr(ts, 1, 10) = ?",
            (today,), one)[0]["n"]
        noise_total = self._run(
            f"SELECT COUNT(*) AS n FROM request_log WHERE {internal_sql}",
            (), one)[0]["n"]
        noise_today = self._run(
            f"SELECT COUNT(*) AS n FROM request_log "
            f"WHERE substr(ts, 1, 10) = ? AND {internal_sql}",
            (today,), one)[0]["n"]
        by_source = self._run(
            """SELECT source, COUNT(*) AS n FROM request_log
               GROUP BY source ORDER BY n DESC""", (), all_)[0]
        by_source_clean = self._run(
            f"""SELECT source, COUNT(*) AS n FROM request_log
                WHERE NOT ({internal_sql})
                GROUP BY source ORDER BY n DESC""", (), all_)[0]
        by_channel = self._run(
            """SELECT funnel AS channel, COUNT(*) AS n FROM request_log
               WHERE funnel IS NOT NULL AND funnel <> ''
               GROUP BY funnel ORDER BY n DESC""", (), all_)[0]
        by_path = self._run(
            """SELECT path, COUNT(*) AS n FROM request_log
               GROUP BY path ORDER BY n DESC LIMIT 10""", (), all_)[0]
        top_user_agents = self._run(
            f"""SELECT user_agent, COUNT(*) AS n FROM request_log
                WHERE user_agent <> '' AND NOT ({internal_sql})
                GROUP BY user_agent ORDER BY n DESC LIMIT 10""", (), all_)[0]
        hourly = self._run(
            """SELECT substr(ts, 12, 2) AS hour, COUNT(*) AS n,
                      SUM(CASE WHEN user_agent LIKE 'Render/%' THEN 1 ELSE 0 END)
                          AS noise
               FROM request_log
               WHERE substr(ts, 1, 10) = ?
               GROUP BY substr(ts, 12, 2) ORDER BY hour""",
            (today,), all_)[0]

        # ── payment funnel per paid route: 402 challenges vs paid retries ──
        funnel = {}
        for path in FUNNEL_ROUTES:
            cur = self._run(
                """SELECT
                     SUM(CASE WHEN status_code = 402 THEN 1 ELSE 0 END)
                         AS challenges,
                     SUM(CASE WHEN status_code = 200 THEN 1 ELSE 0 END) AS paid
                   FROM request_log WHERE path = ?""", (path,), one)[0]
            cur_today = self._run(
                """SELECT
                     SUM(CASE WHEN status_code = 402 THEN 1 ELSE 0 END)
                         AS challenges,
                     SUM(CASE WHEN status_code = 200 THEN 1 ELSE 0 END) AS paid
                   FROM request_log
                   WHERE path = ? AND substr(ts, 1, 10) = ?""",
                (path, today), one)[0]
            # BUGFIX (13.09): "today" used to be filled from the TOTAL query
            # (`cur`), so the dashboard's "Днес: 402 → платени" column silently
            # repeated the all-time numbers (cur_today was thrown away).
            funnel[path] = {
                "challenges_total": cur["challenges"] or 0,
                "paid_total": cur["paid"] or 0,
                "challenges_today": cur_today["challenges"] or 0,
                "paid_today": cur_today["paid"] or 0,
            }
        recent = self._run(
            """SELECT ts, method, path, source, status_code, user_agent, funnel
               FROM request_log ORDER BY id DESC LIMIT ?""",
            (recent_limit,), all_)[0]
        return {
            "today_date": today,
            "today": today_row,
            "total": total,
            "today_clean": max(0, today_row - noise_today),
            "total_clean": max(0, total - noise_total),
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

    def claim_payment_tx(self, tx_hash: str, endpoint: str = "",
                         payer: str = "", amount_usdc: float = 0.0) -> bool:
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
        )
        try:
            _, rowcount = self._run(
                """INSERT INTO payment_guards
                       (tx_hash, endpoint, payer, amount_usdc, consumed_at)
                   VALUES (?, ?, ?, ?, ?)
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

    def guard_stats(self, recent_limit: int = 5) -> Dict[str, Any]:
        """Live health of the C1 replay lock + the blocked attempts it made.

        `lock_alive` is a REAL probe: it writes, reads and removes a sentinel row
        in `payment_guards`, so a broken/locked/read-only lock reports red instead
        of silently letting every replay through. Since the lock lives in the
        durable store, a probe failure here is also exactly the condition under
        which `claim_payment_tx` starts refusing payments (fail-closed) — the
        dashboard shows that state instead of hiding it.
        """
        alive = False
        probe_error = ""
        sentinel = "__lock_probe__"
        try:
            self._run("DELETE FROM payment_guards WHERE tx_hash = ?",
                      (sentinel,))
            self._run(
                """INSERT INTO payment_guards
                       (tx_hash, endpoint, payer, amount_usdc, consumed_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (sentinel, "", "", 0.0, datetime.now(timezone.utc).isoformat()),
            )
            row = self._run(
                "SELECT COUNT(*) AS n FROM payment_guards WHERE tx_hash = ?",
                (sentinel,), "one")[0]
            alive = bool(row and row["n"] == 1)
            self._run("DELETE FROM payment_guards WHERE tx_hash = ?",
                      (sentinel,))
        except Exception as exc:
            probe_error = str(exc)[:200]

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            by_kind = self._run(
                """SELECT kind, COUNT(*) AS n FROM guard_events
                   GROUP BY kind ORDER BY n DESC""", (), "all")[0]
            total_blocked = self._run(
                "SELECT COUNT(*) AS n FROM guard_events", (), "one")[0]
            blocked_today = self._run(
                """SELECT COUNT(*) AS n FROM guard_events
                   WHERE substr(ts, 1, 10) = ?""", (today,), "one")[0]
            recent = self._run(
                """SELECT ts, kind, endpoint, tx_hash, detail FROM guard_events
                   ORDER BY id DESC LIMIT ?""", (recent_limit,), "all")[0]
        except Exception as exc:  # pragma: no cover - display only
            log.debug("guard event stats unavailable: %s", exc)
            by_kind, total_blocked, blocked_today, recent = [], None, None, []
        return {
            "lock_alive": alive,
            "lock_probe_error": probe_error or None,
            "lock_backend": self.backend,
            "lock_durable": self.backend == "postgresql",
            "blocked_total": total_blocked["n"] if total_blocked else 0,
            "blocked_today": blocked_today["n"] if blocked_today else 0,
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

    def get_meta(self, key: str, default: Optional[str] = None) -> Optional[str]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM meta WHERE key = ?", (key,)
            ).fetchone()
        return row["value"] if row else default

    def set_meta(self, key: str, value: str) -> None:
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
    ) -> bool:
        """Claim a settlement tx hash for exactly one paid call.

        Thin wrapper (14.09) — see HistoryStore.claim_payment_tx. The lock now
        lives in the durable store and is FAIL-CLOSED: if the lock cannot be
        reached, this returns False and the payment is REFUSED rather than served
        on an unverifiable replay proof.
        """
        return self.history.claim_payment_tx(
            tx_hash, endpoint=endpoint, payer=payer, amount_usdc=amount_usdc,
        )

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

    def guard_stats(self, recent_limit: int = 5) -> Dict[str, Any]:
        """Lock health + blocked attempts — see HistoryStore.guard_stats.

        Includes `lock_backend` / `lock_durable` so the on-screen СТАЖИ section
        states WHERE the replay lock lives instead of implying durability.
        """
        return self.history.guard_stats(recent_limit)

    def sale_by_tx(self, tx_hash: str) -> Optional[dict]:
        """Sale lookup — see HistoryStore.sale_by_tx (Telegram VIP claim path)."""
        return self.history.sale_by_tx(tx_hash)

    def track_record(self, now: Optional[datetime] = None) -> Dict[str, Any]:
        """Business clock + three numbers — see HistoryStore.track_record."""
        return self.history.track_record(now)

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
            self.set_meta(
                "whaleflow_last_error",
                f"scanned {from_block}-{max(0, safe_end)} of {to_block} "
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
            "state": ("scan_paused_by_owner"
                      if (self.get_meta("whaleflow_state")
                          == "scan_paused_by_owner")
                      else "live_data" if whales
                      else "scan_failed" if last_error
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