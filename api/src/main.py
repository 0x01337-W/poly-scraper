import os
from fastapi import FastAPI

from src.routers.health import router as health_router
from src.routers.markets import router as markets_router
from src.routers.trades import router as trades_router
from src.routers.candles import router as candles_router
from src.routers.orderbook import router as orderbook_router
from src.auth.key_store import ApiKeyStore, bootstrap_default_key


def create_app() -> FastAPI:
    application = FastAPI(title="Polymarket Data API", version="0.1.0")

    # Routers
    application.include_router(health_router)
    application.include_router(markets_router)
    application.include_router(trades_router)
    application.include_router(candles_router)
    application.include_router(orderbook_router)

    @application.on_event("startup")
    def _startup() -> None:
        db_path = os.getenv("API_KEY_DB_PATH", "/data/keys.db")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        store = ApiKeyStore(db_path)
        application.state.api_key_store = store
        bootstrap_default_key(store)

    return application


app = create_app()

