from typing import Optional
from fastapi import APIRouter, Depends, Query
from opensearchpy import OpenSearch

from src.deps.auth import require_api_key
from src.search.client import get_client


router = APIRouter(prefix="/v1/markets", tags=["markets"], dependencies=[Depends(require_api_key)])


@router.get("")
async def list_markets(
    q: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=100, ge=1, le=1000),
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
        "sort": [{"created_at": {"order": "desc"}}],
    }
    res = client.search(index="markets_v1", body=body)
    hits = [h["_source"] | {"_id": h["_id"]} for h in res["hits"]["hits"]]
    return {"data": hits, "page": page, "limit": limit}

