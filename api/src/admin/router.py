import os
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from passlib.hash import bcrypt
from starlette.templating import Jinja2Templates
from opensearchpy import OpenSearch

from src.search.client import get_client
from src.auth.key_store import ApiKeyStore


router = APIRouter(prefix="/admin", tags=["admin"])


templates = Jinja2Templates(directory=os.getenv("ADMIN_TEMPLATES_DIR", "/app/src/admin/templates"))


def _is_logged_in(request: Request) -> bool:
    return bool(request.session.get("admin_auth"))


def require_admin(request: Request) -> None:
    if not _is_logged_in(request):
        raise RedirectResponse(url="/admin/login", status_code=status.HTTP_302_FOUND)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    if _is_logged_in(request):
        return RedirectResponse(url="/admin", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)) -> Response:
    expected_user = os.getenv("ADMIN_USERNAME", "admin")
    expected_hash = os.getenv("ADMIN_PASSWORD_HASH", "")
    if username != expected_user or not expected_hash or not bcrypt.verify(password, expected_hash):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials"}, status_code=status.HTTP_401_UNAUTHORIZED)
    request.session["admin_auth"] = True
    return RedirectResponse(url="/admin", status_code=status.HTTP_302_FOUND)


@router.post("/logout")
async def logout(request: Request) -> Response:
    request.session.clear()
    return RedirectResponse(url="/admin/login", status_code=status.HTTP_302_FOUND)


@router.get("", response_class=HTMLResponse)
async def admin_home(request: Request) -> HTMLResponse:
    require_admin(request)
    # OpenSearch health and index counts
    client: OpenSearch = get_client()
    try:
        health = client.cluster.health()
    except Exception as e:
        health = {"status": "unknown", "error": str(e)}
    indices = {}
    try:
        for name in ["markets_v1", "candles_v1", "orderbook_snapshots_v1"]:
            try:
                res = client.count(index=name)
                indices[name] = res.get("count", 0)
            except Exception:
                indices[name] = None
        # trades is time-sliced; sum across patterns
        try:
            cat = client.cat.indices(index="trades_v1-*", format="json")
            total = 0
            for row in cat:
                idx = row.get("index")
                try:
                    c = client.count(index=idx).get("count", 0)
                    total += c
                except Exception:
                    pass
            indices["trades_v1-*"] = total
        except Exception:
            indices["trades_v1-*"] = None
    except Exception:
        pass
    ctx = {"request": request, "health": health, "indices": indices}
    return templates.TemplateResponse("dashboard.html", ctx)


# ------------------ API Keys ------------------


@router.get("/keys", response_class=HTMLResponse)
async def list_keys(request: Request) -> HTMLResponse:
    require_admin(request)
    store = request.app.state.api_key_store
    with store._get_conn() as conn:  # type: ignore[attr-defined]
        cur = conn.execute("SELECT key, plan_type, status, created_at, COALESCE(expires_at,'') FROM api_keys ORDER BY created_at DESC")
        rows = cur.fetchall()
    keys = [
        {"key": r[0], "plan_type": r[1], "status": r[2], "created_at": r[3], "expires_at": r[4] or None}
        for r in rows
    ]
    return templates.TemplateResponse("keys.html", {"request": request, "keys": keys})


@router.get("/keys/new", response_class=HTMLResponse)
async def new_key_page(request: Request) -> HTMLResponse:
    require_admin(request)
    return templates.TemplateResponse("key_new.html", {"request": request, "error": None})


@router.post("/keys/new")
async def create_key(
    request: Request,
    key: Optional[str] = Form(default=None),
    plan_type: str = Form(default="monthly"),
    expires_at: Optional[str] = Form(default=None),
) -> Response:
    require_admin(request)
    store = request.app.state.api_key_store
    new_key = key.strip() if key else secrets.token_urlsafe(24)
    try:
        store.upsert_key(new_key, plan_type=plan_type, status="active", expires_at=expires_at or None)
    except Exception as e:
        return templates.TemplateResponse(
            "key_new.html", {"request": request, "error": f"Failed to create key: {e}"}, status_code=status.HTTP_400_BAD_REQUEST
        )
    return RedirectResponse(url="/admin/keys", status_code=status.HTTP_302_FOUND)


# ------------------ Data Browsers ------------------


@router.get("/data/markets", response_class=HTMLResponse)
async def data_markets(
    request: Request,
    q: Optional[str] = None,
    category: Optional[str] = None,
    status_: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
) -> HTMLResponse:
    require_admin(request)
    client: OpenSearch = get_client()
    must = []
    if q:
        must.append({"multi_match": {"query": q, "fields": ["title^2", "category", "description"]}})
    if category:
        must.append({"term": {"category": category}})
    if status_:
        must.append({"term": {"status": status_}})
    body = {
        "query": {"bool": {"must": must}} if must else {"match_all": {}},
        "from": (page - 1) * limit,
        "size": limit,
        "sort": [{"created_at": {"order": "desc"}}],
        "track_total_hits": True,
    }
    res = client.search(index="markets_v1", body=body)
    hits = [h["_source"] | {"_id": h["_id"]} for h in res["hits"]["hits"]]
    total = res.get("hits", {}).get("total", {}).get("value", 0)
    return templates.TemplateResponse(
        "data_markets.html",
        {
            "request": request,
            "rows": hits,
            "page": page,
            "limit": limit,
            "total": total,
            "q": q or "",
            "category": category or "",
            "status_": status_ or "",
        },
    )


@router.get("/data/trades", response_class=HTMLResponse)
async def data_trades(
    request: Request,
    market_id: str,
    from_: Optional[str] = None,
    to: Optional[str] = None,
    sort: str = "ts:desc",
    page: int = 1,
    limit: int = 100,
) -> HTMLResponse:
    require_admin(request)
    client: OpenSearch = get_client()
    must = [{"term": {"market_id": market_id}}]
    if from_ or to:
        rng: dict = {}
        if from_:
            rng["gte"] = from_
        if to:
            rng["lte"] = to
        must.append({"range": {"ts": rng}})
    order = "desc" if sort.endswith(":desc") else "asc"
    body = {
        "query": {"bool": {"must": must}},
        "from": (page - 1) * limit,
        "size": limit,
        "sort": [{"ts": {"order": order}}],
        "track_total_hits": True,
    }
    res = client.search(index="trades_v1-*", body=body)
    hits = [h["_source"] | {"_id": h["_id"], "_index": h["_index"]} for h in res["hits"]["hits"]]
    total = res.get("hits", {}).get("total", {}).get("value", 0)
    return templates.TemplateResponse(
        "data_trades.html",
        {
            "request": request,
            "rows": hits,
            "limit": limit,
            "market_id": market_id,
            "from_": from_ or "",
            "to": to or "",
            "sort": sort,
            "page": page,
            "total": total,
        },
    )


@router.get("/data/candles", response_class=HTMLResponse)
async def data_candles(
    request: Request,
    market_id: str,
    interval: str,
    from_: str,
    to: str,
    page: int = 1,
    limit: int = 200,
) -> HTMLResponse:
    require_admin(request)
    client: OpenSearch = get_client()
    body = {
        "query": {
            "bool": {
                "must": [
                    {"term": {"market_id": market_id}},
                    {"term": {"interval": interval}},
                    {"range": {"open_time": {"gte": from_, "lte": to}}},
                ]
            }
        },
        "from": (page - 1) * limit,
        "size": limit,
        "sort": [{"open_time": {"order": "asc"}}],
        "track_total_hits": True,
    }
    res = client.search(index="candles_v1", body=body)
    hits = [h["_source"] | {"_id": h["_id"]} for h in res["hits"]["hits"]]
    total = res.get("hits", {}).get("total", {}).get("value", 0)
    return templates.TemplateResponse(
        "data_candles.html",
        {
            "request": request,
            "rows": hits,
            "market_id": market_id,
            "interval": interval,
            "from_": from_,
            "to": to,
            "page": page,
            "limit": limit,
            "total": total,
        },
    )


@router.get("/data/orderbook", response_class=HTMLResponse)
async def data_orderbook(
    request: Request,
    market_id: str,
    side: str = "bid",
    at: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
) -> HTMLResponse:
    require_admin(request)
    client: OpenSearch = get_client()
    must = [{"term": {"market_id": market_id}}, {"term": {"side": side}}]
    if at:
        must.append({"range": {"ts": {"lte": at}}})
        body = {"query": {"bool": {"must": must}}, "size": 1, "sort": [{"ts": {"order": "desc"}}]}
        res = client.search(index="orderbook_snapshots_v1", body=body)
        doc = res["hits"]["hits"][0]["_source"] if res["hits"]["hits"] else {}
        return templates.TemplateResponse("data_orderbook.html", {"request": request, "doc": doc, "rows": []})
    body = {
        "query": {"bool": {"must": must}},
        "from": (page - 1) * limit,
        "size": limit,
        "sort": [{"ts": {"order": "desc"}}],
        "track_total_hits": True,
    }
    res = client.search(index="orderbook_snapshots_v1", body=body)
    rows = [h["_source"] | {"_id": h["_id"]} for h in res["hits"]["hits"]]
    total = res.get("hits", {}).get("total", {}).get("value", 0)
    return templates.TemplateResponse(
        "data_orderbook.html",
        {"request": request, "rows": rows, "market_id": market_id, "side": side, "page": page, "limit": limit, "total": total},
    )


# ------------------ Ingestion Status ------------------


@router.get("/ingestion", response_class=HTMLResponse)
async def ingestion_status(request: Request) -> HTMLResponse:
    require_admin(request)
    heartbeat_path = os.getenv("ADMIN_HEARTBEAT_PATH", "/data/status/ingester.json")
    checkpoint_paths = {
        "trades": os.getenv("TRADES_CHECKPOINT_PATH", "/data/trades_checkpoint.json"),
        "candles": os.getenv("CANDLES_CHECKPOINT_DIR", "/data/candles_checkpoints"),
        "orderbook": os.getenv("ORDERBOOK_CHECKPOINT_PATH", "/data/orderbook_checkpoint.json"),
    }
    import json, glob
    status_data = {"heartbeat": None, "checkpoints": {}}
    try:
        with open(heartbeat_path, "r", encoding="utf-8") as f:
            status_data["heartbeat"] = json.load(f)
    except Exception:
        status_data["heartbeat"] = None
    # trades
    try:
        with open(checkpoint_paths["trades"], "r", encoding="utf-8") as f:
            status_data["checkpoints"]["trades"] = json.load(f)
    except Exception:
        status_data["checkpoints"]["trades"] = None
    # candles (collect per-interval files if directory)
    candles_dir = checkpoint_paths["candles"]
    candles_data = []
    try:
        for p in glob.glob(os.path.join(candles_dir, "*.json")):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    candles_data.append({"file": os.path.basename(p), "data": json.load(f)})
            except Exception:
                pass
    except Exception:
        pass
    status_data["checkpoints"]["candles"] = candles_data
    # orderbook
    try:
        with open(checkpoint_paths["orderbook"], "r", encoding="utf-8") as f:
            status_data["checkpoints"]["orderbook"] = json.load(f)
    except Exception:
        status_data["checkpoints"]["orderbook"] = None

    return templates.TemplateResponse("ingestion.html", {"request": request, "status": status_data})


# ------------------ Metrics ------------------


@router.get("/metrics", response_class=HTMLResponse)
async def metrics_page(request: Request) -> HTMLResponse:
    require_admin(request)
    store: ApiKeyStore = request.app.state.api_key_store
    rows = store.metrics_last_24h()
    metrics = [
        {"api_key": r[0], "total": r[1], "s2xx": r[2], "s4xx": r[3], "s5xx": r[4]}
        for r in rows
    ]
    return templates.TemplateResponse("metrics.html", {"request": request, "metrics": metrics})


@router.post("/keys/{api_key}/revoke")
async def revoke_key(request: Request, api_key: str) -> Response:
    require_admin(request)
    store = request.app.state.api_key_store
    try:
        store.upsert_key(api_key, status="revoked")
    except Exception:
        pass
    return RedirectResponse(url="/admin/keys", status_code=status.HTTP_302_FOUND)


