"""Persistent dashboard store — single source of truth for the canonical
operations dashboard.

Everything the dashboard shows lives in SQLite (data/dashboard_state.db), NOT
in RAM, so deploys/restarts never reset the numbers (priority-0 invariant:
"deploy must not zero the counters").

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
WHALE_THRESHOLD_DEFAULT = 50_000.0   # USDC
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
                       handle_logs, address: str = USDC_BASE):
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
        start = end + 1
        if start <= to_block:
            _time.sleep(pause_seconds)
    return safe_end, effective_span


class DashboardStore:
    """SQLite-backed persistent store (one connection per call, like CRMStore)."""

    def __init__(self, file_path: str | Path | None = None):
        self.file_path = Path(
            file_path or os.getenv("KRISTO_DASHBOARD_DB") or default_db_path()
        )
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.Lock()
        self._ensure_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.file_path), timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS onchain_sales (
                    tx_hash      TEXT PRIMARY KEY,
                    block_number INTEGER,
                    ts           TEXT,
                    sender       TEXT,
                    amount_usdc  REAL,
                    payer_class  TEXT,
                    payer_label  TEXT,
                    source       TEXT,
                    recorded_at  TEXT
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS request_log (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts         TEXT,
                    method     TEXT,
                    path       TEXT,
                    source     TEXT,
                    status_code INTEGER,
                    user_agent TEXT,
                    referer    TEXT,
                    funnel     TEXT
                )"""
            )
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
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_request_log_ts ON request_log (ts)"
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS whaleflow_events (
                    tx_hash      TEXT,
                    log_index    INTEGER,
                    ts           TEXT,
                    token        TEXT,
                    amount_usdc  REAL,
                    from_addr    TEXT,
                    to_addr      TEXT,
                    block_number INTEGER,
                    recorded_at  TEXT,
                    PRIMARY KEY (tx_hash, log_index)
                )"""
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_whaleflow_ts ON whaleflow_events (ts)"
            )
            # ── C1 replay guard: a tx hash may unlock EXACTLY ONE paid call,
            # and that fact must survive restarts/deploys (RAM sets do not).
            conn.execute(
                """CREATE TABLE IF NOT EXISTS payment_guards (
                    tx_hash    TEXT PRIMARY KEY,
                    endpoint   TEXT,
                    payer      TEXT,
                    amount_usdc REAL,
                    consumed_at TEXT
                )"""
            )
            # ── Guard rejections (C1 replay / C2 depth / H2 binding) — durable
            # so the dashboard "СТАЖИ" section can show the LAST blocked
            # attempt from a table instead of guessing it from log lines.
            conn.execute(
                """CREATE TABLE IF NOT EXISTS guard_events (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts         TEXT,
                    kind       TEXT,
                    endpoint   TEXT,
                    tx_hash    TEXT,
                    detail     TEXT
                )"""
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_guard_events_ts "
                "ON guard_events (ts)"
            )
            conn.commit()

    # ── meta (watermarks, flags) ──────────────────────────────────────────────
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
        with self._write_lock, self._connect() as conn:
            for sender, label in KNOWN_PAYERS.items():
                cur = conn.execute(
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
                updated += cur.rowcount
            conn.commit()
        return updated

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
        """Insert one confirmed on-chain sale. Returns True if it was new.

        Deduplicated by normalized tx hash — the settle path and the monitor
        can both see the same transfer; only the first insert counts.
        """
        tx = _norm_tx(tx_hash)
        if not tx:
            return False
        ts = ts or datetime.now(timezone.utc)
        payer_class, payer_label = classify_payer(sender)
        with self._write_lock, self._connect() as conn:
            cur = conn.execute(
                """INSERT OR IGNORE INTO onchain_sales
                       (tx_hash, block_number, ts, sender, amount_usdc,
                        payer_class, payer_label, source, recorded_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
            conn.commit()
            return cur.rowcount > 0

    def seed_verified_sales(self, rows: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Idempotently restore the chain-verified sales manifest.

        Priority-0 recovery: the canonical dashboard must show the REAL
        on-chain numbers after a deploy wipes the ephemeral filesystem.
        Every row in `integrations.verified_sales.VERIFIED_SALES` was pulled
        from the chain (full 66-char hashes) and cross-verified against an
        independent RPC receipt — see scripts/_verify_seed_chain.py.

        Insert-only (`INSERT OR IGNORE` via record_sale): a scan-discovered
        row wins over the seed, never the other way round. The sales
        watermark is deliberately NOT touched.

        Returns {"inserted": n, "present": n, "total_usdc": x}.
        """
        if rows is None:
            from integrations.verified_sales import VERIFIED_SALES as rows  # type: ignore
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
        summary = self.sales_summary()
        return {
            "inserted": inserted,
            "present": summary["total_count"],
            "total_usdc": summary["total_usdc"],
            "external_payers": summary["external_payers"],
        }

    # ── C1: replay guard (durable, deploy-safe) ───────────────────────────────
    def claim_payment_tx(
        self,
        tx_hash: str,
        endpoint: str = "",
        payer: str = "",
        amount_usdc: float = 0.0,
    ) -> bool:
        """Atomically CLAIM a settlement tx hash for exactly one paid call.

        Returns True only for the FIRST (tx_hash, endpoint) consumer. A
        replay — same hash again, or the same hash re-pointed at a different
        endpoint (H2 binding) — returns False. The claim lives in SQLite, so
        a restart/deploy can no longer resurrect a consumed proof (the
        in-RAM `_verified_payments` set used to be the only guard).

        The INSERT is the lock: the PRIMARY KEY makes the check-and-claim a
        single atomic statement across processes/threads.
        """
        tx = _norm_tx(tx_hash)
        if not tx:
            return False
        row = (
            tx,
            (endpoint or "").strip(),
            (payer or "").lower(),
            round(float(amount_usdc or 0.0), 6),
            datetime.now(timezone.utc).isoformat(),
        )
        with self._write_lock, self._connect() as conn:
            cur = conn.execute(
                """INSERT OR IGNORE INTO payment_guards
                       (tx_hash, endpoint, payer, amount_usdc, consumed_at)
                   VALUES (?, ?, ?, ?, ?)""",
                row,
            )
            conn.commit()
            # rowcount == 1 → we are the first consumer: claim granted.
            # rowcount == 0 → this hash was already spent (replay), no matter
            # which endpoint is asking now. Single-call semantics, always.
            return cur.rowcount > 0

    def payment_guard_stats(self) -> Dict[str, Any]:
        """Guard telemetry for the dashboard / ops (no PII)."""
        with self._connect() as conn:
            n = conn.execute(
                "SELECT COUNT(*) AS n FROM payment_guards"
            ).fetchone()
            by_ep = conn.execute(
                """SELECT endpoint, COUNT(*) AS n FROM payment_guards
                   GROUP BY endpoint"""
            ).fetchall()
            last = conn.execute(
                """SELECT consumed_at, endpoint FROM payment_guards
                   ORDER BY consumed_at DESC LIMIT 1"""
            ).fetchone()
        return {
            "consumed_total": n["n"],
            "by_endpoint": {r["endpoint"] or "unknown": r["n"] for r in by_ep},
            "last_claim_at": last["consumed_at"] if last else None,
            "last_claim_endpoint": last["endpoint"] if last else None,
        }

    # ── guard events: durable record of what the guards BLOCKED ───────────────
    def record_guard_event(self, kind: str, endpoint: str = "",
                           tx_hash: str = "", detail: str = "") -> None:
        """Persist a guard rejection (C1 replay / C2 depth / H2 binding).

        Deliberately separate from `payment_guards` (which records GRANTED
        claims): the dashboard needs to prove the guards are alive, and a
        blocked attempt is the only positive evidence that they fired.
        Never raises — telemetry must not affect a payment decision.
        """
        try:
            with self._write_lock, self._connect() as conn:
                conn.execute(
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
                conn.commit()
        except Exception as exc:  # pragma: no cover - telemetry only
            log.debug("guard event not recorded (%s): %s", kind, exc)

    def guard_stats(self, recent_limit: int = 5) -> Dict[str, Any]:
        """Live health of the C1 replay lock + the blocked attempts it made.

        `lock_alive` is a REAL probe: it writes and removes a sentinel row, so
        a broken/locked/read-only payment_guards table reports red instead of
        silently letting every replay through.
        """
        alive = False
        probe_error = ""
        try:
            sentinel = "__lock_probe__"
            with self._write_lock, self._connect() as conn:
                conn.execute(
                    "DELETE FROM payment_guards WHERE tx_hash = ?", (sentinel,)
                )
                conn.execute(
                    """INSERT INTO payment_guards
                           (tx_hash, endpoint, payer, amount_usdc, consumed_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (sentinel, "", "", 0.0,
                     datetime.now(timezone.utc).isoformat()),
                )
                conn.commit()
                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM payment_guards WHERE tx_hash = ?",
                    (sentinel,),
                ).fetchone()
                alive = bool(row and row["n"] == 1)
                conn.execute(
                    "DELETE FROM payment_guards WHERE tx_hash = ?", (sentinel,)
                )
                conn.commit()
        except Exception as exc:
            probe_error = str(exc)[:200]

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with self._connect() as conn:
            by_kind = conn.execute(
                """SELECT kind, COUNT(*) AS n FROM guard_events
                   GROUP BY kind ORDER BY n DESC"""
            ).fetchall()
            total_blocked = conn.execute(
                "SELECT COUNT(*) AS n FROM guard_events"
            ).fetchone()["n"]
            blocked_today = conn.execute(
                """SELECT COUNT(*) AS n FROM guard_events
                   WHERE substr(ts, 1, 10) = ?""",
                (today,),
            ).fetchone()["n"]
            recent = conn.execute(
                """SELECT ts, kind, endpoint, tx_hash, detail FROM guard_events
                   ORDER BY id DESC LIMIT ?""",
                (recent_limit,),
            ).fetchall()
        return {
            "lock_alive": alive,
            "lock_probe_error": probe_error or None,
            "blocked_total": total_blocked,
            "blocked_today": blocked_today,
            "by_kind": {r["kind"]: r["n"] for r in by_kind},
            "recent_blocks": [dict(r) for r in recent],
        }

    def sales_summary(self, history_limit: int = 100) -> Dict[str, Any]:
        """Aggregate on-chain sales straight from the persistent table."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with self._connect() as conn:
            totals = conn.execute(
                """SELECT COUNT(*) AS n,
                          COALESCE(SUM(amount_usdc), 0.0) AS total
                   FROM onchain_sales"""
            ).fetchone()
            today_row = conn.execute(
                """SELECT COUNT(*) AS n,
                          COALESCE(SUM(amount_usdc), 0.0) AS total
                   FROM onchain_sales WHERE substr(ts, 1, 10) = ?""",
                (today,),
            ).fetchone()
            by_class = conn.execute(
                """SELECT payer_class, COUNT(*) AS n,
                          COALESCE(SUM(amount_usdc), 0.0) AS total
                   FROM onchain_sales GROUP BY payer_class"""
            ).fetchall()
            external_payers = conn.execute(
                """SELECT COUNT(DISTINCT sender) AS n FROM onchain_sales
                   WHERE payer_class = 'external'"""
            ).fetchone()
            history = conn.execute(
                """SELECT tx_hash, block_number, ts, sender, amount_usdc,
                          payer_class, payer_label, source
                   FROM onchain_sales ORDER BY ts DESC, tx_hash DESC LIMIT ?""",
                (history_limit,),
            ).fetchall()

        classes: Dict[str, Dict[str, float]] = {}
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
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT sender, COUNT(*) AS n,
                          COALESCE(SUM(amount_usdc), 0.0) AS total,
                          MIN(ts) AS first_ts, MAX(ts) AS last_ts
                   FROM onchain_sales WHERE payer_class = 'external'
                   GROUP BY lower(sender)
                   ORDER BY total DESC, last_ts DESC"""
            ).fetchall()
            detail = conn.execute(
                """SELECT tx_hash, sender, amount_usdc, ts, block_number,
                          payer_class
                   FROM onchain_sales WHERE payer_class = 'external'
                   ORDER BY ts ASC, block_number ASC"""
            ).fetchall()
            guards = {
                (r["tx_hash"] or "").lower(): (r["endpoint"] or "")
                for r in conn.execute(
                    "SELECT tx_hash, endpoint FROM payment_guards"
                ).fetchall()
            }
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
        with self._write_lock, self._connect() as conn:
            conn.execute(
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
            conn.commit()

    def requests_summary(self, recent_limit: int = 25) -> Dict[str, Any]:
        """today/total + channel (/f/<name>) + source breakdown — from disk.

        The internal keep-alive traffic (UA 'Render/1.0' — our own /health
        pings plus Render health checks) is counted SEPARATELY so the
        "clean" customer/agent-facing numbers light up on their own.
        Also aggregates the payment FUNNEL per paid route (402 challenges ->
        paid follow-ups, today + total) — "caught by the hand" metric.
        """
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        internal_sql = "user_agent LIKE 'Render/%'"
        with self._connect() as conn:
            total = conn.execute(
                "SELECT COUNT(*) AS n FROM request_log"
            ).fetchone()["n"]
            today_row = conn.execute(
                "SELECT COUNT(*) AS n FROM request_log WHERE substr(ts, 1, 10) = ?",
                (today,),
            ).fetchone()["n"]
            noise_total = conn.execute(
                f"SELECT COUNT(*) AS n FROM request_log WHERE {internal_sql}"
            ).fetchone()["n"]
            noise_today = conn.execute(
                f"""SELECT COUNT(*) AS n FROM request_log
                    WHERE substr(ts, 1, 10) = ? AND {internal_sql}""",
                (today,),
            ).fetchone()["n"]
            by_source = conn.execute(
                """SELECT source, COUNT(*) AS n FROM request_log
                   GROUP BY source ORDER BY n DESC"""
            ).fetchall()
            by_source_clean = conn.execute(
                f"""SELECT source, COUNT(*) AS n FROM request_log
                    WHERE NOT ({internal_sql})
                    GROUP BY source ORDER BY n DESC"""
            ).fetchall()
            by_channel = conn.execute(
                """SELECT funnel AS channel, COUNT(*) AS n FROM request_log
                   WHERE funnel IS NOT NULL AND funnel <> ''
                   GROUP BY funnel ORDER BY n DESC"""
            ).fetchall()
            by_path = conn.execute(
                """SELECT path, COUNT(*) AS n FROM request_log
                   GROUP BY path ORDER BY n DESC LIMIT 10"""
            ).fetchall()
            top_user_agents = conn.execute(
                f"""SELECT user_agent, COUNT(*) AS n FROM request_log
                    WHERE user_agent <> '' AND NOT ({internal_sql})
                    GROUP BY user_agent ORDER BY n DESC LIMIT 10"""
            ).fetchall()
            hourly = conn.execute(
                """SELECT substr(ts, 12, 2) AS hour, COUNT(*) AS n,
                          SUM(CASE WHEN user_agent LIKE 'Render/%' THEN 1 ELSE 0 END)
                              AS noise
                   FROM request_log
                   WHERE substr(ts, 1, 10) = ?
                   GROUP BY substr(ts, 12, 2) ORDER BY hour""",
                (today,),
            ).fetchall()
            # ── payment funnel per paid route: 402 challenges vs paid retries ──
            funnel = {}
            for path in FUNNEL_ROUTES:
                cur = conn.execute(
                    """SELECT
                         SUM(CASE WHEN status_code = 402 THEN 1 ELSE 0 END) AS challenges,
                         SUM(CASE WHEN status_code = 200 THEN 1 ELSE 0 END) AS paid
                       FROM request_log WHERE path = ?""",
                    (path,),
                ).fetchone()
                cur_today = conn.execute(
                    """SELECT
                         SUM(CASE WHEN status_code = 402 THEN 1 ELSE 0 END) AS challenges,
                         SUM(CASE WHEN status_code = 200 THEN 1 ELSE 0 END) AS paid
                       FROM request_log
                       WHERE path = ? AND substr(ts, 1, 10) = ?""",
                    (path, today),
                ).fetchone()
                # BUGFIX (13.09): "today" used to be filled from the TOTAL
                # query (`cur`), so the dashboard's "Днес: 402 → платени"
                # column silently repeated the all-time numbers — a phantom
                # number on screen (cur_today was computed and thrown away).
                funnel[path] = {
                    "challenges_total": cur["challenges"] or 0,
                    "paid_total": cur["paid"] or 0,
                    "challenges_today": cur_today["challenges"] or 0,
                    "paid_today": cur_today["paid"] or 0,
                }
            recent = conn.execute(
                """SELECT ts, method, path, source, status_code, user_agent,
                          funnel
                   FROM request_log ORDER BY id DESC LIMIT ?""",
                (recent_limit,),
            ).fetchall()
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
            raise ConnectionError(
                f"RPC not reachable: {redact_rpc(rpc_url)}")

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
            raise ConnectionError(
                f"RPC not reachable: {redact_rpc(rpc_url)}")
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
                    with self._write_lock, self._connect() as conn:
                        cur = conn.execute(
                            """INSERT OR IGNORE INTO whaleflow_events
                                   (tx_hash, log_index, ts, token, amount_usdc,
                                    from_addr, to_addr, block_number, recorded_at)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (tx, ln, stamps[block].isoformat(), "USDC",
                             round(amount, 6), frm.lower(), to.lower(),
                             block, datetime.now(timezone.utc).isoformat()),
                        )
                        conn.commit()
                        added += cur.rowcount
                except Exception:
                    continue

        # SAME chunk/pacing/halving machine as the sales scan — the network-wide
        # query is simply a wider topic filter, not a second implementation.
        safe_end, effective_span = _adaptive_get_logs(
            w3, from_block, to_block, [TRANSFER_TOPIC, None, None],  # all
            chunk_blocks, pause_seconds, _collect,
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
        from_block = max(1, latest - int(hours * 86400 / BLOCK_TIME_SECONDS))
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
        cutoff = (datetime.now(timezone.utc)
                  - timedelta(hours=window_hours)).isoformat()
        scanned_until = self.get_meta("whaleflow_safe_scanned_block") or self.get_meta("whaleflow_last_block")
        # Honesty: a BROKEN scan must never look like a healthy empty feed.
        last_attempt = self.get_meta("whaleflow_last_attempt")
        last_error = self.get_meta("whaleflow_last_error")
        effective_chunk = self.get_meta("whaleflow_effective_chunk")
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT ts, token, amount_usdc, from_addr, to_addr,
                          tx_hash, block_number
                   FROM whaleflow_events
                   WHERE ts >= ? AND amount_usdc >= ?
                   ORDER BY ts DESC, block_number DESC LIMIT ?""",
                (cutoff, threshold, limit),
            ).fetchall()
            # Honesty: an empty window must be distinguishable from "the feed
            # never ran". all_time + last_event make that explicit on screen.
            all_time = conn.execute(
                """SELECT COUNT(*) AS n, MAX(ts) AS last_ts,
                          MAX(block_number) AS last_block
                   FROM whaleflow_events WHERE amount_usdc >= ?""",
                (threshold,),
            ).fetchone()
        whales = []
        for r in rows:
            whales.append({
                "ts": r["ts"],
                "token": r["token"],
                "amount_usdc": round(r["amount_usdc"], 6),
                "from": r["from_addr"],
                "to": r["to_addr"],
                "from_label": _label_address(r["from_addr"]),
                "to_label": _label_address(r["to_addr"]),
                "tx_hash": r["tx_hash"],
                "block": r["block_number"],
            })
        return {
            "whales": whales,
            "count": len(whales),
            "window_hours": window_hours,
            "threshold_usdc": threshold,
            "scanned_until_block": int(scanned_until or 0) or None,
            "all_time_count": all_time["n"] if all_time else 0,
            "last_event_at": all_time["last_ts"] if all_time else None,
            "last_event_block": (int(all_time["last_block"])
                                 if all_time and all_time["last_block"]
                                 else None),
            # "awaiting_whale" is a TRUTHFUL empty: the scan is running
            # (watermark advancing) and simply found nothing >= threshold.
            # "scan_failed" is the opposite: the scanner itself is broken, and
            # showing "чакаме кит" for it would hide a dead paid feed.
            # "scanning" covers the first (minutes-long) network-wide walk.
            "state": ("live_data" if whales
                      else "scan_failed" if last_error
                      else "awaiting_whale" if scanned_until
                      else "scanning" if last_attempt
                      else "scan_not_started"),
            "last_attempt_at": last_attempt or None,
            "last_error": last_error or None,
            "effective_chunk_blocks": (int(effective_chunk)
                                       if effective_chunk else None),
        }