import asyncio
import os
from typing import Any, Optional, Tuple
from datetime import datetime, timezone

import httpx
from opensearchpy import OpenSearch, helpers
import hashlib


POLYMARKET_GAMMA_BASE = os.getenv("POLYMARKET_GAMMA_BASE", "https://gamma-api.polymarket.com")
MARKETS_PAGE_SIZE = int(os.getenv("MARKETS_PAGE_SIZE", "250"))


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


async def fetch_markets_page(
    limit: Optional[int] = None,
    cursor: Optional[str] = None,
    page: Optional[int] = None,
    offset: Optional[int] = None,
) -> Tuple[list[dict[str, Any]], Optional[str], Optional[int]]:
    url = f"{POLYMARKET_GAMMA_BASE}/markets"
    params: dict[str, Any] = {}
    if limit is not None:
        params["limit"] = limit
    if cursor:
        params["cursor"] = cursor
    if page is not None:
        params["page"] = page
    if offset is not None:
        params["offset"] = offset
    headers = {"User-Agent": "PolyScraper/0.1", "Accept": "application/json"}
    print(f"[markets_worker] GET {url} params={params}")
    async with httpx.AsyncClient(timeout=30, headers=headers) as client:
        try:
            r = await client.get(url, params=params)
        except Exception as e:
            print(f"[markets_worker] request error: {e} url={url} params={params}")
            raise
        try:
            r.raise_for_status()
        except Exception as e:
            print(f"[markets_worker] fetch error: {e} url={url} status={r.status_code} body={r.text[:500]}")
            raise
        payload = r.json()
        print(f"[markets_worker] response status={r.status_code} len={len(r.text)}")
        data: list[dict[str, Any]] = []
        next_cursor: Optional[str] = None
        next_page: Optional[int] = None
        if isinstance(payload, dict):
            if "data" in payload and isinstance(payload["data"], list):
                data = payload["data"]
            elif isinstance(payload, list):
                data = payload  # type: ignore
            # cursor-based pagination keys vary; try common ones
            for key in ("next_cursor", "cursor", "next"):
                val = payload.get(key)
                if isinstance(val, str) and val:
                    next_cursor = val
                    break
            # increment page if present
            if "page" in payload and isinstance(payload.get("page"), int):
                try:
                    next_page = int(payload["page"]) + 1
                except Exception:
                    next_page = None
        elif isinstance(payload, list):
            data = payload
        return data, next_cursor, next_page


async def fetch_all_markets(page_size: int = MARKETS_PAGE_SIZE) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    cursor: Optional[str] = None
    page: Optional[int] = None
    offset: Optional[int] = 0
    safety_pages = 0
    while True:
        safety_pages += 1
        if safety_pages > 10000:
            break
        data, next_cursor, next_page = await fetch_markets_page(
            limit=page_size, cursor=cursor, page=page, offset=offset
        )
        print(f"[markets_worker] page#{safety_pages} got={len(data)} cursor={bool(next_cursor)} next_page={next_page} offset={offset}")
        if not data:
            break
        results.extend(data)
        # advance pagination: prefer cursor, then page, then offset heuristic
        if next_cursor:
            cursor = next_cursor
            page = None
            offset = None
        elif next_page is not None:
            page = next_page
            cursor = None
            offset = None
        else:
            # heuristic: if page returned exactly page_size, assume more via offset
            if len(data) < page_size:
                break
            offset = (offset or 0) + page_size
            cursor = None
            page = None
    print(f"[markets_worker] done pagination total={len(results)}")
    return results


def _to_iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    # numeric epoch seconds or milliseconds
    if isinstance(value, (int, float)):
        try:
            ts = float(value)
            # heuristic: if larger than ~10^12, treat as ms
            if ts > 1_000_000_000_000:
                dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
            else:
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            return dt.isoformat()
        except Exception:
            return None
    # string ISO or parseable
    if isinstance(value, str):
        v = value.strip()
        try:
            # handle trailing Z
            if v.endswith("Z"):
                v = v.replace("Z", "+00:00")
            dt = datetime.fromisoformat(v)
            return dt.astimezone(timezone.utc).isoformat()
        except Exception:
            # last resort: try int string
            try:
                return _to_iso(int(value))
            except Exception:
                return None
    return None


def to_es_doc(market: dict[str, Any]) -> dict[str, Any]:
    # Normalize fields commonly used by the API index and queries
    doc: dict[str, Any] = dict(market)
    # Ensure stable ids are present in the document
    if "market_id" not in doc and "id" in doc:
        doc["market_id"] = doc.get("id")
    # Normalize created_at from possible source fields
    created_sources = [
        "created_at",
        "createdAt",
        "created_time",
        "creation_time",
        "creationTime",
        "created",
        "openDate",
        "openTime",
        "start_date",
        "startDate",
        "start_time",
        "startTime",
    ]
    created_at: Optional[str] = None
    for key in created_sources:
        if key in doc and doc.get(key) is not None:
            created_at = _to_iso(doc.get(key))
            if created_at:
                break
    if created_at:
        doc["created_at"] = created_at
    return doc


def generate_market_id(market: dict[str, Any]) -> str:
    mid = str(market.get("id") or market.get("market_id") or "")
    if mid:
        return mid
    # Fallback: stable hash from title + createdAt if needed
    key = "|".join([str(market.get("title") or ""), str(market.get("created_at") or market.get("createdAt") or "")])
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def bulk_upsert_markets(markets: list[dict[str, Any]]) -> int:
    client = get_client()
    actions = []
    for m in markets:
        market_id = generate_market_id(m)
        doc = to_es_doc(m)
        actions.append(
            {
                "_op_type": "index",
                "_index": "markets_v1",
                "_id": market_id,
                "_source": doc,
            }
        )
    if not actions:
        return 0
    try:
        success, errors = helpers.bulk(client, actions, request_timeout=60, raise_on_error=False)
        if errors:
            try:
                # print first few errors for visibility
                print(f"[markets_worker] bulk errors count={len(errors)} sample={str(errors)[:400]}")
            except Exception:
                pass
        return int(success)
    except Exception as e:
        print(f"[markets_worker] bulk exception: {e}")
        return 0


async def run_markets_worker(poll_ms: int = 10000) -> None:
    print(f"[markets_worker] starting with poll_ms={poll_ms} base={POLYMARKET_GAMMA_BASE} page_size={MARKETS_PAGE_SIZE}")
    # Periodically fetch all markets with pagination and upsert
    while True:
        try:
            markets = await fetch_all_markets(page_size=MARKETS_PAGE_SIZE)
            count = bulk_upsert_markets(markets)
            print(f"[markets_worker] fetched={len(markets)} upserted={count}")
        except Exception as e:  # log minimal for now
            print(f"[markets_worker] error: {e}")
        await asyncio.sleep(poll_ms / 1000)

