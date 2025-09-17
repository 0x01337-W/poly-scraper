import os
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from opensearchpy import OpenSearch, helpers


POLYMARKET_CLOB_BASE = os.getenv("POLYMARKET_CLOB_BASE", "")
ORDERBOOK_DEPTH = int(os.getenv("ORDERBOOK_DEPTH", "10"))
ORDERBOOK_CHECKPOINT_PATH = os.getenv("ORDERBOOK_CHECKPOINT_PATH", "/data/orderbook_checkpoint.json")
ORDERBOOK_POLL_MS = int(os.getenv("ORDERBOOK_POLL_MS", "15000"))


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


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


def _load_checkpoint() -> dict:
    try:
        p = Path(ORDERBOOK_CHECKPOINT_PATH)
        if p.exists():
            return json.loads(p.read_text())
    except Exception:
        pass
    return {}


def _save_checkpoint(state: dict) -> None:
    try:
        p = Path(ORDERBOOK_CHECKPOINT_PATH)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(state))
    except Exception:
        pass


async def _fetch_top_n(market_id: str, side: str, depth: int) -> Optional[dict[str, Any]]:
    if not POLYMARKET_CLOB_BASE:
        return None
    url = f"{POLYMARKET_CLOB_BASE}/orderbook"
    params = {"market_id": market_id, "side": side, "depth": depth}
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, dict):
            return None
        return data


def _index_snapshot(client: OpenSearch, market_id: str, side: str, ts: str, levels: list[dict]) -> None:
    doc = {
        "market_id": market_id,
        "ts": ts,
        "side": side,
        "levels": levels,
    }
    doc_id = f"{market_id}:{side}:{ts}"
    helpers.bulk(
        client,
        [
            {
                "_op_type": "index",
                "_index": "orderbook_snapshots_v1",
                "_id": doc_id,
                "_source": doc,
            }
        ],
        request_timeout=30,
        raise_on_error=False,
    )


async def run_orderbook_worker() -> None:
    import asyncio

    client = get_client()
    state = _load_checkpoint()
    # For MVP, pull a configured set of market_ids from env (comma-separated)
    market_ids = [s.strip() for s in os.getenv("ORDERBOOK_MARKET_IDS", "").split(",") if s.strip()]
    if not market_ids:
        print("[orderbook_worker] No ORDERBOOK_MARKET_IDS configured; worker idle")
    while True:
        try:
            ts = _iso(datetime.now(timezone.utc))
            for mid in market_ids:
                for side in ("bid", "ask"):
                    ob = await _fetch_top_n(mid, side, ORDERBOOK_DEPTH)
                    if ob and isinstance(ob.get("levels"), list):
                        levels = ob["levels"][:ORDERBOOK_DEPTH]
                        _index_snapshot(client, mid, side, ts, levels)
            state["last_ts"] = ts
            _save_checkpoint(state)
        except Exception as e:
            print(f"[orderbook_worker] error: {e}")
        await asyncio.sleep(ORDERBOOK_POLL_MS / 1000)


