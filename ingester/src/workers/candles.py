import os
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Iterable

from opensearchpy import OpenSearch, helpers


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


def _load_checkpoint(interval: str, default_start: datetime) -> datetime:
    path = Path(os.getenv("CANDLES_CHECKPOINT_DIR", "/data")) / f"candles_checkpoint_{interval}.json"
    try:
        if path.exists():
            data = json.loads(path.read_text())
            ts = data.get("last_open_time")
            if ts:
                return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        pass
    return default_start


def _save_checkpoint(interval: str, open_time: datetime) -> None:
    path = Path(os.getenv("CANDLES_CHECKPOINT_DIR", "/data")) / f"candles_checkpoint_{interval}.json"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"last_open_time": _iso(open_time)}))
    except Exception:
        pass


def _interval_to_timedelta(interval: str) -> timedelta:
    if interval.endswith("m"):
        return timedelta(minutes=int(interval[:-1]))
    if interval.endswith("h"):
        return timedelta(hours=int(interval[:-1]))
    raise ValueError("Unsupported interval")


def _bucket_range(start: datetime, end: datetime, step: timedelta) -> Iterable[datetime]:
    t = start
    # align to step boundary (UTC)
    seconds = int(step.total_seconds())
    epoch = int(t.timestamp())
    aligned = epoch - (epoch % seconds)
    t = datetime.fromtimestamp(aligned, tz=timezone.utc)
    while t < end:
        yield t
        t = t + step


def _fetch_trades(client: OpenSearch, t0: datetime, t1: datetime, size: int) -> list[dict]:
    body = {
        "query": {
            "range": {
                "ts": {
                    "gte": _iso(t0),
                    "lt": _iso(t1),
                }
            }
        },
        "size": size,
        "sort": [{"ts": {"order": "asc"}}, {"_id": {"order": "asc"}}],
    }
    res = client.search(index="trades_v1-*", body=body)
    return [h["_source"] for h in res.get("hits", {}).get("hits", [])]


def _compute_candles(trades: list[dict], interval: str, bucket_start: datetime) -> list[dict]:
    by_market: dict[str, list[dict]] = {}
    for t in trades:
        mid = str(t.get("market_id") or "")
        if not mid:
            continue
        by_market.setdefault(mid, []).append(t)
    out: list[dict] = []
    for market_id, rows in by_market.items():
        if not rows:
            continue
        # rows are sorted asc by ts already
        def _price(x: dict) -> float:
            try:
                return float(x.get("price"))
            except Exception:
                return 0.0

        def _size(x: dict) -> float:
            try:
                return float(x.get("size"))
            except Exception:
                return 0.0

        open_p = _price(rows[0])
        close_p = _price(rows[-1])
        high_p = max((_price(r) for r in rows), default=open_p)
        low_p = min((_price(r) for r in rows), default=open_p)
        volume = sum(_size(r) for r in rows)
        out.append(
            {
                "market_id": market_id,
                "interval": interval,
                "open_time": _iso(bucket_start),
                "open": float(open_p),
                "high": float(high_p),
                "low": float(low_p),
                "close": float(close_p),
                "volume": float(volume),
            }
        )
    return out


def _bulk_index_candles(client: OpenSearch, docs: list[dict]) -> int:
    if not docs:
        return 0
    actions = []
    for d in docs:
        doc_id = f"{d['market_id']}:{d['interval']}:{d['open_time']}"
        actions.append(
            {
                "_op_type": "index",
                "_index": "candles_v1",
                "_id": doc_id,
                "_source": d,
            }
        )
    success, _ = helpers.bulk(client, actions, request_timeout=60, raise_on_error=False)
    return int(success)


async def run_candles_worker() -> None:
    client = get_client()
    intervals = os.getenv("CANDLES_INTERVALS", "1m,5m,1h").split(",")
    lookback_minutes = int(os.getenv("CANDLES_LOOKBACK_MINUTES", "180"))
    trades_fetch_limit = int(os.getenv("CANDLES_TRADES_FETCH_LIMIT", "5000"))
    poll_ms = int(os.getenv("CANDLES_POLL_MS", "60000"))
    while True:
        try:
            now = datetime.now(timezone.utc)
            for interval in intervals:
                interval = interval.strip()
                if not interval:
                    continue
                step = _interval_to_timedelta(interval)
                default_start = now - timedelta(minutes=lookback_minutes)
                t0 = _load_checkpoint(interval, default_start)
                # process buckets until we catch up to now-step (avoid open current bucket)
                for bstart in _bucket_range(t0, now - step, step):
                    bend = bstart + step
                    trades = _fetch_trades(client, bstart, bend, size=trades_fetch_limit)
                    candles = _compute_candles(trades, interval, bstart)
                    _bulk_index_candles(client, candles)
                    _save_checkpoint(interval, bend)
        except Exception as e:
            print(f"[candles_worker] error: {e}")
        finally:
            # sleep at end of full cycle across intervals
            import asyncio

            await asyncio.sleep(poll_ms / 1000)


