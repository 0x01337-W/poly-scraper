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


@router.get("")
async def list_candles(
    market_id: str = Query(...),
    interval: str = Query(..., pattern="^(1m|5m|1h)$"),
    _from: str = Query(..., alias="from"),
    to: str = Query(...),
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

