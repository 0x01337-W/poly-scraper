import asyncio
import os
import hashlib
from datetime import datetime, timezone
from typing import Any

import httpx
from opensearchpy import OpenSearch, helpers


POLYMARKET_TRADES_BASE = os.getenv("POLYMARKET_TRADES_BASE", "")


def get_client() -> OpenSearch:
    url = os.getenv("OPENSEARCH_URL", "https://opensearch:9200")
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
    # Normalize fields for consistent querying
    doc = dict(trade)
    ts_val = trade.get("ts") or trade.get("timestamp")
    if isinstance(ts_val, (int, float)):
        dt = datetime.fromtimestamp(int(ts_val), tz=timezone.utc)
        doc["ts"] = dt.isoformat()
    elif isinstance(ts_val, str):
        # assume ISO8601
        try:
            dt = datetime.fromisoformat(ts_val.replace("Z", "+00:00")).astimezone(timezone.utc)
            doc["ts"] = dt.isoformat()
        except Exception:
            doc["ts"] = datetime.now(timezone.utc).isoformat()
    else:
        doc["ts"] = datetime.now(timezone.utc).isoformat()

    # Map conditionId to market_id for consistency
    if "conditionId" in trade and "market_id" not in trade:
        doc["market_id"] = trade.get("conditionId")

    # Normalize side
    if "side" in trade and isinstance(trade["side"], str):
        doc["side"] = trade["side"].lower()

    return doc


def generate_trade_id(trade: dict[str, Any]) -> str:
    # Prefer transaction hash + asset + timestamp for uniqueness
    tx = str(trade.get("transactionHash") or trade.get("txHash") or "")
    asset = str(trade.get("asset") or "")
    ts = str(trade.get("timestamp") or trade.get("ts") or "")
    if tx and asset and ts:
        return f"{tx}:{asset}:{ts}"
    # Fallback to hash of key fields
    key = "|".join(
        [
            str(trade.get("conditionId") or trade.get("market_id") or ""),
            asset,
            str(trade.get("side") or ""),
            str(trade.get("price") or ""),
            str(trade.get("size") or ""),
            ts,
        ]
    )
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def bulk_upsert_trades(trades: list[dict[str, Any]]) -> int:
    if not trades:
        return 0
    client = get_client()
    actions = []
    for t in trades:
        trade_id = generate_trade_id(t)
        ts = str(t.get("ts") or t.get("timestamp") or "")
        if not ts:
            ts = datetime.now(timezone.utc).isoformat()
        index = index_for_timestamp(ts)
        doc = to_es_doc(t)
        action = {
            "_op_type": "create",
            "_index": index,
            "_source": doc,
        }
        action["_id"] = trade_id
        actions.append(action)
    if not actions:
        return 0
    success, _ = helpers.bulk(client, actions, request_timeout=60, raise_on_error=False)
    return int(success)


async def run_trades_worker(poll_ms: int = 3000) -> None:
    while True:
        try:
            trades = await fetch_trades()
            count = bulk_upsert_trades(trades)
            print(f"[trades_worker] created={count}")
        except Exception as e:
            print(f"[trades_worker] error: {e}")
        await asyncio.sleep(poll_ms / 1000)

