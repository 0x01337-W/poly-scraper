from typing import Optional
from fastapi import APIRouter, Depends, Query
from opensearchpy import OpenSearch

from src.deps.auth import require_api_key
from src.deps.rate_limit import require_rate_limit
from src.search.client import get_client


router = APIRouter(
    prefix="/v1/markets",
    tags=["markets"],
    dependencies=[Depends(require_api_key), Depends(require_rate_limit)],
)


@router.get(
    "",
    summary="List markets",
    description="Search and filter markets by free text, category, and status. Supports pagination and sort by created_at desc.",
)
async def list_markets(
    q: Optional[str] = Query(default=None, description="Free-text query across title, category, description"),
    category: Optional[str] = Query(default=None, description="Filter by category (keyword)"),
    status: Optional[str] = Query(default=None, description="Filter by status (e.g., open/closed)"),
    page: int = Query(default=1, ge=1, description="Page number (1-based)"),
    limit: int = Query(default=100, ge=1, le=1000, description="Page size (max 1000)"),
    client: OpenSearch = Depends(get_client),
) -> dict:
    must = []
    if q:
        must.append({"multi_match": {"query": q, "fields": ["title^2", "category", "description"]}})
    if category:
        must.append({"term": {"category": category}})
    if status:
        must.append({"term": {"status": status}})

    body = {
        "query": {"bool": {"must": must}} if must else {"match_all": {}},
        "from": (page - 1) * limit,
        "size": limit,
        "sort": [
            {
                "created_at": {
                    "order": "desc",
                    "unmapped_type": "date",
                }
            }
        ],
    }
    res = client.search(index="markets_v1", body=body)
    hits = [h["_source"] | {"_id": h["_id"]} for h in res["hits"]["hits"]]
    return {"data": hits, "page": page, "limit": limit}


@router.get(
    "/{market_id}",
    summary="Get a market by ID",
    description="Fetch a single market document by its ID; falls back to term lookup on the market_id field.",
)
async def get_market(
    market_id: str,
    client: OpenSearch = Depends(get_client),
) -> dict:
    try:
        res = client.get(index="markets_v1", id=market_id)
        src = res.get("_source", {})
        return src | {"_id": market_id}
    except Exception:
        # fallback search by field if direct get misses due to differing ids
        body = {"query": {"bool": {"must": [{"term": {"market_id": market_id}}]}}, "size": 1}
        res = client.search(index="markets_v1", body=body)
        if not res["hits"]["hits"]:
            return {"error": {"code": "not_found", "message": "Market not found"}}
        h = res["hits"]["hits"][0]
        return h["_source"] | {"_id": h["_id"]}

