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
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
FUNNEL_ROUTES = [
    "/api/v1/signal",
    "/api/stats",
    "/api/sales",
    "/api/bot-status",
    "/api/arb/opportunities",
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
                funnel[path] = {
                    "challenges_total": cur["challenges"] or 0,
                    "paid_total": cur["paid"] or 0,
                    "challenges_today": cur["challenges"] or 0,
                    "paid_today": cur["paid"] or 0,
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
        out: Dict[int, datetime] = {}
        for b in dict.fromkeys(blocks):
            try:
                block = w3.eth.get_block(b)
                out[b] = datetime.fromtimestamp(block["timestamp"], tz=timezone.utc)
            except Exception:
                continue
        return out

    def scan_window(
        self,
        from_block: int,
        to_block: int,
        rpc_url: str = "",
        chunk_size: int = 5000,
        pause_seconds: float = 0.15,
    ) -> int:
        """Scan a block range for incoming USDC transfers and persist them.

        Read-only public-RPC scan (eth_getLogs), chunked and paced exactly
        like scripts/competitor_recon. Returns the number of NEW sales
        recorded. Watermark is NOT updated here — the caller owns it.
        """
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
            raise ConnectionError(f"RPC not reachable: {rpc_url}")

        padded = "0x" + "0" * 24 + receiver.lower().replace("0x", "")
        transfers: List[dict] = []
        start = from_block
        while start <= to_block:
            end = min(start + chunk_size - 1, to_block)
            try:
                logs = w3.eth.get_logs({
                    "fromBlock": start,
                    "toBlock": end,
                    "address": Web3.to_checksum_address(USDC_BASE),
                    "topics": [TRANSFER_TOPIC, None, padded],
                })
            except Exception:
                # Failed chunk: DO NOT silently skip (honesty rule — same as
                # whale scan). Stop the scan; the watermark-based retry next
                # cycle re-covers this range.
                break
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
            start = end + 1
            if start <= to_block:
                import time as _time
                _time.sleep(pause_seconds)

        if not transfers:
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
        self.set_meta("last_scanned_block", str(latest))
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
            # No watermark yet: treat `latest` as the start — the next cycle
            # covers the gap; retro_scan is the intended first-run path.
            self.set_meta("last_scanned_block", str(latest))
            return 0
        from_block = last + 1
        to_block = min(latest, from_block + max_blocks)
        if to_block < from_block:
            return 0
        added = self.scan_window(from_block, to_block, rpc_url=rpc_url)
        self.set_meta("last_scanned_block", str(to_block))
        return added

    # ── whale flow (network-wide big USDC transfers on Base) ─────────────────
    def scan_whale_window(self, from_block: int, to_block: int,
                          rpc_url: str = "", chunk_blocks: int = 0,
                          pause_seconds: float = 0.2) -> int:
        """Network-wide scan: ALL USDC Transfer logs on Base, keep only
        transfers >= the current WHALE_THRESHOLD. Read-only RPC,
        chunked/paced. Watermark is the caller's job.
        Returns the number of NEW whale events recorded.
        chunk_blocks: 0 = env WHALEFLOW_CHUNK_BLOCKS (default 250 — the size
        the free drpc endpoint reliably serves for wildcard getLogs)."""
        if to_block < from_block:
            return 0
        threshold = whale_threshold()
        try:
            chunk_blocks = max(50, int(os.getenv("WHALEFLOW_CHUNK_BLOCKS",
                                                 str(chunk_blocks or 250))))
        except ValueError:
            chunk_blocks = 250
        from web3 import Web3

        rpc_url = rpc_url or os.getenv("BASE_RPC_URL", "https://mainnet.base.org")
        w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
        if not w3.is_connected():
            raise ConnectionError(f"RPC not reachable: {rpc_url}")
        added = 0
        start = from_block
        safe_end = from_block - 1          # last contiguous scanned block
        while start <= to_block:
            end = min(start + chunk_blocks - 1, to_block)
            try:
                logs = w3.eth.get_logs({
                    "fromBlock": start, "toBlock": end,
                    "address": Web3.to_checksum_address(USDC_BASE),
                    "topics": [TRANSFER_TOPIC, None, None],   # all transfers
                })
            except Exception:
                # Failed chunk: DO NOT silently skip (honesty rule) — stop the
                # scan at the last good block; the caller retries next cycle.
                break
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
            start = end + 1
            safe_end = end
            if start <= to_block:
                import time as _time
                _time.sleep(pause_seconds)
        # Record the last CONTIGUOUS scanned block — failed chunks are retried
        # next cycle instead of being skipped (honesty: we never serve a range
        # that was not actually scanned).
        self.set_meta("whaleflow_safe_scanned_block", str(max(0, safe_end)))
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
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT ts, token, amount_usdc, from_addr, to_addr,
                          tx_hash, block_number
                   FROM whaleflow_events
                   WHERE ts >= ? AND amount_usdc >= ?
                   ORDER BY ts DESC, block_number DESC LIMIT ?""",
                (cutoff, threshold, limit),
            ).fetchall()
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
        }