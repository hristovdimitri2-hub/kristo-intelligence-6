from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4


CATALOG_SEED: List[Dict[str, Any]] = [
    {
        "id": "whaleflow-radar",
        "name": "WhaleFlow Radar",
        "description": "On-chain whale, exchange-flow and smart-money movement signals with confidence.",
        "category": "onchain_intelligence",
        "price_x402": 0.03,
        "price_stripe": 19.0,
    },
    {
        "id": "cross-venue-signal-divergence",
        "name": "Cross-Venue Signal Divergence",
        "description": "Compares spot, perpetual and prediction-market signals to surface meaningful divergence.",
        "category": "market_intelligence",
        "price_x402": 0.04,
        "price_stripe": 24.0,
    },
    {
        "id": "token-launch-rug-risk-scanner",
        "name": "Token Launch & Rug Risk Scanner",
        "description": "Screens token-launch liquidity, deployer and contract red flags before a trade decision.",
        "category": "token_security",
        "price_x402": 0.06,
        "price_stripe": 29.0,
    },
    {
        "id": "defi-yield-risk-optimizer",
        "name": "DeFi Yield & Risk Optimizer",
        "description": "Ranks DeFi opportunities by net APY, liquidity and protocol risk without executing deposits.",
        "category": "defi",
        "price_x402": 0.03,
        "price_stripe": 19.0,
    },
    {
        "id": "gas-route-optimizer",
        "name": "Gas & Route Optimizer",
        "description": "Estimates gas, route cost and execution risk for swap and bridge decisions without signing.",
        "category": "transaction_intelligence",
        "price_x402": 0.01,
        "price_stripe": 12.0,
    },
    {
        "id": "ai-sentiment-narrative-pulse",
        "name": "AI Sentiment & Narrative Pulse",
        "description": "Combines market, news and social narrative momentum into a concise token or sector signal.",
        "category": "sentiment",
        "price_x402": 0.02,
        "price_stripe": 15.0,
    },
    {
        "id": "smart-contract-security-triage",
        "name": "Smart Contract Security Triage",
        "description": "First-pass verified-contract screening for access, upgrade, ownership and minting red flags.",
        "category": "security",
        "price_x402": 0.12,
        "price_stripe": 49.0,
    },
    {
        "id": "signal-to-channel-publisher",
        "name": "Signal-to-Channel Publisher",
        "description": "Turns an approved signal into compliant Telegram or X content for an authorized channel.",
        "category": "automation",
        "price_x402": 0.02,
        "price_stripe": 25.0,
    },
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_float(value: Any) -> float:
    return float(value or 0.0)


def _serialize_row(row: Dict[str, Any]) -> Dict[str, Any]:
    item = dict(row)
    for key in ("price_x402", "price_stripe", "total_revenue"):
        item[key] = _as_float(item.get(key))
    for key in ("click_count", "call_count"):
        item[key] = int(item.get(key) or 0)
    item["is_active"] = bool(item.get("is_active"))
    updated = item.get("last_updated")
    if hasattr(updated, "isoformat"):
        item["last_updated"] = updated.isoformat()
    return item


def _empty_metrics(product: Dict[str, Any]) -> Dict[str, Any]:
    return {
        **product,
        "clicks_24h": 0,
        "calls_24h": 0,
        "payments_24h": 0,
        "revenue_24h": 0.0,
        "conversion_rate_24h": 0.0,
        "popularity_rank": 0,
    }


def _rank_metrics(products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    for product in products:
        product["conversion_rate_24h"] = round(
            (product["payments_24h"] / product["clicks_24h"] * 100)
            if product["clicks_24h"]
            else 0.0,
            2,
        )
        # Calls remain visible, but are intentionally excluded until each
        # catalog SKU has a real execution endpoint emitting call events.
        product["_popularity_score"] = product["clicks_24h"] + (
            product["payments_24h"] * 10
        )
    products.sort(
        key=lambda product: (
            product["_popularity_score"],
            product["revenue_24h"],
            product["payments_24h"],
            product["clicks_24h"],
            product["name"],
        ),
        reverse=True,
    )
    for rank, product in enumerate(products, start=1):
        product["popularity_rank"] = rank
        product.pop("_popularity_score", None)
    return products


class CatalogStore:
    """Durable SQLite catalog and event store used for development and tests."""

    backend = "sqlite"

    def __init__(self, file_path: str | Path):
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_db()
        self.seed_catalog()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.file_path))
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS agent_skus (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    category TEXT NOT NULL,
                    price_x402 REAL NOT NULL,
                    price_stripe REAL NOT NULL,
                    click_count INTEGER NOT NULL DEFAULT 0,
                    call_count INTEGER NOT NULL DEFAULT 0,
                    total_revenue REAL NOT NULL DEFAULT 0,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    last_updated TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS agent_events (
                    event_id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    amount_usd REAL NOT NULL DEFAULT 0,
                    FOREIGN KEY(agent_id) REFERENCES agent_skus(id)
                );
                CREATE INDEX IF NOT EXISTS idx_agent_events_window
                    ON agent_events (occurred_at, agent_id, event_type);

                CREATE TABLE IF NOT EXISTS agent_checkouts (
                    checkout_id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    customer_email TEXT NOT NULL,
                    expected_amount REAL NOT NULL,
                    payment_status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    paid_at TEXT,
                    FOREIGN KEY(agent_id) REFERENCES agent_skus(id)
                );

                CREATE TABLE IF NOT EXISTS agent_entitlements (
                    checkout_id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    customer_email TEXT NOT NULL,
                    activated_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    FOREIGN KEY(agent_id) REFERENCES agent_skus(id)
                );
                CREATE INDEX IF NOT EXISTS idx_agent_entitlements_access
                    ON agent_entitlements (agent_id, customer_email, status, expires_at);

                CREATE TABLE IF NOT EXISTS agent_metrics_24h (
                    agent_id TEXT PRIMARY KEY,
                    computed_at TEXT NOT NULL,
                    window_started_at TEXT NOT NULL,
                    clicks INTEGER NOT NULL DEFAULT 0,
                    calls INTEGER NOT NULL DEFAULT 0,
                    payments INTEGER NOT NULL DEFAULT 0,
                    revenue REAL NOT NULL DEFAULT 0,
                    conversion_rate REAL NOT NULL DEFAULT 0,
                    popularity_rank INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY(agent_id) REFERENCES agent_skus(id)
                );
                """
            )

    def seed_catalog(self) -> None:
        now = _now().isoformat()
        with self._connect() as conn:
            for product in CATALOG_SEED:
                conn.execute(
                    """
                    INSERT INTO agent_skus (
                        id, name, description, category, price_x402, price_stripe,
                        is_active, last_updated
                    ) VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name=excluded.name,
                        description=excluded.description,
                        category=excluded.category,
                        price_x402=excluded.price_x402,
                        price_stripe=excluded.price_stripe,
                        is_active=excluded.is_active,
                        last_updated=excluded.last_updated
                    """,
                    (
                        product["id"],
                        product["name"],
                        product["description"],
                        product["category"],
                        product["price_x402"],
                        product["price_stripe"],
                        now,
                    ),
                )

    def get_product(self, product_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM agent_skus WHERE id = ? AND is_active = 1",
                (product_id,),
            ).fetchone()
        return _serialize_row(dict(row)) if row else None

    def get_catalog(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM agent_skus WHERE is_active = 1 ORDER BY name"
            ).fetchall()
        return [_serialize_row(dict(row)) for row in rows]

    def _record_event(
        self,
        product_id: str,
        event_type: str,
        amount_usd: float = 0.0,
        event_id: Optional[str] = None,
        occurred_at: Optional[datetime] = None,
    ) -> bool:
        if event_type not in {"click", "call", "payment"}:
            raise ValueError("unsupported catalog event type")
        if not self.get_product(product_id):
            return False

        event_id = event_id or f"{event_type}:{uuid4()}"
        now = (occurred_at or _now()).isoformat()
        amount = round(max(0.0, float(amount_usd or 0.0)), 6)
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO agent_events (
                    event_id, agent_id, event_type, occurred_at, amount_usd
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (event_id, product_id, event_type, now, amount),
            )
            if cursor.rowcount != 1:
                return False
            if event_type == "click":
                conn.execute(
                    "UPDATE agent_skus SET click_count = click_count + 1, last_updated = ? WHERE id = ?",
                    (now, product_id),
                )
            elif event_type == "call":
                conn.execute(
                    "UPDATE agent_skus SET call_count = call_count + 1, last_updated = ? WHERE id = ?",
                    (now, product_id),
                )
            else:
                conn.execute(
                    "UPDATE agent_skus SET total_revenue = total_revenue + ?, last_updated = ? WHERE id = ?",
                    (amount, now, product_id),
                )
        return True

    def record_click(self, product_id: str, event_id: Optional[str] = None) -> bool:
        return self._record_event(product_id, "click", event_id=event_id)

    def record_call(self, product_id: str, event_id: Optional[str] = None) -> bool:
        return self._record_event(product_id, "call", event_id=event_id)

    def record_payment(
        self, product_id: str, amount_usd: float, event_id: Optional[str] = None
    ) -> bool:
        return self._record_event(
            product_id, "payment", amount_usd=amount_usd, event_id=event_id
        )

    def register_checkout(
        self,
        checkout_id: str,
        product_id: str,
        customer_email: str,
        expected_amount: float,
    ) -> bool:
        """Persist the server-created Stripe session before a webhook may credit it."""
        if not checkout_id or not self.get_product(product_id):
            return False
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO agent_checkouts (
                    checkout_id, agent_id, customer_email, expected_amount, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    checkout_id,
                    product_id,
                    customer_email.lower(),
                    round(float(expected_amount), 2),
                    _now().isoformat(),
                ),
            )
        return cursor.rowcount == 1

    def _checkout_matches(
        self,
        checkout_id: str,
        product_id: str,
        customer_email: str,
        amount_usd: float,
    ) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM agent_checkouts WHERE checkout_id = ?",
                (checkout_id,),
            ).fetchone()
        return bool(
            row
            and row["agent_id"] == product_id
            and row["customer_email"] == customer_email.lower()
            and abs(_as_float(row["expected_amount"]) - float(amount_usd)) < 0.01
        )

    def _mark_checkout_paid(self, checkout_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE agent_checkouts
                SET payment_status = 'paid', paid_at = ?
                WHERE checkout_id = ?
                """,
                (_now().isoformat(), checkout_id),
            )

    def confirm_checkout_payment(
        self,
        checkout_id: str,
        product_id: str,
        customer_email: str,
        amount_usd: float,
    ) -> bool:
        """Validate a server-created checkout before attributing webhook revenue."""
        if not self._checkout_matches(
            checkout_id, product_id, customer_email, amount_usd
        ):
            return False
        self.record_payment(
            product_id,
            amount_usd,
            event_id=f"stripe:{checkout_id}",
        )
        self._mark_checkout_paid(checkout_id)
        return True

    def validate_checkout(
        self,
        checkout_id: str,
        product_id: str,
        customer_email: str,
        amount_usd: float,
    ) -> bool:
        """Check signed-webhook attributes against a server-created checkout."""
        return self._checkout_matches(
            checkout_id, product_id, customer_email, amount_usd
        )

    def grant_entitlement(
        self,
        checkout_id: str,
        product_id: str,
        customer_email: str,
        duration_days: int = 30,
        now: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        """Create an idempotent, time-bounded access right from a paid checkout."""
        if not checkout_id or not self.get_product(product_id):
            return None
        activated_at = now or _now()
        expires_at = activated_at + timedelta(days=duration_days)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO agent_entitlements (
                    checkout_id, agent_id, customer_email, activated_at, expires_at, status
                ) VALUES (?, ?, ?, ?, ?, 'active')
                """,
                (
                    checkout_id,
                    product_id,
                    customer_email.lower(),
                    activated_at.isoformat(),
                    expires_at.isoformat(),
                ),
            )
            row = conn.execute(
                "SELECT * FROM agent_entitlements WHERE checkout_id = ?",
                (checkout_id,),
            ).fetchone()
        return self._serialize_entitlement(dict(row)) if row else None

    @staticmethod
    def _serialize_entitlement(row: Dict[str, Any]) -> Dict[str, Any]:
        result = dict(row)
        for key in ("activated_at", "expires_at"):
            if hasattr(result.get(key), "isoformat"):
                result[key] = result[key].isoformat()
        return result

    def get_active_entitlement(
        self,
        product_id: str,
        customer_email: str,
        now: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        reference = now or _now()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM agent_entitlements
                WHERE agent_id = ? AND customer_email = ? AND status = 'active'
                ORDER BY expires_at DESC LIMIT 1
                """,
                (product_id, customer_email.lower()),
            ).fetchone()
            if not row:
                return None
            entitlement = self._serialize_entitlement(dict(row))
            expires_at = datetime.fromisoformat(entitlement["expires_at"])
            if expires_at <= reference:
                conn.execute(
                    "UPDATE agent_entitlements SET status = 'expired' WHERE checkout_id = ?",
                    (entitlement["checkout_id"],),
                )
                return None
        return entitlement

    def expire_entitlements(self, now: Optional[datetime] = None) -> int:
        reference = (now or _now()).isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE agent_entitlements
                SET status = 'expired'
                WHERE status = 'active' AND expires_at <= ?
                """,
                (reference,),
            )
        return cursor.rowcount

    def active_entitlement_count(self) -> int:
        self.expire_entitlements()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM agent_entitlements WHERE status = 'active'"
            ).fetchone()
        return int(row["count"] or 0)

    def recalculate_24h(self) -> Dict[str, Any]:
        window_start = _now() - timedelta(hours=24)
        products = {_product["id"]: _empty_metrics(_product) for _product in self.get_catalog()}
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT agent_id,
                    SUM(CASE WHEN event_type = 'click' THEN 1 ELSE 0 END) AS clicks,
                    SUM(CASE WHEN event_type = 'call' THEN 1 ELSE 0 END) AS calls,
                    SUM(CASE WHEN event_type = 'payment' THEN 1 ELSE 0 END) AS payments,
                    SUM(CASE WHEN event_type = 'payment' THEN amount_usd ELSE 0 END) AS revenue
                FROM agent_events
                WHERE occurred_at >= ?
                GROUP BY agent_id
                """,
                (window_start.isoformat(),),
            ).fetchall()
            for row in rows:
                metric = products.get(row["agent_id"])
                if metric:
                    metric["clicks_24h"] = int(row["clicks"] or 0)
                    metric["calls_24h"] = int(row["calls"] or 0)
                    metric["payments_24h"] = int(row["payments"] or 0)
                    metric["revenue_24h"] = round(_as_float(row["revenue"]), 6)

            ranked = _rank_metrics(list(products.values()))
            computed_at = _now().isoformat()
            for product in ranked:
                conn.execute(
                    """
                    INSERT INTO agent_metrics_24h (
                        agent_id, computed_at, window_started_at, clicks, calls, payments,
                        revenue, conversion_rate, popularity_rank
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(agent_id) DO UPDATE SET
                        computed_at=excluded.computed_at,
                        window_started_at=excluded.window_started_at,
                        clicks=excluded.clicks,
                        calls=excluded.calls,
                        payments=excluded.payments,
                        revenue=excluded.revenue,
                        conversion_rate=excluded.conversion_rate,
                        popularity_rank=excluded.popularity_rank
                    """,
                    (
                        product["id"],
                        computed_at,
                        window_start.isoformat(),
                        product["clicks_24h"],
                        product["calls_24h"],
                        product["payments_24h"],
                        product["revenue_24h"],
                        product["conversion_rate_24h"],
                        product["popularity_rank"],
                    ),
                )
        return self._metrics_payload(ranked)

    def _metrics_payload(self, products: List[Dict[str, Any]]) -> Dict[str, Any]:
        top_seller = max(
            products,
            key=lambda product: (
                product["revenue_24h"],
                product["payments_24h"],
                product["calls_24h"],
                product["clicks_24h"],
            ),
            default=None,
        )
        return {
            "window_hours": 24,
            "products": sorted(products, key=lambda product: product["popularity_rank"]),
            "totals": {
                "clicks": sum(product["clicks_24h"] for product in products),
                "calls": sum(product["calls_24h"] for product in products),
                "payments": sum(product["payments_24h"] for product in products),
                "revenue_usd": round(sum(product["revenue_24h"] for product in products), 6),
            },
            "top_selling_agent": (
                {
                    "id": top_seller["id"],
                    "name": top_seller["name"],
                    "revenue_24h": top_seller["revenue_24h"],
                    "payments_24h": top_seller["payments_24h"],
                }
                if top_seller
                else None
            ),
        }

    def get_metrics_24h(self) -> Dict[str, Any]:
        return self.recalculate_24h()

    def is_healthy(self) -> bool:
        try:
            with self._connect() as conn:
                return conn.execute("SELECT 1").fetchone() is not None
        except sqlite3.Error:
            return False


class PostgresCatalogStore(CatalogStore):
    """PostgreSQL-backed catalog store for durable production analytics."""

    backend = "postgresql"

    def __init__(self, database_url: str):
        self.database_url = database_url
        self._ensure_db()
        self.seed_catalog()

    def _connect(self):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError("psycopg is required for PostgreSQL catalog storage") from exc
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def _ensure_db(self) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_skus (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    category TEXT NOT NULL,
                    price_x402 DOUBLE PRECISION NOT NULL,
                    price_stripe DOUBLE PRECISION NOT NULL,
                    click_count INTEGER NOT NULL DEFAULT 0,
                    call_count INTEGER NOT NULL DEFAULT 0,
                    total_revenue DOUBLE PRECISION NOT NULL DEFAULT 0,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    last_updated TIMESTAMPTZ NOT NULL
                );
                CREATE TABLE IF NOT EXISTS agent_events (
                    event_id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL REFERENCES agent_skus(id),
                    event_type TEXT NOT NULL,
                    occurred_at TIMESTAMPTZ NOT NULL,
                    amount_usd DOUBLE PRECISION NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_agent_events_window
                    ON agent_events (occurred_at, agent_id, event_type);
                CREATE TABLE IF NOT EXISTS agent_checkouts (
                    checkout_id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL REFERENCES agent_skus(id),
                    customer_email TEXT NOT NULL,
                    expected_amount DOUBLE PRECISION NOT NULL,
                    payment_status TEXT NOT NULL DEFAULT 'pending',
                    created_at TIMESTAMPTZ NOT NULL,
                    paid_at TIMESTAMPTZ
                );
                CREATE TABLE IF NOT EXISTS agent_entitlements (
                    checkout_id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL REFERENCES agent_skus(id),
                    customer_email TEXT NOT NULL,
                    activated_at TIMESTAMPTZ NOT NULL,
                    expires_at TIMESTAMPTZ NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active'
                );
                CREATE INDEX IF NOT EXISTS idx_agent_entitlements_access
                    ON agent_entitlements (agent_id, customer_email, status, expires_at);
                CREATE TABLE IF NOT EXISTS agent_metrics_24h (
                    agent_id TEXT PRIMARY KEY REFERENCES agent_skus(id),
                    computed_at TIMESTAMPTZ NOT NULL,
                    window_started_at TIMESTAMPTZ NOT NULL,
                    clicks INTEGER NOT NULL DEFAULT 0,
                    calls INTEGER NOT NULL DEFAULT 0,
                    payments INTEGER NOT NULL DEFAULT 0,
                    revenue DOUBLE PRECISION NOT NULL DEFAULT 0,
                    conversion_rate DOUBLE PRECISION NOT NULL DEFAULT 0,
                    popularity_rank INTEGER NOT NULL DEFAULT 0
                );
                """
            )

    def seed_catalog(self) -> None:
        now = _now()
        with self._connect() as conn, conn.cursor() as cur:
            for product in CATALOG_SEED:
                cur.execute(
                    """
                    INSERT INTO agent_skus (
                        id, name, description, category, price_x402, price_stripe,
                        is_active, last_updated
                    ) VALUES (%s, %s, %s, %s, %s, %s, TRUE, %s)
                    ON CONFLICT(id) DO UPDATE SET
                        name=EXCLUDED.name,
                        description=EXCLUDED.description,
                        category=EXCLUDED.category,
                        price_x402=EXCLUDED.price_x402,
                        price_stripe=EXCLUDED.price_stripe,
                        is_active=EXCLUDED.is_active,
                        last_updated=EXCLUDED.last_updated
                    """,
                    (
                        product["id"],
                        product["name"],
                        product["description"],
                        product["category"],
                        product["price_x402"],
                        product["price_stripe"],
                        now,
                    ),
                )

    def get_product(self, product_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM agent_skus WHERE id = %s AND is_active = TRUE",
                (product_id,),
            )
            row = cur.fetchone()
        return _serialize_row(row) if row else None

    def get_catalog(self) -> List[Dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM agent_skus WHERE is_active = TRUE ORDER BY name")
            rows = cur.fetchall()
        return [_serialize_row(row) for row in rows]

    def _record_event(
        self,
        product_id: str,
        event_type: str,
        amount_usd: float = 0.0,
        event_id: Optional[str] = None,
        occurred_at: Optional[datetime] = None,
    ) -> bool:
        if event_type not in {"click", "call", "payment"}:
            raise ValueError("unsupported catalog event type")
        if not self.get_product(product_id):
            return False

        event_id = event_id or f"{event_type}:{uuid4()}"
        timestamp = occurred_at or _now()
        amount = round(max(0.0, float(amount_usd or 0.0)), 6)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO agent_events (
                    event_id, agent_id, event_type, occurred_at, amount_usd
                ) VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT(event_id) DO NOTHING
                RETURNING event_id
                """,
                (event_id, product_id, event_type, timestamp, amount),
            )
            if not cur.fetchone():
                return False
            if event_type == "click":
                cur.execute(
                    "UPDATE agent_skus SET click_count = click_count + 1, last_updated = %s WHERE id = %s",
                    (timestamp, product_id),
                )
            elif event_type == "call":
                cur.execute(
                    "UPDATE agent_skus SET call_count = call_count + 1, last_updated = %s WHERE id = %s",
                    (timestamp, product_id),
                )
            else:
                cur.execute(
                    "UPDATE agent_skus SET total_revenue = total_revenue + %s, last_updated = %s WHERE id = %s",
                    (amount, timestamp, product_id),
                )
        return True

    def register_checkout(
        self,
        checkout_id: str,
        product_id: str,
        customer_email: str,
        expected_amount: float,
    ) -> bool:
        if not checkout_id or not self.get_product(product_id):
            return False
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO agent_checkouts (
                    checkout_id, agent_id, customer_email, expected_amount, created_at
                ) VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT(checkout_id) DO NOTHING
                RETURNING checkout_id
                """,
                (
                    checkout_id,
                    product_id,
                    customer_email.lower(),
                    round(float(expected_amount), 2),
                    _now(),
                ),
            )
            return bool(cur.fetchone())

    def _checkout_matches(
        self,
        checkout_id: str,
        product_id: str,
        customer_email: str,
        amount_usd: float,
    ) -> bool:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM agent_checkouts WHERE checkout_id = %s",
                (checkout_id,),
            )
            row = cur.fetchone()
        return bool(
            row
            and row["agent_id"] == product_id
            and row["customer_email"] == customer_email.lower()
            and abs(_as_float(row["expected_amount"]) - float(amount_usd)) < 0.01
        )

    def _mark_checkout_paid(self, checkout_id: str) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE agent_checkouts
                SET payment_status = 'paid', paid_at = %s
                WHERE checkout_id = %s
                """,
                (_now(), checkout_id),
            )

    def grant_entitlement(
        self,
        checkout_id: str,
        product_id: str,
        customer_email: str,
        duration_days: int = 30,
        now: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        if not checkout_id or not self.get_product(product_id):
            return None
        activated_at = now or _now()
        expires_at = activated_at + timedelta(days=duration_days)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO agent_entitlements (
                    checkout_id, agent_id, customer_email, activated_at, expires_at, status
                ) VALUES (%s, %s, %s, %s, %s, 'active')
                ON CONFLICT(checkout_id) DO NOTHING
                """,
                (
                    checkout_id,
                    product_id,
                    customer_email.lower(),
                    activated_at,
                    expires_at,
                ),
            )
            cur.execute(
                "SELECT * FROM agent_entitlements WHERE checkout_id = %s",
                (checkout_id,),
            )
            row = cur.fetchone()
        return self._serialize_entitlement(row) if row else None

    def get_active_entitlement(
        self,
        product_id: str,
        customer_email: str,
        now: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        reference = now or _now()
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM agent_entitlements
                WHERE agent_id = %s AND customer_email = %s AND status = 'active'
                ORDER BY expires_at DESC LIMIT 1
                """,
                (product_id, customer_email.lower()),
            )
            row = cur.fetchone()
            if not row:
                return None
            entitlement = self._serialize_entitlement(row)
            expires_at = row["expires_at"]
            if expires_at <= reference:
                cur.execute(
                    "UPDATE agent_entitlements SET status = 'expired' WHERE checkout_id = %s",
                    (entitlement["checkout_id"],),
                )
                return None
        return entitlement

    def expire_entitlements(self, now: Optional[datetime] = None) -> int:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE agent_entitlements
                SET status = 'expired'
                WHERE status = 'active' AND expires_at <= %s
                """,
                (now or _now(),),
            )
            return cur.rowcount

    def active_entitlement_count(self) -> int:
        self.expire_entitlements()
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS count FROM agent_entitlements WHERE status = 'active'"
            )
            row = cur.fetchone()
        return int(row["count"] or 0)

    def recalculate_24h(self) -> Dict[str, Any]:
        window_start = _now() - timedelta(hours=24)
        products = {_product["id"]: _empty_metrics(_product) for _product in self.get_catalog()}
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT agent_id,
                    SUM(CASE WHEN event_type = 'click' THEN 1 ELSE 0 END) AS clicks,
                    SUM(CASE WHEN event_type = 'call' THEN 1 ELSE 0 END) AS calls,
                    SUM(CASE WHEN event_type = 'payment' THEN 1 ELSE 0 END) AS payments,
                    SUM(CASE WHEN event_type = 'payment' THEN amount_usd ELSE 0 END) AS revenue
                FROM agent_events
                WHERE occurred_at >= %s
                GROUP BY agent_id
                """,
                (window_start,),
            )
            for row in cur.fetchall():
                metric = products.get(row["agent_id"])
                if metric:
                    metric["clicks_24h"] = int(row["clicks"] or 0)
                    metric["calls_24h"] = int(row["calls"] or 0)
                    metric["payments_24h"] = int(row["payments"] or 0)
                    metric["revenue_24h"] = round(_as_float(row["revenue"]), 6)

            ranked = _rank_metrics(list(products.values()))
            computed_at = _now()
            for product in ranked:
                cur.execute(
                    """
                    INSERT INTO agent_metrics_24h (
                        agent_id, computed_at, window_started_at, clicks, calls, payments,
                        revenue, conversion_rate, popularity_rank
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT(agent_id) DO UPDATE SET
                        computed_at=EXCLUDED.computed_at,
                        window_started_at=EXCLUDED.window_started_at,
                        clicks=EXCLUDED.clicks,
                        calls=EXCLUDED.calls,
                        payments=EXCLUDED.payments,
                        revenue=EXCLUDED.revenue,
                        conversion_rate=EXCLUDED.conversion_rate,
                        popularity_rank=EXCLUDED.popularity_rank
                    """,
                    (
                        product["id"],
                        computed_at,
                        window_start,
                        product["clicks_24h"],
                        product["calls_24h"],
                        product["payments_24h"],
                        product["revenue_24h"],
                        product["conversion_rate_24h"],
                        product["popularity_rank"],
                    ),
                )
        return self._metrics_payload(ranked)

    def is_healthy(self) -> bool:
        try:
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute("SELECT 1")
                return cur.fetchone() is not None
        except Exception:
            return False


def create_catalog_store(
    sqlite_path: str | Path, database_url: Optional[str] = None
) -> CatalogStore | PostgresCatalogStore:
    """Use managed PostgreSQL when available, otherwise retain a SQLite preview store."""
    url = (database_url if database_url is not None else os.getenv("DATABASE_URL", "")).strip()
    return PostgresCatalogStore(url) if url else CatalogStore(sqlite_path)