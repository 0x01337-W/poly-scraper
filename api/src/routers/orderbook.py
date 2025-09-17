from typing import Optional
from fastapi import APIRouter, Depends, Query
from opensearchpy import OpenSearch

from src.deps.auth import require_api_key
from src.deps.rate_limit import require_rate_limit
from src.search.client import get_client


router = APIRouter(
    prefix="/v1/orderbook",
    tags=["orderbook"],
    dependencies=[Depends(require_api_key), Depends(require_rate_limit)],
)


@router.get(
    "",
    summary="Get order book snapshot",
    description="Get latest or time-aligned order book snapshot for a market and side.",
)
async def get_orderbook(
    market_id: str = Query(..., description="Market identifier"),
    side: str = Query("bid", pattern="^(bid|ask)$", description="Book side"),
    at: Optional[str] = Query(default=None, description="If set, returns the snapshot at/just before this time"),
    client: OpenSearch = Depends(get_client),
) -> dict:
    if at:
        body = {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"market_id": market_id}},
                        {"term": {"side": side}},
                        {"range": {"ts": {"lte": at}}}
                    ]
                }
            },
            "size": 1,
            "sort": [{"ts": {"order": "desc"}}]
        }
    else:
        body = {
            "query": {"bool": {"must": [{"term": {"market_id": market_id}}, {"term": {"side": side}}]}},
            "size": 1,
            "sort": [{"ts": {"order": "desc"}}]
        }
    res = client.search(index="orderbook_snapshots_v1", body=body)
    if not res["hits"]["hits"]:
        return {"market_id": market_id, "side": side, "levels": []}
    doc = res["hits"]["hits"][0]["_source"]
    return doc

