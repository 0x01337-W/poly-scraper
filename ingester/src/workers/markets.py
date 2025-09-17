import asyncio
import os
from typing import Any

import httpx
from opensearchpy import OpenSearch, helpers


POLYMARKET_GAMMA_BASE = os.getenv("POLYMARKET_GAMMA_BASE", "https://gamma-api.polymarket.com")


def get_client() -> OpenSearch:
    url = os.getenv("OPENSEARCH_URL", "https://localhost:9200")
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


def bulk_upsert_markets(markets: list[dict[str, Any]]) -> None:
    client = get_client()
    actions = []
    for m in markets:
        market_id = str(m.get("id") or m.get("market_id") or "")
        if not market_id:
            continue
        doc = to_es_doc(m)
        actions.append(
            {
                "_op_type": "index",
                "_index": "markets_v1",
                "_id": market_id,
                "_source": doc,
            }
        )
    if actions:
        helpers.bulk(client, actions, request_timeout=60)


async def run_markets_worker(poll_ms: int = 10000) -> None:
    # Simple loop: fetch and upsert periodically
    while True:
        try:
            markets = await fetch_markets()
            bulk_upsert_markets(markets)
        except Exception as e:  # log minimal for now
            print(f"[markets_worker] error: {e}")
        await asyncio.sleep(poll_ms / 1000)

