from __future__ import annotations

import hashlib
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4


VALID_SOURCES = {"discord", "rss", "github"}
VALID_STATUSES = {"PENDING", "APPROVED", "ARCHIVED"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _serialize(row: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(row)
    for key in ("created_at", "updated_at"):
        if hasattr(result.get(key), "isoformat"):
            result[key] = result[key].isoformat()
    return result


def _normalize_source(value: str) -> str:
    source = (value or "").strip().lower()
    if source not in VALID_SOURCES:
        raise ValueError("unsupported research source")
    return source


def _normalize_text(value: str, field: str, maximum: int) -> str:
    text = (value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    if len(text) > maximum:
        raise ValueError(f"{field} is too long")
    return text


def _dedupe_key(source: str, title: str, content: str, external_id: str) -> str:
    if external_id:
        return f"{source}:{external_id[:500]}"
    digest = hashlib.sha256(f"{source}\n{title}\n{content}".encode()).hexdigest()
    return f"{source}:sha256:{digest}"


class ResearchInsightStore:
    """Durable research workflow storage for preview SQLite."""

    backend = "sqlite"

    def __init__(self, file_path: str | Path):
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.file_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS research_insights (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    external_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    actionable_summary TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_research_insights_dedupe
                    ON research_insights (source, external_id);
                CREATE INDEX IF NOT EXISTS idx_research_insights_status_created
                    ON research_insights (status, created_at DESC);
                """
            )

    def ingest(
        self,
        source: str,
        title: str,
        content: str,
        actionable_summary: str = "",
        external_id: str = "",
    ) -> Dict[str, Any]:
        source = _normalize_source(source)
        title = _normalize_text(title, "title", 300)
        content = _normalize_text(content, "content", 12000)
        actionable_summary = (actionable_summary or "").strip()[:2000]
        external_id = _dedupe_key(source, title, content, (external_id or "").strip())
        timestamp = _now().isoformat()
        insight_id = str(uuid4())

        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO research_insights (
                    id, source, external_id, title, content, actionable_summary,
                    status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?, ?)
                """,
                (
                    insight_id,
                    source,
                    external_id,
                    title,
                    content,
                    actionable_summary,
                    timestamp,
                    timestamp,
                ),
            )
            row = conn.execute(
                "SELECT * FROM research_insights WHERE source = ? AND external_id = ?",
                (source, external_id),
            ).fetchone()
        result = _serialize(dict(row))
        result["created"] = cursor.rowcount == 1
        return result

    def list_insights(
        self, status: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        limit = max(1, min(int(limit), 200))
        normalized_status = (status or "").strip().upper()
        if normalized_status and normalized_status not in VALID_STATUSES:
            raise ValueError("unsupported research status")
        with self._connect() as conn:
            if normalized_status:
                rows = conn.execute(
                    """
                    SELECT * FROM research_insights
                    WHERE status = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (normalized_status, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM research_insights ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [_serialize(dict(row)) for row in rows]

    def update_status(self, insight_id: str, status: str) -> Optional[Dict[str, Any]]:
        normalized_status = (status or "").strip().upper()
        if normalized_status not in VALID_STATUSES:
            raise ValueError("unsupported research status")
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE research_insights
                SET status = ?, updated_at = ?
                WHERE id = ?
                """,
                (normalized_status, _now().isoformat(), insight_id),
            )
            row = conn.execute(
                "SELECT * FROM research_insights WHERE id = ?", (insight_id,)
            ).fetchone()
        return _serialize(dict(row)) if row else None

    def is_healthy(self) -> bool:
        try:
            with self._connect() as conn:
                return conn.execute("SELECT 1").fetchone() is not None
        except sqlite3.Error:
            return False


class PostgresResearchInsightStore(ResearchInsightStore):
    """PostgreSQL parity for production research workflows."""

    backend = "postgresql"

    def __init__(self, database_url: str):
        self.database_url = database_url
        self._ensure_db()

    def _connect(self):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError("psycopg is required for PostgreSQL research storage") from exc
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def _ensure_db(self) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS research_insights (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    external_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    actionable_summary TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    created_at TIMESTAMPTZ NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_research_insights_dedupe
                    ON research_insights (source, external_id);
                CREATE INDEX IF NOT EXISTS idx_research_insights_status_created
                    ON research_insights (status, created_at DESC);
                """
            )

    def ingest(
        self,
        source: str,
        title: str,
        content: str,
        actionable_summary: str = "",
        external_id: str = "",
    ) -> Dict[str, Any]:
        source = _normalize_source(source)
        title = _normalize_text(title, "title", 300)
        content = _normalize_text(content, "content", 12000)
        actionable_summary = (actionable_summary or "").strip()[:2000]
        external_id = _dedupe_key(source, title, content, (external_id or "").strip())
        timestamp = _now()
        insight_id = str(uuid4())

        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO research_insights (
                    id, source, external_id, title, content, actionable_summary,
                    status, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, 'PENDING', %s, %s)
                ON CONFLICT(source, external_id) DO NOTHING
                RETURNING *
                """,
                (
                    insight_id,
                    source,
                    external_id,
                    title,
                    content,
                    actionable_summary,
                    timestamp,
                    timestamp,
                ),
            )
            row = cur.fetchone()
            created = bool(row)
            if not row:
                cur.execute(
                    "SELECT * FROM research_insights WHERE source = %s AND external_id = %s",
                    (source, external_id),
                )
                row = cur.fetchone()
        result = _serialize(row)
        result["created"] = created
        return result

    def list_insights(
        self, status: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        limit = max(1, min(int(limit), 200))
        normalized_status = (status or "").strip().upper()
        if normalized_status and normalized_status not in VALID_STATUSES:
            raise ValueError("unsupported research status")
        with self._connect() as conn, conn.cursor() as cur:
            if normalized_status:
                cur.execute(
                    """
                    SELECT * FROM research_insights
                    WHERE status = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (normalized_status, limit),
                )
            else:
                cur.execute(
                    "SELECT * FROM research_insights ORDER BY created_at DESC LIMIT %s",
                    (limit,),
                )
            rows = cur.fetchall()
        return [_serialize(row) for row in rows]

    def update_status(self, insight_id: str, status: str) -> Optional[Dict[str, Any]]:
        normalized_status = (status or "").strip().upper()
        if normalized_status not in VALID_STATUSES:
            raise ValueError("unsupported research status")
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE research_insights
                SET status = %s, updated_at = %s
                WHERE id = %s
                RETURNING *
                """,
                (normalized_status, _now(), insight_id),
            )
            row = cur.fetchone()
        return _serialize(row) if row else None

    def is_healthy(self) -> bool:
        try:
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute("SELECT 1")
                return cur.fetchone() is not None
        except Exception:
            return False


def create_research_store(
    sqlite_path: str | Path, database_url: Optional[str] = None
) -> ResearchInsightStore | PostgresResearchInsightStore:
    url = (database_url if database_url is not None else os.getenv("DATABASE_URL", "")).strip()
    return PostgresResearchInsightStore(url) if url else ResearchInsightStore(sqlite_path)