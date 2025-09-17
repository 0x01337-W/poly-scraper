import os
from fastapi import FastAPI, Request
import logging
from starlette.middleware.sessions import SessionMiddleware

from src.routers.health import router as health_router
from src.routers.markets import router as markets_router
from src.routers.trades import router as trades_router
from src.routers.candles import router as candles_router
from src.routers.orderbook import router as orderbook_router
from src.auth.key_store import ApiKeyStore, bootstrap_default_key


def create_app() -> FastAPI:
    debug = os.getenv("API_DEBUG", "false").lower() == "true"
    openapi_url = "/openapi.json" if debug else None
    docs_url = "/docs" if debug else None
    redoc_url = "/redoc" if debug else None
    tags_metadata = [
        {"name": "health", "description": "Service health and readiness."},
        {"name": "markets", "description": "Market metadata search and lookup."},
        {"name": "trades", "description": "Raw trades with time windows and pagination."},
        {"name": "candles", "description": "Derived OHLCV by interval."},
        {"name": "orderbook", "description": "Order book snapshot access."},
    ]
    application = FastAPI(
        title="Polymarket Data API",
        version="0.1.0",
        debug=debug,
        openapi_url=openapi_url,
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_tags=tags_metadata,
        description="Self-hosted, read-only Polymarket data API."
    )

    # Routers
    application.include_router(health_router)
    application.include_router(markets_router)
    application.include_router(trades_router)
    application.include_router(candles_router)
    application.include_router(orderbook_router)

    # Optional Admin Dashboard
    if os.getenv("ADMIN_ENABLED", "false").lower() == "true":
        secret = os.getenv("ADMIN_SESSION_SECRET", "")
        if secret:
            application.add_middleware(SessionMiddleware, secret_key=secret)
        try:
            from src.admin.router import router as admin_router  # type: ignore

            application.include_router(admin_router)
        except Exception:
            # If admin router import fails, continue without admin
            pass

    @application.on_event("startup")
    def _startup() -> None:
        db_path = os.getenv("API_KEY_DB_PATH", "/data/keys.db")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        store = ApiKeyStore(db_path)
        application.state.api_key_store = store
        bootstrap_default_key(store)

    @application.middleware("http")
    async def _metrics_mw(request: Request, call_next):
        response = await call_next(request)
        try:
            # Skip admin routes from metrics
            if not request.url.path.startswith("/admin"):
                key = getattr(request.state, "api_key", None)
                application.state.api_key_store.log_request(key, request.method, request.url.path, response.status_code)
        except Exception:
            pass
        return response

    # Configure logging level
    level = os.getenv("LOG_LEVEL", "info").lower()
    level_map = {"debug": logging.DEBUG, "info": logging.INFO, "warning": logging.WARNING, "error": logging.ERROR}
    logging.getLogger().setLevel(level_map.get(level, logging.INFO))

    return application


app = create_app()

