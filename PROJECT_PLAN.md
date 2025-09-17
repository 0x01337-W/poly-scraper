## Polymarket Data SaaS – Architecture and Implementation Plan

### Executive summary
Build a self-hosted, read-only SaaS-style data platform for Polymarket that continuously ingests public data, indexes it for fast querying, and exposes a clean REST/JSON API secured by API keys. Optional: a small frontend portal for docs and key management. All components live in a single monorepo with clear separation: `ingester/`, `database/`, `api/`, `frontend/`.

### Progress tracker (high-level delivery phases)
- **Phase 0 – Monorepo scaffold**: 0% 
- **Phase 1 – Ingestion (REST backfill + polling)**: 0%
- **Phase 2 – OpenSearch indices + ILM (90-day retention)**: 0%
- **Phase 3 – REST API (FastAPI) + API key auth**: 0%
- **Phase 4 – Optional frontend portal**: 0%
- **Phase 5 – Optional WebSocket MARKET stream**: 0%

Session log notes will be appended under each phase during implementation.

---

## 1) Goals, constraints, and non-goals

### Goals
- Provide comprehensive, queryable Polymarket data for users who want to optimize or automate trading.
- Read-only analytics/data access over REST/JSON.
- Self-hosted on a dedicated machine; no external managed services.
- Best-effort freshness and availability; no strict SLAs.
- Retain raw/derived data for 90 days.
- Optional buyer-facing portal (docs + API key management). Pricing: weekly/monthly access.

### Non-goals (for this plan)
- Trading/execution features.
- Authenticated Polymarket user channels (no USER WebSocket usage).
- Monitoring/alerting/backup/DR; can be added later.

### Data sources in scope
- Polymarket public endpoints:
  - Gamma API
  - Data-API
  - CLOB REST
  - WebSocket MARKET channel (optional, post-MVP)

---

## 2) High-level architecture

```
[Polymarket Public APIs]
  |\
  | REST backfill + polling (Gamma/Data-API/CLOB)
  |  \
  |   \--> [Ingestion Workers (Python)] --> [Staging Queues (in-process)] --> [OpenSearch Cluster]
  |                                                                                 ^
  |  Optional: WebSocket MARKET consumer -------------------------------------------|
  |
 [Backend API (FastAPI)]  --> Auth (API Key) --> Query OpenSearch --> JSON responses
  |
  └--> Optional Frontend (Next.js) for docs and key management
```

Key properties:
- Stateless workers; idempotent upserts into OpenSearch.
- Time-partitioned indices with ILM to enforce 90-day retention.
- API server performs query composition, validation, rate limiting, and pagination.
- Simple API key store (SQLite) for local self-hosting; header-based auth.

---

## 3) Monorepo structure

```
AA_LLC_PolyScraper/
  ingester/
    src/
      collectors/              # Gamma, Data-API, CLOB REST pollers
      transforms/              # JSON normalization, enrichment (candles, metrics)
      loaders/                 # OpenSearch bulk upserts
      common/                  # config, logging, http client, retry, rate-limit
    tests/
    pyproject.toml             # Python project config
    README.md
  database/
    opensearch/
      docker-compose.yml       # OpenSearch + Dashboards (optional)
      templates/               # index templates & ILM policies
      scripts/                 # setup scripts (create templates, ilm, users)
    README.md
  api/
    src/
      main.py                  # FastAPI app entry
      auth/                    # API key middleware, rate limiter
      routers/                 # markets, trades, orderbook, candles
      clients/                 # OpenSearch client wrapper
      schemas/                 # Pydantic models for requests/responses
    tests/
    pyproject.toml
    README.md
  frontend/ (optional)
    next.config.js
    src/
      pages/                   # Docs, key management, plan selection (stub)
      components/
    package.json
    README.md
  .env.example
  README.md                    # root overview and quickstart
```

Rationale:
- Clean separation of concerns per component while keeping developer ergonomics of a monorepo.

---

## 4) Ingestion design

### 4.1 Datasets (initial MVP)
- Markets metadata: market id, title, description, status, category, created/close times, outcomes, fees, etc.
- Trades: executed trades with price, size, direction, timestamps.
- Order book: periodic snapshots (top N levels) and optional deltas if/when WebSocket is enabled.
- Candles: derived OHLCV (e.g., 1m, 5m, 1h) from trades.

### 4.2 Backfill strategy
- Use Data-API and/or Gamma endpoints for historical markets and trades when available.
- If historical order book not available: start snapshots from go-live, then maintain forward.
- Backfill runs once on first startup; checkpointed progress persisted in OpenSearch (or local state file) to resume safely.

### 4.3 Live updates (polling first)
- Poll REST endpoints at conservative intervals respecting documented/observed rate limits.
- Exponential backoff on HTTP errors; jitter to avoid thundering herd.
- Idempotent writes using natural keys:
  - Markets: `market_id` as document id.
  - Trades: `trade_id` or `(market_id, tx_hash, ts)` composite for dedupe.
  - Order book snapshots: `(market_id, timestamp, side)`.

### 4.4 Optional WebSocket MARKET consumer (post-MVP)
- Subscribe to MARKET channels to capture near-real-time deltas.
- Rebuild book state with periodic authoritative snapshots for accuracy.
- Persist deltas compacted into per-interval aggregates to control index growth.

### 4.5 Transform and load
- Normalize source payloads to stable internal schemas.
- Compute candles via streaming aggregations over trades (windowed by interval).
- Bulk index into OpenSearch with backpressure if cluster is overloaded.

### 4.6 Configuration
- Single `.env` controls keys and polling cadence, e.g.:
  - `POLL_INTERVAL_TRADES_MS`, `POLL_INTERVAL_MARKETS_MS`
  - `OPENSEARCH_URL`, `OPENSEARCH_USER`, `OPENSEARCH_PASSWORD`
  - `CANDLES_INTERVALS=1m,5m,1h`

---

## 5) Database layer (OpenSearch)

### 5.1 Choice
- OpenSearch (Elasticsearch-compatible) for full-text, structured search, aggregations, and time-series indexing. Fully self-hosted via Docker Compose.

### 5.2 Indices and mappings (v1)
- `markets_v1`
  - `market_id (keyword)` primary id
  - `title (text, keyword subfield)`, `category (keyword)`, `status (keyword)`
  - `created_at (date)`, `close_time (date)`
  - `outcomes (nested)` with `name (keyword)`, `probability (float)`
- `trades_v1` (time-partitioned)
  - `trade_id (keyword)`, `market_id (keyword)`, `ts (date)`
  - `price (float)`, `size (float)`, `side (keyword)`
  - index pattern: `trades_v1-YYYY.MM.DD`
- `orderbook_snapshots_v1`
  - `market_id (keyword)`, `ts (date)`, `side (keyword)`
  - `levels (nested)` with `price (float)`, `size (float)`, `level (integer)`
- `candles_v1`
  - `market_id (keyword)`, `interval (keyword)`, `open_time (date)`
  - `open (float)`, `high (float)`, `low (float)`, `close (float)`, `volume (float)`

Note: exact field names will be finalized from live payloads.

### 5.3 ILM and retention
- Hot-only policy with delete at 90 days.
- Rollover on size/time for high-throughput indices (e.g., trades):
  - Policy: `max_primary_shard_size: 50gb` OR `max_age: 7d` (whichever first), then delete at 90d.

### 5.4 Query patterns (for API)
- Markets: search/filter by text, category, status, date ranges.
- Trades: filter by `market_id`, time window; aggregate volumes and VWAP.
- Order book: get latest snapshot or snapshot at/nearest to timestamp.
- Candles: query by `market_id` + `interval` within range; return evenly spaced buckets.

---

## 6) Backend API (SaaS layer)

### 6.1 Tech
- Python + FastAPI for speed of development and great typing (Pydantic), with Uvicorn.

### 6.2 Authentication
- Header: `X-API-Key: <key>`.
- Keys stored locally in SQLite (`api/keys.db`) with fields: `key`, `plan_type (weekly|monthly)`, `status (active|revoked)`, `created_at`, `expires_at` (nullable).
- Simple admin CLI to create/revoke keys.

### 6.3 Rate limiting (optional, single-node)
- Token bucket in-memory per API key (configurable RPS and daily cap). For a single dedicated server, this is sufficient.

### 6.4 Endpoints (initial)
- `GET /v1/markets`
  - Params: `q`, `category`, `status`, `from`, `to`, `page`, `limit`
  - Returns: list of markets with pagination.
- `GET /v1/markets/{market_id}`
  - Returns: detailed market metadata.
- `GET /v1/trades`
  - Params: `market_id`, `from`, `to`, `sort=ts:asc|desc`, `page`, `limit`.
  - Returns: trades and basic aggregates (volume, vwap if requested).
- `GET /v1/orderbook`
  - Params: `market_id`, `at` (timestamp optional for historical), `side=bid|ask`.
  - Returns: latest or time-aligned snapshot.
- `GET /v1/candles`
  - Params: `market_id`, `interval in [1m,5m,1h]`, `from`, `to`.
  - Returns: OHLCV bars aligned on interval boundaries.

### 6.5 Pagination & response limits
- `limit` default 100, max 1000. Use cursor-based pagination for trades endpoints.

### 6.6 Validation and errors
- Pydantic models; consistent error envelope `{error: {code, message}}`.

---

## 7) Optional frontend

### 7.1 Scope
- Developer portal (self-hosted): documentation, API key viewing/rotation (admin-only for now), plan info (weekly/monthly).
- No payment processing in scope (can be integrated later if desired).

### 7.2 Tech
- Next.js + TypeScript, MUI or Tailwind. Minimal pages: Home, Docs, Admin (keys).

---

## 8) Local deployment (Docker Compose)

### 8.1 Services
- `opensearch`: OpenSearch node (single-node dev profile) + volumes.
- `opensearch-dashboards`: optional UI for inspection.
- `api`: FastAPI app container.
- `ingester`: Python worker container(s).
- `frontend`: optional Next.js app container.

### 8.2 Environment (.env.example)
- `OPENSEARCH_URL=http://opensearch:9200`
- `OPENSEARCH_USER=admin`
- `OPENSEARCH_PASSWORD=admin`
- `API_BIND_HOST=0.0.0.0`
- `API_BIND_PORT=8080`
- `API_RATE_RPS=10`
- `API_DAILY_CAP=100000`
- `POLL_INTERVAL_TRADES_MS=3000`
- `POLL_INTERVAL_MARKETS_MS=10000`

### 8.3 Start-up order
1) Bring up OpenSearch and Dashboards.
2) Run database setup scripts (templates, ILM).
3) Start API and ingester.
4) (Optional) Start frontend.

---

## 9) Data validation and testing

### 9.1 Ingestion tests
- Unit tests for parsers/transforms against fixture payloads.
- Idempotency tests: re-run batches and verify no duplicates.

### 9.2 API tests
- Contract tests for each endpoint (status codes, schema, pagination, filters).
- Golden tests for candles and aggregates.

### 9.3 Sanity checks
- Periodic counts: trades per market per day; alert locally in logs on anomalies.

---

## 10) Roadmap and acceptance criteria

### Phase 0 – Monorepo scaffold
- Create root repo and folders; add base READMEs and .env.example.
- Acceptance: `docker compose` can boot OpenSearch; API runs and returns 200 on `/health`.

### Phase 1 – Ingestion (REST backfill + polling)
- Implement collectors for markets and trades; persist to OpenSearch.
- Acceptance: Backfill completes on a sample set; live polling updates counts.

### Phase 2 – OpenSearch indices + ILM
- Apply index templates and ILM; time-partitioned indices working.
- Acceptance: Documents land in correct indices; lifecycle deletes old data at 90d in test.

### Phase 3 – Backend API + API keys
- FastAPI endpoints implemented; header auth with SQLite key store.
- Acceptance: All endpoints return expected schemas; rate limiting configurable.

### Phase 4 – Optional frontend
- Minimal portal with docs and admin key management page.
- Acceptance: Admin can create/revoke API keys; docs render query examples.

### Phase 5 – Optional WebSocket MARKET consumer
- Add WebSocket deltas, reconcile with snapshots.
- Acceptance: Book updates reflect WS events; throughput stable under load test.

---

## 11) Risks and mitigations
- API changes or undocumented limits: implement adaptive backoff and feature flags per collector.
- Historical completeness: document which datasets are fully backfilled vs forward-only.
- Index growth from order books: use top-N snapshots and compact deltas; tune ILM and intervals.
- Single-node limits: acceptable per dedicated server constraint; document scaling path (shards, nodes) for future.

---

## 12) Quickstart (developer workflow)

1) Copy `.env.example` to `.env` and adjust settings.
2) Start OpenSearch services:
   - `docker compose -f database/opensearch/docker-compose.yml up -d`
3) Run setup scripts to create templates/ILM.
4) Start API and ingester containers with the root `docker-compose.yml` (to be added in Phase 0).
5) Generate an API key via the API admin CLI; call `/v1/*` endpoints with `X-API-Key`.

---

## 13) Appendix A – Example API shapes (illustrative)

Markets list response (excerpt):
```json
{
  "data": [
    {
      "market_id": "123",
      "title": "Will X happen by Y?",
      "category": "Politics",
      "status": "open",
      "created_at": "2025-08-01T12:00:00Z",
      "close_time": "2025-11-05T00:00:00Z"
    }
  ],
  "page": 1,
  "limit": 100,
  "next_cursor": null
}
```

Candles response (excerpt):
```json
{
  "market_id": "123",
  "interval": "1m",
  "candles": [
    { "open_time": "2025-09-17T10:00:00Z", "open": 0.45, "high": 0.46, "low": 0.44, "close": 0.455, "volume": 1234.5 }
  ]
}
```

---

This plan reflects the requested constraints: read-only, best-effort freshness/availability, public data only, 90-day retention, self-hosted, monorepo with clear separation, and optional frontend.


