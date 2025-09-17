## Polymarket Data SaaS – Current Features

### Overview
Self-hosted, read-only data platform for Polymarket. Continuously ingests public data, stores it in OpenSearch with 90‑day retention, and serves a REST API secured by API keys. Designed for traders and market makers to query markets, trades, candles, and order book snapshots.

### What is ingested
- Markets (Gamma API)
  - Periodic polling of market metadata (title, status, category, created/close times, etc.).
  - Deterministic IDs and idempotent upserts into `markets_v1`.

- Trades (CLOB REST/Data-API)
  - Backfill with pagination and time-windowing; resumable via checkpoints.
  - Incremental polling from the last checkpoint.
  - Normalization to a stable schema (ISO8601 `ts`, `market_id`, numeric `price`/`size`, lowercase `side`).
  - Optional fields captured when present: `market_order_id`, `match_time`, `bucket_index`, `status`.
  - Deterministic IDs and idempotent upserts into daily indices `trades_v1-YYYY.MM.DD`.

- Candles (derived)
  - Worker computes OHLCV for configurable intervals (`1m,5m,1h`) from raw trades.
  - Per-interval checkpoints; idempotent upserts keyed by `{market_id, interval, open_time}` into `candles_v1`.

- Order book snapshots (forward-only)
  - Worker captures periodic top‑N depth per side (`bid`, `ask`) for configured markets.
  - Stored as snapshots in `orderbook_snapshots_v1` keyed by `{market_id, ts, side}`.

### Where and how data is stored (OpenSearch)
- Indices and mappings
  - `markets_v1`: market metadata.
  - `trades_v1-*`: time-partitioned trades (daily), includes `trade_id`, `market_id`, `ts`, `price`, `size`, `side`, optional CLOB fields.
  - `candles_v1`: derived OHLCV with `market_id`, `interval`, `open_time`, `open/high/low/close`, `volume`.
  - `orderbook_snapshots_v1`: `market_id`, `ts`, `side`, `levels[nested(price,size,level)]`.
- Retention & lifecycle
  - ILM/ISM policy `90d_delete`: hot-only, deletes indices after 90 days.
- Write strategy
  - Deterministic document IDs; bulk operations; idempotent upserts (`_op_type: index`).
- Checkpoints
  - Trades: JSON file at `TRADES_CHECKPOINT_PATH`.
  - Candles: per-interval JSON files under `CANDLES_CHECKPOINT_DIR`.
  - Orderbook: JSON file at `ORDERBOOK_CHECKPOINT_PATH`.

### Backend API (FastAPI)
- Authentication
  - Header `X-API-Key` required for all endpoints (except `/health`).
  - Keys stored in SQLite (`/data/keys.db` by default) with status and optional expiry.
  - Admin CLI available to upsert/list/revoke keys.

- Rate limiting
  - In-memory token bucket per API key.
  - Configurable short-term RPS (`API_RATE_RPS`) and daily cap (`API_DAILY_CAP`).

- Endpoints
  - GET `/health`
    - Returns API health.

  - GET `/v1/markets`
    - Filters: `q`, `category`, `status`.
    - Pagination: `page`, `limit` (offset/limit).
    - Sort: `created_at desc`.
    - Response: list of market documents.

  - GET `/v1/markets/{market_id}`
    - Fetches a single market by ID. Falls back to term lookup on `market_id` field when necessary.

  - GET `/v1/trades`
    - Required: `market_id`.
    - Optional window: `from`, `to` (ISO8601).
    - Sorting: `sort=ts:asc|desc` (default `desc`).
    - Cursor pagination: `cursor` (opaque) + `limit` (default 100, max 1000). Returns `next_cursor`.
    - Reads from `trades_v1-*`.

  - GET `/v1/candles`
    - Required: `market_id`, `interval in {1m,5m,1h}`, `from`, `to`.
    - Returns aligned OHLCV bars from `candles_v1`.

  - GET `/v1/orderbook`
    - Required: `market_id`.
    - Optional: `side in {bid,ask}` (default `bid`), `at` (timestamp for historical lookup at/<= time).
    - Returns latest or time-aligned snapshot from `orderbook_snapshots_v1`.

- Example usage
```
curl -H "X-API-Key: $KEY" "http://localhost:8080/v1/markets?status=open&limit=10"
curl -H "X-API-Key: $KEY" "http://localhost:8080/v1/trades?market_id=abc&from=2025-09-16T00:00:00Z&limit=100"
curl -H "X-API-Key: $KEY" "http://localhost:8080/v1/candles?market_id=abc&interval=1m&from=2025-09-17T10:00:00Z&to=2025-09-17T11:00:00Z"
curl -H "X-API-Key: $KEY" "http://localhost:8080/v1/orderbook?market_id=abc&side=bid"
```

### Admin CLI (API keys)
- Location: `api/src/auth/cli.py`
- Commands
  - `upsert <key> [--plan monthly|weekly] [--status active|revoked] [--expires-at ISO8601]`
  - `list`
  - `revoke <key>`

### Deployment and operations
- Docker Compose
  - Services: `opensearch`, `opensearch-dashboards`, `polyscraper-api`, `polyscraper-ingester`.
  - OpenSearch healthchecks and TLS enabled in-container.
- Setup
  - Copy `env.example` to `.env` and configure values.
  - Start OpenSearch: `docker compose -f database/opensearch/docker-compose.yml up -d`.
  - Initialize templates/ILM: `bash database/opensearch/scripts/setup.sh`.
  - Start full stack: `docker compose up -d`.
- Windows notes
  - Use Git Bash/WSL for the setup script (`curl` + `jq` required).

### Configuration (key variables)
- OpenSearch: `OPENSEARCH_URL` (use `https://opensearch:9200` in Docker), `OPENSEARCH_USER`, `OPENSEARCH_PASSWORD`.
- API server: `API_BIND_HOST`, `API_BIND_PORT`, `API_KEY_DB_PATH`, `API_RATE_RPS`, `API_DAILY_CAP`.
- Markets: `POLYMARKET_GAMMA_BASE`.
- Trades: `POLYMARKET_TRADES_BASE`, `TRADES_PAGE_SIZE`, `TRADES_BACKFILL_DAYS`, `TRADES_BACKFILL_WINDOW_MINUTES`, `TRADES_CHECKPOINT_PATH`.
- Candles: `ENABLE_CANDLES_WORKER`, `CANDLES_INTERVALS`, `CANDLES_LOOKBACK_MINUTES`, `CANDLES_TRADES_FETCH_LIMIT`, `CANDLES_POLL_MS`, `CANDLES_CHECKPOINT_DIR`.
- Orderbook: `ENABLE_ORDERBOOK_WORKER`, `ORDERBOOK_MARKET_IDS`, `ORDERBOOK_DEPTH`, `ORDERBOOK_POLL_MS`, `ORDERBOOK_CHECKPOINT_PATH`, `POLYMARKET_CLOB_BASE`.

### Current limitations and notes
- WebSocket deltas for order book are not yet ingested (forward-only snapshots for configured markets).
- API currently uses FastAPI default error structure; a consistent error envelope and Pydantic response schemas are planned.
- Rate limiting is in-memory (single-node); suitable for the intended single-host deployment.
- Ensure `OPENSEARCH_URL` scheme matches runtime (TLS is enabled in the provided Docker setup).


