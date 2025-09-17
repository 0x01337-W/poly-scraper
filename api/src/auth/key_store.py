import os
import sqlite3
from dataclasses import dataclass
from typing import Optional


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS api_keys (
  key TEXT PRIMARY KEY,
  plan_type TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('active','revoked')),
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  expires_at TEXT
);
CREATE TABLE IF NOT EXISTS api_requests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL DEFAULT (datetime('now')),
  api_key TEXT,
  method TEXT NOT NULL,
  path TEXT NOT NULL,
  status INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_api_requests_ts ON api_requests(ts);
CREATE INDEX IF NOT EXISTS idx_api_requests_key ON api_requests(api_key);
"""


@dataclass
class ApiKeyRecord:
    key: str
    plan_type: str
    status: str
    created_at: str
    expires_at: Optional[str]


class ApiKeyStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.execute(SCHEMA_SQL)
            conn.commit()

    def upsert_key(self, key: str, plan_type: str = "monthly", status: str = "active", expires_at: Optional[str] = None) -> None:
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO api_keys(key, plan_type, status, expires_at) VALUES(?,?,?,?) ON CONFLICT(key) DO UPDATE SET plan_type=excluded.plan_type, status=excluded.status, expires_at=excluded.expires_at",
                (key, plan_type, status, expires_at),
            )
            conn.commit()

    def is_key_active(self, key: str) -> bool:
        with self._get_conn() as conn:
            cur = conn.execute(
                "SELECT status, COALESCE(expires_at, '') FROM api_keys WHERE key = ?",
                (key,),
            )
            row = cur.fetchone()
            if not row:
                return False
            status, expires_at = row
            if status != "active":
                return False
            # If expires_at is set and in the past, treat as inactive
            if expires_at:
                cur = conn.execute("SELECT datetime('now') >= datetime(?)", (expires_at,))
                expired = cur.fetchone()[0]
                if expired:
                    return False
            return True

    def log_request(self, api_key: str | None, method: str, path: str, status: int) -> None:
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO api_requests(api_key, method, path, status) VALUES(?,?,?,?)",
                (api_key, method, path, status),
            )
            conn.commit()

    def metrics_last_24h(self) -> list[tuple[str | None, int, int, int, int]]:
        with self._get_conn() as conn:
            cur = conn.execute(
                """
                SELECT api_key,
                       COUNT(*) AS total,
                       SUM(CASE WHEN status BETWEEN 200 AND 299 THEN 1 ELSE 0 END) AS s2xx,
                       SUM(CASE WHEN status BETWEEN 400 AND 499 THEN 1 ELSE 0 END) AS s4xx,
                       SUM(CASE WHEN status >= 500 THEN 1 ELSE 0 END) AS s5xx
                FROM api_requests
                WHERE ts >= datetime('now', '-1 day')
                GROUP BY api_key
                ORDER BY total DESC
                """
            )
            return cur.fetchall()


def bootstrap_default_key(store: ApiKeyStore) -> None:
    default_key = os.getenv("API_BOOTSTRAP_KEY", "")
    if default_key:
        store.upsert_key(default_key, plan_type=os.getenv("API_BOOTSTRAP_PLAN", "monthly"), status="active", expires_at=os.getenv("API_BOOTSTRAP_EXPIRES_AT"))

