from typing import Optional
from fastapi import APIRouter, Depends, Query
from opensearchpy import OpenSearch

from src.deps.auth import require_api_key
from src.deps.rate_limit import require_rate_limit
from src.search.client import get_client


router = APIRouter(
    prefix="/v1/trades",
    tags=["trades"],
    dependencies=[Depends(require_api_key), Depends(require_rate_limit)],
)


@router.get(
    "",
    summary="List trades",
    description="List trades for a market within an optional time window. Supports sort and cursor-based pagination.",
)
async def list_trades(
    market_id: str = Query(..., description="Market identifier"),
    _from: Optional[str] = Query(default=None, alias="from", description="Start time (ISO8601)"),
    to: Optional[str] = Query(default=None, description="End time (ISO8601)"),
    sort: str = Query(default="ts:desc", description="Sort by ts asc|desc"),
    cursor: str | None = Query(default=None, description="Opaque cursor from previous page"),
    limit: int = Query(default=100, ge=1, le=1000, description="Page size (max 1000)"),
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
        "size": limit,
        "sort": [{sort_field: {"order": order}}, {"_id": {"order": order}}],
    }
    if cursor:
        # Expect cursor as "sortFieldValue|_id"
        try:
            parts = cursor.split("|", 1)
            sort_val = parts[0]
            doc_id = parts[1]
            # For date fields, pass the raw value; OpenSearch will parse
            body["search_after"] = [sort_val, doc_id]
        except Exception:
            pass
    res = client.search(index="trades_v1-*", body=body)
    hits_raw = res["hits"]["hits"]
    hits = [h["_source"] | {"_id": h["_id"], "_index": h["_index"]} for h in hits_raw]
    next_cursor = None
    if hits_raw:
        last = hits_raw[-1]
        last_sort = last.get("sort", [])
        if len(last_sort) >= 2:
            next_cursor = f"{last_sort[0]}|{last['_id']}"
    return {"data": hits, "limit": limit, "next_cursor": next_cursor}

