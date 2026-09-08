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
        """today/total + channel (/f/<name>) + source breakdown — from disk."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with self._connect() as conn:
            total = conn.execute(
                "SELECT COUNT(*) AS n FROM request_log"
            ).fetchone()["n"]
            today_row = conn.execute(
                "SELECT COUNT(*) AS n FROM request_log WHERE substr(ts, 1, 10) = ?",
                (today,),
            ).fetchone()["n"]
            by_source = conn.execute(
                """SELECT source, COUNT(*) AS n FROM request_log
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
            "by_source": [dict(r) for r in by_source],
            "by_channel": [dict(r) for r in by_channel],
            "top_paths": [dict(r) for r in by_path],
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
                start = end + 1
                continue
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