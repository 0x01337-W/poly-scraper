from fastapi import APIRouter, Depends, Query
from opensearchpy import OpenSearch

from src.deps.auth import require_api_key
from src.deps.rate_limit import require_rate_limit
from src.search.client import get_client


router = APIRouter(
    prefix="/v1/candles",
    tags=["candles"],
    dependencies=[Depends(require_api_key), Depends(require_rate_limit)],
)


@router.get(
    "",
    summary="List candles",
    description="Return OHLCV candles for a market and interval within a time range.",
)
async def list_candles(
    market_id: str = Query(..., description="Market identifier"),
    interval: str = Query(..., pattern="^(1m|5m|1h)$", description="Candle interval"),
    _from: str = Query(..., alias="from", description="Start time (ISO8601)"),
    to: str = Query(..., description="End time (ISO8601)"),
    client: OpenSearch = Depends(get_client),
) -> dict:
    body = {
        "query": {
            "bool": {
                "must": [
                    {"term": {"market_id": market_id}},
                    {"term": {"interval": interval}},
                    {"range": {"open_time": {"gte": _from, "lte": to}}}
                ]
            }
        },
        "sort": [{"open_time": {"order": "asc"}}],
        "size": 2000
    }
    res = client.search(index="candles_v1", body=body)
    hits = [h["_source"] for h in res["hits"]["hits"]]
    return {"market_id": market_id, "interval": interval, "candles": hits}

