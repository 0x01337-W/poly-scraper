from typing import Optional
from fastapi import APIRouter, Depends, Query
from opensearchpy import OpenSearch

from src.deps.auth import require_api_key
from src.search.client import get_client


router = APIRouter(prefix="/v1/trades", tags=["trades"], dependencies=[Depends(require_api_key)])


@router.get("")
async def list_trades(
    market_id: str = Query(...),
    _from: Optional[str] = Query(default=None, alias="from"),
    to: Optional[str] = Query(default=None),
    sort: str = Query(default="ts:desc"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=100, ge=1, le=1000),
    client: OpenSearch = Depends(get_client),
) -> dict:
    sort_field, order = (sort.split(":", 1) + ["desc"])[:2]
    must = [{"term": {"market_id": market_id}}]
    if _from or to:
        rng: dict = {}
        if _from:
            rng["gte"] = _from
        if to:
            rng["lte"] = to
        must.append({"range": {"ts": rng}})

    body = {
        "query": {"bool": {"must": must}},
        "from": (page - 1) * limit,
        "size": limit,
        "sort": [{sort_field: {"order": order}}],
    }
    res = client.search(index="trades_v1-*", body=body)
    hits = [h["_source"] | {"_id": h["_id"], "_index": h["_index"]} for h in res["hits"]["hits"]]
    return {"data": hits, "page": page, "limit": limit}

