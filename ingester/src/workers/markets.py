import asyncio
import os
from typing import Any

import httpx
from opensearchpy import OpenSearch, helpers
import hashlib


POLYMARKET_GAMMA_BASE = os.getenv("POLYMARKET_GAMMA_BASE", "https://gamma-api.polymarket.com")


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


async def fetch_markets() -> list[dict[str, Any]]:
    url = f"{POLYMARKET_GAMMA_BASE}/markets"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url)
        r.raise_for_status()
        data = r.json()
        # Normalize to list of dicts
        if isinstance(data, dict) and "data" in data:
            return data["data"]
        if isinstance(data, list):
            return data
        return []


def to_es_doc(market: dict[str, Any]) -> dict[str, Any]:
    # Keep as-is initially; enrich later based on real payloads
    return market


def generate_market_id(market: dict[str, Any]) -> str:
    mid = str(market.get("id") or market.get("market_id") or "")
    if mid:
        return mid
    # Fallback: stable hash from title + createdAt if needed
    key = "|".join([str(market.get("title") or ""), str(market.get("created_at") or market.get("createdAt") or "")])
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def bulk_upsert_markets(markets: list[dict[str, Any]]) -> int:
    client = get_client()
    actions = []
    for m in markets:
        market_id = generate_market_id(m)
        doc = to_es_doc(m)
        actions.append(
            {
                "_op_type": "create",
                "_index": "markets_v1",
                "_id": market_id,
                "_source": doc,
            }
        )
    if not actions:
        return 0
    success, _ = helpers.bulk(client, actions, request_timeout=60, raise_on_error=False)
    return int(success)


async def run_markets_worker(poll_ms: int = 10000) -> None:
    # Simple loop: fetch and upsert periodically
    while True:
        try:
            markets = await fetch_markets()
            count = bulk_upsert_markets(markets)
            print(f"[markets_worker] upserted={count}")
        except Exception as e:  # log minimal for now
            print(f"[markets_worker] error: {e}")
        await asyncio.sleep(poll_ms / 1000)

