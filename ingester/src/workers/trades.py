import asyncio
import os
from datetime import datetime, timezone
from typing import Any

import httpx
from opensearchpy import OpenSearch, helpers


POLYMARKET_TRADES_BASE = os.getenv("POLYMARKET_TRADES_BASE", "")


def get_client() -> OpenSearch:
    url = os.getenv("OPENSEARCH_URL", "http://localhost:9200")
    user = os.getenv("OPENSEARCH_USER", "")
    password = os.getenv("OPENSEARCH_PASSWORD", "")
    auth = (user, password) if user and password else None
    client = OpenSearch(
        hosts=[url],
        http_auth=auth,
        verify_certs=False,
        ssl_show_warn=False,
        timeout=30,
        max_retries=3,
        retry_on_timeout=True,
    )
    return client


async def fetch_trades(market_id: str | None = None) -> list[dict[str, Any]]:
    if not POLYMARKET_TRADES_BASE:
        return []
    params = {"market_id": market_id} if market_id else {}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(POLYMARKET_TRADES_BASE, params=params)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict) and "data" in data:
            return data["data"]
        if isinstance(data, list):
            return data
        return []


def index_for_timestamp(ts: str) -> str:
    try:
        # Try ISO8601 parsing
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        dt = datetime.now(timezone.utc)
    return f"trades_v1-{dt.strftime('%Y.%m.%d')}"


def to_es_doc(trade: dict[str, Any]) -> dict[str, Any]:
    return trade


def bulk_upsert_trades(trades: list[dict[str, Any]]) -> None:
    if not trades:
        return
    client = get_client()
    actions = []
    for t in trades:
        trade_id = str(t.get("id") or t.get("trade_id") or "")
        ts = str(t.get("ts") or t.get("timestamp") or "")
        if not ts:
            ts = datetime.now(timezone.utc).isoformat()
        index = index_for_timestamp(ts)
        doc = to_es_doc(t)
        action = {
            "_op_type": "index",
            "_index": index,
            "_source": doc,
        }
        if trade_id:
            action["_id"] = trade_id
        actions.append(action)
    if actions:
        helpers.bulk(client, actions, request_timeout=60)


async def run_trades_worker(poll_ms: int = 3000) -> None:
    while True:
        try:
            trades = await fetch_trades()
            bulk_upsert_trades(trades)
        except Exception as e:
            print(f"[trades_worker] error: {e}")
        await asyncio.sleep(poll_ms / 1000)

