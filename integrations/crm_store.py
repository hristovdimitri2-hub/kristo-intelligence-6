from __future__ import annotations

import json
import logging
import os
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

#: Fields that describe a PAYMENT, not a lead. Only `mark_paid()` may change them:
#: a re-submitted checkout form carries fresh empty defaults ("pending", 0.0) and
#: applying them blindly erased the sale record — payment_status back to pending,
#: amount_usd back to 0, and (before 17.09) no paid_at/checkout_id to lose yet.
_PAYMENT_FACTS = ("payment_status", "amount_usd", "paid_at", "checkout_id",
                  "status", "plan")


@dataclass
class LeadRecord:
    email: str
    source: str
    campaign: str
    utm_source: str = ""
    utm_medium: str = ""
    utm_campaign: str = ""
    status: str = "new"
    created_at: str = ""
    plan: str = ""
    telegram_chat_id: str = ""
    amount_usd: float = 0.0
    payment_status: str = "pending"
    #: WHEN the money arrived (the Stripe event's own timestamp) and WHICH Stripe
    #: session produced it. Until 17.09 the CRM had neither, so the dashboard dated
    #: a sale by the LEAD's creation — right by luck on the first sale (38 s apart),
    #: wrong by hours whenever a buyer pays later — and no CRM row could be joined
    #: to the Stripe payment at all.
    paid_at: str = ""
    checkout_id: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


class CRMStore:
    """SQLite-backed CRM store with JSON fallback for local launch operations."""

    backend = "sqlite"

    def __init__(self, file_path: str | Path):
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

        if self.file_path.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
            self._ensure_db()
            return

        if not self.file_path.exists():
            self.file_path.write_text("[]", encoding="utf-8")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.file_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS leads (
                    email TEXT PRIMARY KEY,
                    source TEXT,
                    campaign TEXT,
                    utm_source TEXT,
                    utm_medium TEXT,
                    utm_campaign TEXT,
                    status TEXT DEFAULT 'new',
                    created_at TEXT,
                    plan TEXT,
                    telegram_chat_id TEXT,
                    amount_usd REAL DEFAULT 0.0,
                    payment_status TEXT DEFAULT 'pending',
                    paid_at TEXT,
                    checkout_id TEXT
                )
                """
            )
            # Databases created before 17.09 lack the two payment facts; ALTER them
            # in rather than starting over (the table holds the only off-chain
            # money record — the first sale's row lives in it).
            existing = {row["name"] for row in
                        conn.execute("PRAGMA table_info(leads)").fetchall()}
            for column in ("paid_at", "checkout_id"):
                if column not in existing:
                    conn.execute("ALTER TABLE leads ADD COLUMN %s TEXT" % column)
            conn.commit()

    def _read(self) -> List[Dict[str, Any]]:
        if self.file_path.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
            with self._connect() as conn:
                rows = conn.execute("SELECT * FROM leads ORDER BY created_at").fetchall()
                return [dict(r) for r in rows]

        try:
            data = json.loads(self.file_path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []

    def _write(self, data: List[Dict[str, Any]]) -> None:
        if self.file_path.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
            with self._connect() as conn:
                conn.execute("DELETE FROM leads")
                for item in data:
                    conn.execute(
                        """
                        INSERT INTO leads (
                            email, source, campaign, utm_source, utm_medium, utm_campaign,
                            status, created_at, plan, telegram_chat_id, amount_usd, payment_status,
                            paid_at, checkout_id
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            item.get("email", ""),
                            item.get("source", "website"),
                            item.get("campaign", "launch"),
                            item.get("utm_source", ""),
                            item.get("utm_medium", ""),
                            item.get("utm_campaign", ""),
                            item.get("status", "new"),
                            item.get("created_at", datetime.now(timezone.utc).isoformat()),
                            item.get("plan", ""),
                            item.get("telegram_chat_id", ""),
                            float(item.get("amount_usd", 0.0) or 0.0),
                            item.get("payment_status", "pending"),
                            item.get("paid_at", ""),
                            item.get("checkout_id", ""),
                        ),
                    )
                conn.commit()
            return

        self.file_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def add_lead(self, lead: LeadRecord) -> Dict[str, Any]:
        payload = asdict(lead)
        if self.file_path.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
            with self._connect() as conn:
                existing = conn.execute("SELECT * FROM leads WHERE email = ?", (lead.email.lower(),)).fetchone()
                if existing:
                    paid_before = (existing["payment_status"] or "") == "paid"
                    conn.execute(
                        """
                        UPDATE leads SET source=?, campaign=?, utm_source=?, utm_medium=?, utm_campaign=?,
                        status=?, created_at=?, plan=?, telegram_chat_id=?, amount_usd=?, payment_status=?
                        WHERE email=?
                        """,
                        (
                            lead.source,
                            lead.campaign,
                            lead.utm_source,
                            lead.utm_medium,
                            lead.utm_campaign,
                            existing["status"] if paid_before else lead.status,
                            lead.created_at,
                            existing["plan"] if paid_before else lead.plan,
                            lead.telegram_chat_id,
                            float(existing["amount_usd"] or 0.0) if paid_before
                            else lead.amount_usd,
                            existing["payment_status"] if paid_before
                            else lead.payment_status,
                            lead.email.lower(),
                        ),
                    )
                    conn.commit()
                    # Return what is STORED, not the incoming lead merged over it:
                    # the caller must never be told "pending" for a paid lead.
                    updated = conn.execute("SELECT * FROM leads WHERE email = ?",
                                           (lead.email.lower(),)).fetchone()
                    return dict(updated) if updated else {**dict(existing), **payload}

                conn.execute(
                    """
                    INSERT INTO leads (
                        email, source, campaign, utm_source, utm_medium, utm_campaign,
                        status, created_at, plan, telegram_chat_id, amount_usd, payment_status,
                        paid_at, checkout_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        lead.email.lower(),
                        lead.source,
                        lead.campaign,
                        lead.utm_source,
                        lead.utm_medium,
                        lead.utm_campaign,
                        lead.status,
                        lead.created_at,
                        lead.plan,
                        lead.telegram_chat_id,
                        lead.amount_usd,
                        lead.payment_status,
                        lead.paid_at,
                        lead.checkout_id,
                    ),
                )
                conn.commit()
                return payload

        records = self._read()
        existing = self.find_by_email(lead.email)
        if existing:
            paid_before = existing.get("payment_status") == "paid"
            for key, value in payload.items():
                if paid_before and key in _PAYMENT_FACTS:
                    continue
                existing[key] = value
            self._write(records)
            return existing
        records.append(payload)
        self._write(records)
        return payload

    def get_all(self) -> List[Dict[str, Any]]:
        return self._read()

    def find_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        for item in self._read():
            if (item.get("email") or "").lower() == email.lower():
                return item
        return None

    def update_status(self, email: str, new_status: str) -> Optional[Dict[str, Any]]:
        if self.file_path.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
            with self._connect() as conn:
                row = conn.execute("SELECT * FROM leads WHERE email = ?", (email.lower(),)).fetchone()
                if not row:
                    return None
                conn.execute("UPDATE leads SET status = ? WHERE email = ?", (new_status, email.lower()))
                conn.commit()
                updated = conn.execute("SELECT * FROM leads WHERE email = ?", (email.lower(),)).fetchone()
                return dict(updated) if updated else None

        records = self._read()
        for item in records:
            if item.get("email", "").lower() == email.lower():
                item["status"] = new_status
                self._write(records)
                return item
        return None

    def mark_paid(self, email: str, amount_usd: float, plan: str = "",
                  checkout_id: str = "", paid_at: str = "") -> Optional[Dict[str, Any]]:
        """Record the sale. `paid_at` is WHEN THE MONEY ARRIVED (the Stripe event's
        own timestamp) and `checkout_id` is WHICH session paid — without them the
        dashboard dated a sale by the lead and nothing joined the CRM to Stripe."""
        if self.file_path.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
            with self._connect() as conn:
                row = conn.execute("SELECT * FROM leads WHERE email = ?", (email.lower(),)).fetchone()
                if not row:
                    return None
                conn.execute(
                    """
                    UPDATE leads SET payment_status = ?, status = ?, amount_usd = ?, plan = ?,
                        paid_at = CASE WHEN ? <> '' THEN ? ELSE paid_at END,
                        checkout_id = CASE WHEN ? <> '' THEN ? ELSE checkout_id END
                    WHERE email = ?
                    """,
                    ("paid", "qualified", float(amount_usd), plan or row["plan"],
                     paid_at, paid_at, checkout_id, checkout_id, email.lower()),
                )
                conn.commit()
                updated = conn.execute("SELECT * FROM leads WHERE email = ?", (email.lower(),)).fetchone()
                return dict(updated)

        records = self._read()
        for item in records:
            if item.get("email", "").lower() == email.lower():
                item["payment_status"] = "paid"
                item["status"] = "qualified"
                item["amount_usd"] = float(amount_usd)
                if plan:
                    item["plan"] = plan
                if paid_at:
                    item["paid_at"] = paid_at
                if checkout_id:
                    item["checkout_id"] = checkout_id
                self._write(records)
                return item
        return None

    def count_by_status(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for item in self._read():
            status = item.get("status", "unknown")
            counts[status] = counts.get(status, 0) + 1
        return counts

    def get_sales_pipeline(self) -> Dict[str, int]:
        pipeline = {"new": 0, "contacted": 0, "qualified": 0, "paid": 0, "won": 0}
        for item in self._read():
            status = item.get("status", "new")
            if status in pipeline:
                pipeline[status] += 1
            if item.get("payment_status") == "paid":
                pipeline["paid"] += 1
        return pipeline

    def is_healthy(self) -> bool:
        try:
            with self._connect() as conn:
                conn.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            return False


class PostgresCRMStore:
    """PostgreSQL-backed CRM store for durable Replit production data."""

    backend = "postgresql"

    def __init__(self, database_url: str):
        if not database_url:
            raise ValueError("database_url is required for PostgresCRMStore")
        self.database_url = database_url
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Create the `leads` table on first use — idempotent.

        AUDIT A2b (13.09): this class ASSUMED the table already existed. The
        moment DATABASE_URL pointed at a BRAND-NEW Render Postgres, every CRM
        read raised
            psycopg.errors.UndefinedTable: relation "leads" does not exist
        which turned /api/dashboard/data into an HTTP 500 for EVERYONE — the
        whole dashboard, not just the CRM section. The SQLite sibling has always
        created its own schema; this one now does the same.

        `created_at` is TEXT (not TIMESTAMPTZ) so the shape matches the SQLite
        table exactly: the insert path passes an ISO-8601 string, and ISO-8601
        sorts correctly as text, so no implicit cast can fail in production.
        """
        try:
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS leads (
                        email TEXT PRIMARY KEY,
                        source TEXT,
                        campaign TEXT,
                        utm_source TEXT,
                        utm_medium TEXT,
                        utm_campaign TEXT,
                        status TEXT DEFAULT 'new',
                        created_at TEXT,
                        plan TEXT,
                        telegram_chat_id TEXT,
                        amount_usd DOUBLE PRECISION DEFAULT 0.0,
                        payment_status TEXT DEFAULT 'pending',
                        paid_at TEXT,
                        checkout_id TEXT
                    )
                    """
                )
                # Migrate databases created before 17.09: the two payment facts are
                # added in place (the table holds the only off-chain money record).
                cur.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS paid_at TEXT")
                cur.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS "
                            "checkout_id TEXT")
                conn.commit()
            log.info("PostgreSQL CRM schema ready (leads).")
        except Exception as exc:
            # Booting must not die here: the app stays up so /health answers and
            # the failure stays visible in the logs on the first CRM call.
            log.warning("PostgreSQL CRM schema init failed: %s", exc)

    def _connect(self):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError("psycopg is required for PostgreSQL CRM storage") from exc

        return psycopg.connect(self.database_url, row_factory=dict_row)

    @staticmethod
    def _normalize(row: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(row)
        # Both timestamps are TEXT (ISO-8601) so the shape matches SQLite; a driver
        # that hands back a datetime must still serialize the same way.
        for field in ("created_at", "paid_at"):
            value = normalized.get(field)
            if hasattr(value, "isoformat"):
                normalized[field] = value.isoformat()
        amount = normalized.get("amount_usd")
        if amount is not None:
            normalized["amount_usd"] = float(amount)
        return normalized

    def _read(self) -> List[Dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM leads ORDER BY created_at")
            return [self._normalize(row) for row in cur.fetchall()]

    def add_lead(self, lead: LeadRecord) -> Dict[str, Any]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO leads (
                    email, source, campaign, utm_source, utm_medium, utm_campaign,
                    status, created_at, plan, telegram_chat_id, amount_usd, payment_status,
                    paid_at, checkout_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (email) DO UPDATE SET
                    source = EXCLUDED.source,
                    campaign = EXCLUDED.campaign,
                    utm_source = EXCLUDED.utm_source,
                    utm_medium = EXCLUDED.utm_medium,
                    utm_campaign = EXCLUDED.utm_campaign,
                    -- A PAID lead is never downgraded by a re-submitted form: the
                    -- incoming row carries "pending"/0.0 defaults, and applying them
                    -- reset payment_status and amount_usd — erasing the sale record.
                    -- paid_at / checkout_id are NOT in this list at all: only
                    -- mark_paid() writes them.
                    status = CASE WHEN leads.payment_status = 'paid'
                                  THEN leads.status ELSE EXCLUDED.status END,
                    created_at = EXCLUDED.created_at,
                    plan = CASE WHEN leads.payment_status = 'paid'
                                THEN leads.plan ELSE EXCLUDED.plan END,
                    telegram_chat_id = EXCLUDED.telegram_chat_id,
                    amount_usd = CASE WHEN leads.payment_status = 'paid'
                                      THEN leads.amount_usd ELSE EXCLUDED.amount_usd END,
                    payment_status = CASE WHEN leads.payment_status = 'paid'
                                          THEN leads.payment_status
                                          ELSE EXCLUDED.payment_status END
                RETURNING *
                """,
                (
                    lead.email.lower(),
                    lead.source,
                    lead.campaign,
                    lead.utm_source,
                    lead.utm_medium,
                    lead.utm_campaign,
                    lead.status,
                    lead.created_at,
                    lead.plan,
                    lead.telegram_chat_id,
                    float(lead.amount_usd),
                    lead.payment_status,
                    lead.paid_at,
                    lead.checkout_id,
                ),
            )
            row = cur.fetchone()
        return self._normalize(row)

    def get_all(self) -> List[Dict[str, Any]]:
        return self._read()

    def find_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM leads WHERE email = %s", (email.lower(),))
            row = cur.fetchone()
        return self._normalize(row) if row else None

    def update_status(self, email: str, new_status: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE leads SET status = %s WHERE email = %s RETURNING *",
                (new_status, email.lower()),
            )
            row = cur.fetchone()
        return self._normalize(row) if row else None

    def mark_paid(self, email: str, amount_usd: float, plan: str = "",
                  checkout_id: str = "", paid_at: str = "") -> Optional[Dict[str, Any]]:
        """Record the sale. `paid_at` is WHEN THE MONEY ARRIVED (the Stripe event's
        own timestamp) and `checkout_id` is WHICH session paid. Both keep their
        previous value when the caller has none (an empty string never erases a
        known payment time)."""
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE leads
                SET payment_status = 'paid',
                    status = 'qualified',
                    amount_usd = %s,
                    plan = CASE WHEN %s <> '' THEN %s ELSE plan END,
                    paid_at = CASE WHEN %s <> '' THEN %s ELSE paid_at END,
                    checkout_id = CASE WHEN %s <> '' THEN %s ELSE checkout_id END
                WHERE email = %s
                RETURNING *
                """,
                (float(amount_usd), plan, plan, paid_at, paid_at,
                 checkout_id, checkout_id, email.lower()),
            )
            row = cur.fetchone()
        return self._normalize(row) if row else None

    def count_by_status(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for item in self._read():
            status = item.get("status", "unknown")
            counts[status] = counts.get(status, 0) + 1
        return counts

    def get_sales_pipeline(self) -> Dict[str, int]:
        pipeline = {"new": 0, "contacted": 0, "qualified": 0, "paid": 0, "won": 0}
        for item in self._read():
            status = item.get("status", "new")
            if status in pipeline:
                pipeline[status] += 1
            if item.get("payment_status") == "paid":
                pipeline["paid"] += 1
        return pipeline

    def is_healthy(self) -> bool:
        try:
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute("SELECT 1")
                return cur.fetchone() is not None
        except Exception:
            return False


def create_crm_store(
    sqlite_path: str | Path,
    database_url: Optional[str] = None,
) -> CRMStore | PostgresCRMStore:
    """Use managed PostgreSQL when Replit supplies DATABASE_URL; otherwise SQLite."""
    url = (database_url if database_url is not None else os.getenv("DATABASE_URL", "")).strip()
    return PostgresCRMStore(url) if url else CRMStore(sqlite_path)
