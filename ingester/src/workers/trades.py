import asyncio
import os
import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, Tuple

import httpx
from opensearchpy import OpenSearch, helpers


POLYMARKET_TRADES_BASE = os.getenv("POLYMARKET_TRADES_BASE", "")
TRADES_PAGE_SIZE = int(os.getenv("TRADES_PAGE_SIZE", "500"))
TRADES_BACKFILL_DAYS = int(os.getenv("TRADES_BACKFILL_DAYS", "7"))
TRADES_BACKFILL_WINDOW_MINUTES = int(os.getenv("TRADES_BACKFILL_WINDOW_MINUTES", "60"))
TRADES_CHECKPOINT_PATH = os.getenv("TRADES_CHECKPOINT_PATH", "/data/trades_checkpoint.json")


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


async def fetch_trades(
    market_id: Optional[str] = None,
    start_iso: Optional[str] = None,
    end_iso: Optional[str] = None,
    cursor: Optional[str] = None,
    page: Optional[int] = None,
    limit: Optional[int] = None,
) -> Tuple[list[dict[str, Any]], Optional[str], Optional[int]]:
    if not POLYMARKET_TRADES_BASE:
        return [], None, None
    params: dict[str, Any] = {}
    if market_id:
        params["market_id"] = market_id
    if start_iso:
        params["from"] = start_iso
    if end_iso:
        params["to"] = end_iso
    if cursor:
        params["cursor"] = cursor
    if page is not None:
        params["page"] = page
    if limit is not None:
        params["limit"] = limit
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(POLYMARKET_TRADES_BASE, params=params)
        r.raise_for_status()
        payload = r.json()
        # Try to normalize common response shapes
        data: list[dict[str, Any]] = []
        next_cursor: Optional[str] = None
        next_page: Optional[int] = None
        if isinstance(payload, dict):
            if "data" in payload and isinstance(payload["data"], list):
                data = payload["data"]
            elif isinstance(payload, list):
                data = payload  # type: ignore
            # find cursor
            for key in ("next_cursor", "cursor", "next"):
                val = payload.get(key)
                if isinstance(val, str) and val:
                    next_cursor = val
                    break
            # find page
            if "page" in payload and isinstance(payload.get("page"), int):
                p = int(payload["page"]) + 1
                next_page = p
        elif isinstance(payload, list):
            data = payload
        return data, next_cursor, next_page


def index_for_timestamp(ts: str) -> str:
    try:
        # Try ISO8601 parsing
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        dt = datetime.now(timezone.utc)
    return f"trades_v1-{dt.strftime('%Y.%m.%d')}"


def to_es_doc(trade: dict[str, Any]) -> dict[str, Any]:
    # Normalize to the mapping: trade_id (implicit via _id), market_id, ts, price, size, side
    out: dict[str, Any] = {}
    # ts normalization
    ts_val = trade.get("ts") or trade.get("timestamp")
    if isinstance(ts_val, (int, float)):
        dt = datetime.fromtimestamp(int(ts_val), tz=timezone.utc)
        out["ts"] = dt.isoformat()
    elif isinstance(ts_val, str):
        try:
            dt = datetime.fromisoformat(ts_val.replace("Z", "+00:00")).astimezone(timezone.utc)
            out["ts"] = dt.isoformat()
        except Exception:
            out["ts"] = datetime.now(timezone.utc).isoformat()
    else:
        out["ts"] = datetime.now(timezone.utc).isoformat()

    # market_id
    if "market_id" in trade:
        out["market_id"] = trade["market_id"]
    elif "conditionId" in trade:
        out["market_id"] = trade.get("conditionId")

    # numeric fields
    if "price" in trade:
        try:
            out["price"] = float(trade["price"])  # type: ignore
        except Exception:
            pass
    if "size" in trade:
        try:
            out["size"] = float(trade["size"])  # type: ignore
        except Exception:
            pass

    # side
    if "side" in trade and isinstance(trade["side"], str):
        out["side"] = trade["side"].lower()

    return out


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
        ts_val = t.get("ts") or t.get("timestamp")
        if not ts_val:
            ts_val = datetime.now(timezone.utc).isoformat()
        index = index_for_timestamp(str(ts_val))
        doc = to_es_doc(t)
        action = {
            "_op_type": "index",  # idempotent upsert
            "_index": index,
            "_id": trade_id,
            "_source": doc,
        }
        actions.append(action)
    if not actions:
        return 0
    success, _ = helpers.bulk(client, actions, request_timeout=60, raise_on_error=False)
    return int(success)


def _load_checkpoint() -> dict:
    try:
        p = Path(TRADES_CHECKPOINT_PATH)
        if p.exists():
            return json.loads(p.read_text())
    except Exception:
        pass
    return {}


def _save_checkpoint(state: dict) -> None:
    try:
        p = Path(TRADES_CHECKPOINT_PATH)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(state))
    except Exception:
        pass


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


async def backfill_trades(
    days: int = TRADES_BACKFILL_DAYS,
    window_minutes: int = TRADES_BACKFILL_WINDOW_MINUTES,
    page_size: int = TRADES_PAGE_SIZE,
) -> None:
    if not POLYMARKET_TRADES_BASE:
        return
    state = _load_checkpoint()
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    # resume from checkpoint if available
    if state.get("last_ts"):
        try:
            start = datetime.fromisoformat(state["last_ts"].replace("Z", "+00:00")).astimezone(timezone.utc)
        except Exception:
            pass
    cursor: Optional[str] = None
    t0 = start
    while t0 < now:
        t1 = min(t0 + timedelta(minutes=window_minutes), now)
        window_from, window_to = _iso(t0), _iso(t1)
        page: Optional[int] = None
        while True:
            data, next_cursor, next_page = await fetch_trades(
                start_iso=window_from, end_iso=window_to, cursor=cursor, page=page, limit=page_size
            )
            if not data:
                break
            bulk_upsert_trades(data)
            # advance pagination
            if next_cursor:
                cursor = next_cursor
                page = None
            elif next_page is not None:
                page = next_page
                cursor = None
            else:
                # heuristic: if less than page size, assume done
                if len(data) < page_size:
                    break
                page = (page or 1) + 1
        # update checkpoint to end of window
        state["last_ts"] = window_to
        _save_checkpoint(state)
        t0 = t1


async def run_trades_worker(poll_ms: int = 3000) -> None:
    # One-time backfill on startup (resumable via checkpoint)
    try:
        await backfill_trades()
    except Exception as e:
        print(f"[trades_worker] backfill error: {e}")
    # Incremental polling using moving window since last checkpoint
    while True:
        try:
            state = _load_checkpoint()
            last_ts = state.get("last_ts")
            now_iso = _iso(datetime.now(timezone.utc))
            data, _, _ = await fetch_trades(start_iso=last_ts, end_iso=now_iso, limit=TRADES_PAGE_SIZE)
            count = bulk_upsert_trades(data)
            # advance checkpoint if we ingested anything
            if count:
                state["last_ts"] = now_iso
                _save_checkpoint(state)
            print(f"[trades_worker] upserted={count}")
        except Exception as e:
            print(f"[trades_worker] error: {e}")
        await asyncio.sleep(poll_ms / 1000)

