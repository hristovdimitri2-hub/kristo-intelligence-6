from __future__ import annotations

import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional


class StripeVIPStore:
    """Durable binding between a standard Stripe Checkout and VIP fulfillment.

    Runtime PostgreSQL tables are created exclusively by the managed migration.
    The SQLite schema exists solely for isolated local tests and preview fallback.
    """

    def __init__(self, sqlite_path: str | Path, database_url: str = ""):
        self.database_url = database_url.strip()
        self.backend = "postgresql" if self.database_url else "sqlite"
        self.sqlite_path = Path(sqlite_path)
        if not self.database_url:
            self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            self._ensure_sqlite_schema()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _parse_time(value: Any) -> Optional[datetime]:
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc)
        if isinstance(value, str) and value:
            try:
                return datetime.fromisoformat(value).astimezone(timezone.utc)
            except ValueError:
                return None
        return None

    def _sqlite_connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.sqlite_path))
        connection.row_factory = sqlite3.Row
        return connection

    def _postgres_connection(self):
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(self.database_url, row_factory=dict_row)

    def _ensure_sqlite_schema(self) -> None:
        with self._sqlite_connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS stripe_vip_checkouts (
                    checkout_id TEXT PRIMARY KEY,
                    customer_email TEXT NOT NULL,
                    plan_key TEXT NOT NULL,
                    expected_amount_cents INTEGER NOT NULL,
                    currency TEXT NOT NULL,
                    source TEXT NOT NULL,
                    campaign TEXT NOT NULL,
                    link_token TEXT NOT NULL UNIQUE,
                    payment_status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    paid_at TEXT
                );
                CREATE TABLE IF NOT EXISTS stripe_webhook_events (
                    event_id TEXT PRIMARY KEY,
                    checkout_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    processing_token TEXT,
                    received_at TEXT NOT NULL,
                    completed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS stripe_vip_deliveries (
                    checkout_id TEXT PRIMARY KEY,
                    telegram_chat_id TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending_link',
                    invite_link TEXT NOT NULL DEFAULT '',
                    invite_expires_at TEXT,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT NOT NULL DEFAULT '',
                    delivery_lock_until TEXT,
                    delivery_lock_token TEXT,
                    updated_at TEXT NOT NULL
                );
                """
            )

    @staticmethod
    def _normalize(record: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if record is None:
            return None
        normalized = dict(record)
        for key in ("created_at", "paid_at", "received_at", "completed_at", "updated_at"):
            if hasattr(normalized.get(key), "isoformat"):
                normalized[key] = normalized[key].isoformat()
        return normalized

    def register_checkout(
        self,
        *,
        checkout_id: str,
        customer_email: str,
        plan_key: str,
        expected_amount_cents: int,
        currency: str,
        source: str,
        campaign: str,
        link_token: str,
    ) -> Dict[str, Any]:
        now = self._now()
        values = (
            checkout_id,
            customer_email.lower(),
            plan_key,
            int(expected_amount_cents),
            currency.lower(),
            source,
            campaign,
            link_token,
            now,
        )
        if self.backend == "sqlite":
            with self._sqlite_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO stripe_vip_checkouts (
                        checkout_id, customer_email, plan_key, expected_amount_cents,
                        currency, source, campaign, link_token, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(checkout_id) DO NOTHING
                    """,
                    values,
                )
            return self.get_checkout(checkout_id) or {}

        with self._postgres_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.stripe_vip_checkouts (
                    checkout_id, customer_email, plan_key, expected_amount_cents,
                    currency, source, campaign, link_token, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (checkout_id) DO NOTHING
                """,
                values,
            )
        return self.get_checkout(checkout_id) or {}

    def get_checkout(self, checkout_id: str) -> Optional[Dict[str, Any]]:
        if self.backend == "sqlite":
            with self._sqlite_connection() as conn:
                row = conn.execute(
                    "SELECT * FROM stripe_vip_checkouts WHERE checkout_id = ?",
                    (checkout_id,),
                ).fetchone()
                return self._normalize(dict(row) if row else None)
        with self._postgres_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM public.stripe_vip_checkouts WHERE checkout_id = %s",
                (checkout_id,),
            )
            return self._normalize(cur.fetchone())

    def get_checkout_by_link_token(self, link_token: str) -> Optional[Dict[str, Any]]:
        if self.backend == "sqlite":
            with self._sqlite_connection() as conn:
                row = conn.execute(
                    "SELECT * FROM stripe_vip_checkouts WHERE link_token = ?",
                    (link_token,),
                ).fetchone()
                return self._normalize(dict(row) if row else None)
        with self._postgres_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM public.stripe_vip_checkouts WHERE link_token = %s",
                (link_token,),
            )
            return self._normalize(cur.fetchone())

    def validate_checkout(
        self,
        checkout_id: str,
        customer_email: str,
        plan_key: str,
        amount_cents: int,
        currency: str,
    ) -> bool:
        checkout = self.get_checkout(checkout_id)
        return bool(
            checkout
            and checkout["customer_email"].lower() == customer_email.lower()
            and checkout["plan_key"] == plan_key
            and int(checkout["expected_amount_cents"]) == int(amount_cents)
            and checkout["currency"].lower() == currency.lower()
        )

    def get_webhook_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        if self.backend == "sqlite":
            with self._sqlite_connection() as conn:
                row = conn.execute(
                    "SELECT * FROM stripe_webhook_events WHERE event_id=?",
                    (event_id,),
                ).fetchone()
                return self._normalize(dict(row) if row else None)
        with self._postgres_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM public.stripe_webhook_events WHERE event_id=%s",
                (event_id,),
            )
            return self._normalize(cur.fetchone())

    def claim_webhook_event(
        self,
        event_id: str,
        checkout_id: str,
        event_type: str,
        lease_seconds: int = 300,
    ) -> Dict[str, str]:
        """Claim a Stripe event, safely reclaiming only an expired processing lease."""
        now = self._now()
        stale_before = datetime.now(timezone.utc) - timedelta(seconds=lease_seconds)
        processing_token = secrets.token_urlsafe(18)
        if self.backend == "sqlite":
            with self._sqlite_connection() as conn:
                existing = conn.execute(
                    "SELECT status, received_at FROM stripe_webhook_events WHERE event_id = ?",
                    (event_id,),
                ).fetchone()
                if existing and existing["status"] == "completed":
                    return {"status": "completed"}
                if (
                    existing
                    and existing["status"] == "processing"
                    and (
                        self._parse_time(existing["received_at"]) is None
                        or self._parse_time(existing["received_at"]) >= stale_before
                    )
                ):
                    return {"status": "processing"}
                if existing:
                    conn.execute(
                        """
                        UPDATE stripe_webhook_events
                        SET checkout_id=?, event_type=?, status='processing',
                            received_at=?, completed_at=NULL, processing_token=?
                        WHERE event_id=?
                        """,
                        (checkout_id, event_type, now, processing_token, event_id),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO stripe_webhook_events
                        (event_id, checkout_id, event_type, status, received_at, processing_token)
                        VALUES (?, ?, ?, 'processing', ?, ?)
                        """,
                        (event_id, checkout_id, event_type, now, processing_token),
                    )
                return {"status": "claimed", "processing_token": processing_token}
        with self._postgres_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.stripe_webhook_events
                (event_id, checkout_id, event_type, status, received_at, processing_token)
                VALUES (%s, %s, %s, 'processing', %s, %s)
                ON CONFLICT (event_id) DO UPDATE SET
                    checkout_id = EXCLUDED.checkout_id,
                    event_type = EXCLUDED.event_type,
                    status = 'processing',
                    received_at = EXCLUDED.received_at,
                    completed_at = NULL,
                    processing_token = EXCLUDED.processing_token
                WHERE public.stripe_webhook_events.status = 'failed'
                   OR (
                       public.stripe_webhook_events.status = 'processing'
                       AND public.stripe_webhook_events.received_at < %s
                   )
                RETURNING event_id
                """,
                (event_id, checkout_id, event_type, now, processing_token, stale_before),
            )
            if cur.fetchone() is not None:
                return {"status": "claimed", "processing_token": processing_token}
        event = self.get_webhook_event(event_id)
        return {"status": (event or {}).get("status", "processing")}

    def complete_webhook_event(self, event_id: str, processing_token: str) -> bool:
        now = self._now()
        query = (
            """
            UPDATE stripe_webhook_events
            SET status='completed', completed_at=?
            WHERE event_id=? AND status='processing' AND processing_token=?
            """
            if self.backend == "sqlite"
            else """
            UPDATE public.stripe_webhook_events
            SET status='completed', completed_at=%s
            WHERE event_id=%s AND status='processing' AND processing_token=%s
            """
        )
        if self.backend == "sqlite":
            with self._sqlite_connection() as conn:
                return conn.execute(query, (now, event_id, processing_token)).rowcount == 1
        with self._postgres_connection() as conn, conn.cursor() as cur:
            cur.execute(query, (now, event_id, processing_token))
            return cur.rowcount == 1

    def fail_webhook_event(self, event_id: str, processing_token: str) -> bool:
        query = (
            """
            UPDATE stripe_webhook_events
            SET status='failed'
            WHERE event_id=? AND status='processing' AND processing_token=?
            """
            if self.backend == "sqlite"
            else """
            UPDATE public.stripe_webhook_events
            SET status='failed'
            WHERE event_id=%s AND status='processing' AND processing_token=%s
            """
        )
        if self.backend == "sqlite":
            with self._sqlite_connection() as conn:
                return conn.execute(query, (event_id, processing_token)).rowcount == 1
        with self._postgres_connection() as conn, conn.cursor() as cur:
            cur.execute(query, (event_id, processing_token))
            return cur.rowcount == 1

    def mark_paid(self, checkout_id: str) -> Optional[Dict[str, Any]]:
        now = self._now()
        if self.backend == "sqlite":
            with self._sqlite_connection() as conn:
                conn.execute(
                    """
                    UPDATE stripe_vip_checkouts
                    SET payment_status='paid', paid_at=COALESCE(paid_at, ?)
                    WHERE checkout_id=?
                    """,
                    (now, checkout_id),
                )
            return self.get_checkout(checkout_id)
        with self._postgres_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE public.stripe_vip_checkouts
                SET payment_status='paid', paid_at=COALESCE(paid_at, %s)
                WHERE checkout_id=%s
                """,
                (now, checkout_id),
            )
        return self.get_checkout(checkout_id)

    def ensure_delivery(self, checkout_id: str) -> Optional[Dict[str, Any]]:
        checkout = self.get_checkout(checkout_id)
        if not checkout:
            return None
        now = self._now()
        initial_status = "pending_link"
        if self.backend == "sqlite":
            with self._sqlite_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO stripe_vip_deliveries (checkout_id, status, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(checkout_id) DO NOTHING
                    """,
                    (checkout_id, initial_status, now),
                )
        else:
            with self._postgres_connection() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO public.stripe_vip_deliveries (checkout_id, status, updated_at)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (checkout_id) DO NOTHING
                    """,
                    (checkout_id, initial_status, now),
                )
        return self.get_delivery(checkout_id)

    def get_delivery(self, checkout_id: str) -> Optional[Dict[str, Any]]:
        if self.backend == "sqlite":
            with self._sqlite_connection() as conn:
                row = conn.execute(
                    "SELECT * FROM stripe_vip_deliveries WHERE checkout_id=?",
                    (checkout_id,),
                ).fetchone()
                return self._normalize(dict(row) if row else None)
        with self._postgres_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM public.stripe_vip_deliveries WHERE checkout_id=%s",
                (checkout_id,),
            )
            return self._normalize(cur.fetchone())

    def link_telegram_account(self, link_token: str, chat_id: str) -> Optional[Dict[str, Any]]:
        checkout = self.get_checkout_by_link_token(link_token)
        if not checkout:
            return None
        self.ensure_delivery(checkout["checkout_id"])
        current = self.get_delivery(checkout["checkout_id"])
        if not current:
            return None
        existing_chat_id = (current.get("telegram_chat_id") or "").strip()
        if existing_chat_id and existing_chat_id != str(chat_id):
            return {"link_result": "conflict", **current}
        now = self._now()
        status = "pending_delivery" if checkout["payment_status"] == "paid" else "pending_payment"
        if self.backend == "sqlite":
            with self._sqlite_connection() as conn:
                result = conn.execute(
                    """
                    UPDATE stripe_vip_deliveries
                    SET telegram_chat_id=?,
                        status=CASE WHEN status='invite_sent' THEN status ELSE ? END,
                        updated_at=?
                    WHERE checkout_id=? AND (telegram_chat_id='' OR telegram_chat_id=?)
                    """,
                    (str(chat_id), status, now, checkout["checkout_id"], str(chat_id)),
                )
                if result.rowcount != 1:
                    return {"link_result": "conflict", **(self.get_delivery(checkout["checkout_id"]) or {})}
        else:
            with self._postgres_connection() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE public.stripe_vip_deliveries
                    SET telegram_chat_id=%s,
                        status=CASE WHEN status='invite_sent' THEN status ELSE %s END,
                        updated_at=%s
                    WHERE checkout_id=%s
                      AND (telegram_chat_id='' OR telegram_chat_id=%s)
                    RETURNING checkout_id
                    """,
                    (str(chat_id), status, now, checkout["checkout_id"], str(chat_id)),
                )
                if cur.fetchone() is None:
                    return {"link_result": "conflict", **(self.get_delivery(checkout["checkout_id"]) or {})}
        return {"link_result": "linked", **(self.get_delivery(checkout["checkout_id"]) or {})}

    def save_invite(
        self,
        checkout_id: str,
        invite_link: str,
        invite_expires_at: str,
        lock_token: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        return self._update_delivery(
            checkout_id,
            status="invite_created",
            invite_link=invite_link,
            invite_expires_at=invite_expires_at,
            last_error="",
            increment_attempts=True,
            lock_token=lock_token,
        )

    def mark_delivery(
        self,
        checkout_id: str,
        status: str,
        error: str = "",
        lock_token: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        return self._update_delivery(
            checkout_id,
            status=status,
            last_error=error[:240],
            increment_attempts=status != "invite_sent",
            lock_token=lock_token,
        )

    def _update_delivery(
        self,
        checkout_id: str,
        *,
        status: str,
        invite_link: Optional[str] = None,
        invite_expires_at: Optional[str] = None,
        last_error: str,
        increment_attempts: bool,
        lock_token: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        current = self.ensure_delivery(checkout_id)
        if not current:
            return None
        now = self._now()
        invite = current["invite_link"] if invite_link is None else invite_link
        expires_at = (
            current.get("invite_expires_at")
            if invite_expires_at is None
            else invite_expires_at
        )
        attempts = int(current["attempts"]) + (1 if increment_attempts else 0)
        if self.backend == "sqlite":
            with self._sqlite_connection() as conn:
                query = """
                    UPDATE stripe_vip_deliveries
                    SET status=?, invite_link=?, invite_expires_at=?, attempts=?, last_error=?, updated_at=?
                    WHERE checkout_id=?
                """
                values: tuple[Any, ...] = (
                    status, invite, expires_at, attempts, last_error, now, checkout_id
                )
                if lock_token:
                    query += " AND delivery_lock_token=?"
                    values += (lock_token,)
                result = conn.execute(query, values)
                if result.rowcount != 1:
                    return None
        else:
            with self._postgres_connection() as conn, conn.cursor() as cur:
                query = """
                    UPDATE public.stripe_vip_deliveries
                    SET status=%s, invite_link=%s, invite_expires_at=%s,
                        attempts=%s, last_error=%s, updated_at=%s
                    WHERE checkout_id=%s
                """
                values = (status, invite, expires_at, attempts, last_error, now, checkout_id)
                if lock_token:
                    query += " AND delivery_lock_token=%s"
                    values += (lock_token,)
                cur.execute(query, values)
                if cur.rowcount != 1:
                    return None
        return self.get_delivery(checkout_id)

    def invite_is_valid(self, delivery: Dict[str, Any]) -> bool:
        expires_at = self._parse_time(delivery.get("invite_expires_at"))
        return bool(
            delivery.get("invite_link")
            and expires_at
            and expires_at > datetime.now(timezone.utc)
        )

    def acquire_delivery_lock(
        self, checkout_id: str, lease_seconds: int = 120
    ) -> Optional[str]:
        now = datetime.now(timezone.utc)
        lock_until = (now + timedelta(seconds=lease_seconds)).isoformat()
        now_iso = now.isoformat()
        lock_token = secrets.token_urlsafe(18)
        if self.backend == "sqlite":
            with self._sqlite_connection() as conn:
                result = conn.execute(
                    """
                    UPDATE stripe_vip_deliveries
                    SET delivery_lock_until=?, delivery_lock_token=?
                    WHERE checkout_id=?
                      AND (delivery_lock_until IS NULL OR delivery_lock_until < ?)
                    """,
                    (lock_until, lock_token, checkout_id, now_iso),
                )
                return lock_token if result.rowcount == 1 else None
        with self._postgres_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE public.stripe_vip_deliveries
                SET delivery_lock_until=%s, delivery_lock_token=%s
                WHERE checkout_id=%s
                  AND (delivery_lock_until IS NULL OR delivery_lock_until < %s)
                RETURNING checkout_id
                """,
                (lock_until, lock_token, checkout_id, now_iso),
            )
            return lock_token if cur.fetchone() is not None else None

    def renew_delivery_lock(
        self, checkout_id: str, lock_token: str, lease_seconds: int = 120
    ) -> bool:
        now = datetime.now(timezone.utc)
        lock_until = (now + timedelta(seconds=lease_seconds)).isoformat()
        now_iso = now.isoformat()
        if self.backend == "sqlite":
            with self._sqlite_connection() as conn:
                result = conn.execute(
                    """
                    UPDATE stripe_vip_deliveries
                    SET delivery_lock_until=?
                    WHERE checkout_id=? AND delivery_lock_token=?
                      AND delivery_lock_until >= ?
                    """,
                    (lock_until, checkout_id, lock_token, now_iso),
                )
                return result.rowcount == 1
        with self._postgres_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE public.stripe_vip_deliveries
                SET delivery_lock_until=%s
                WHERE checkout_id=%s AND delivery_lock_token=%s
                  AND delivery_lock_until >= %s
                RETURNING checkout_id
                """,
                (lock_until, checkout_id, lock_token, now_iso),
            )
            return cur.fetchone() is not None

    def release_delivery_lock(self, checkout_id: str, lock_token: str) -> None:
        query = (
            """
            UPDATE stripe_vip_deliveries
            SET delivery_lock_until=NULL, delivery_lock_token=NULL
            WHERE checkout_id=? AND delivery_lock_token=?
            """
            if self.backend == "sqlite"
            else """
            UPDATE public.stripe_vip_deliveries
            SET delivery_lock_until=NULL, delivery_lock_token=NULL
            WHERE checkout_id=%s AND delivery_lock_token=%s
            """
        )
        if self.backend == "sqlite":
            with self._sqlite_connection() as conn:
                conn.execute(query, (checkout_id, lock_token))
            return
        with self._postgres_connection() as conn, conn.cursor() as cur:
            cur.execute(query, (checkout_id, lock_token))

    def is_healthy(self) -> bool:
        try:
            self.get_checkout("__healthcheck__")
            return True
        except Exception:
            return False


def create_stripe_vip_store(
    sqlite_path: str | Path,
    database_url: Optional[str] = None,
) -> StripeVIPStore:
    return StripeVIPStore(sqlite_path, database_url or os.getenv("DATABASE_URL", ""))