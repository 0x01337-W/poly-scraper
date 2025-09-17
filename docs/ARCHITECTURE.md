## Architecture

### Executive summary
Self-hosted SaaS-style data platform for Polymarket. It ingests public data (REST, optional WS), normalizes and stores it in OpenSearch with 90-day retention, and serves a typed REST API secured by API keys. Optional frontend can provide docs and admin key management.

### System diagram (logical)
```
[Polymarket Public APIs]
  |\
  |  REST backfill + polling (Gamma, Data-API, CLOB)
  |   \--> [Ingestion Workers (Python)] --> [OpenSearch Cluster]
  |                                                  ^
  |  (optional) WebSocket MARKET consumer -----------|
  |
[Backend API (FastAPI)] --> Auth (API Key) --> Query OpenSearch --> JSON
  |
  └--> (optional) Frontend for docs and admin key management
```

### Components
- Ingestion (Python):
  - `markets` worker polls Gamma markets endpoint and upserts `markets_v1`.
  - `trades` worker polls Data-API, normalizes fields, and writes daily `trades_v1-YYYY.MM.DD` indices.
  - Future: candles derivation and orderbook snapshots.
- Storage (OpenSearch):
  - Indices: `markets_v1`, `trades_v1-*`, `candles_v1`, `orderbook_snapshots_v1`.
  - ILM/ISM: hot-only, delete at 90 days (`90d_delete`).
- API (FastAPI):
  - Routes: `/health`, `/v1/markets`, `/v1/trades`, `/v1/candles`, `/v1/orderbook`.
  - Header auth via `X-API-Key`, keys stored in SQLite.
- Orchestration: Docker Compose for OpenSearch, API, ingester (frontend optional later).

### Data flow
1) Ingestion workers call upstream APIs and receive JSON.
2) Workers normalize payloads and bulk write into OpenSearch with deterministic IDs.
3) API composes queries over OpenSearch and returns JSON responses.

### Environments
- Local single-node via Docker Compose for OpenSearch and services.
- Production single host (initial) with the same compose stack.

### Configuration
Environment variables (see `env.example`):
- OpenSearch connection: `OPENSEARCH_URL`, `OPENSEARCH_USER`, `OPENSEARCH_PASSWORD`.
- API: `API_BIND_HOST`, `API_BIND_PORT`, `API_RATE_RPS`, `API_DAILY_CAP`, SQLite path.
- Ingestion: polling intervals, feature flags, Polymarket base URLs.

Important: OpenSearch in this stack listens on HTTPS by default. Use `OPENSEARCH_URL=https://opensearch:9200` when running in Docker. The default client config disables certificate verification in-container.

### Reliability and idempotency
- Writes use deterministic document IDs to avoid duplicates on retries.
- Backfill and polling should checkpoint last-seen timestamps per dataset to resume safely.
- ILM ensures bounded storage via 90-day deletion.

### Security
- API key header `X-API-Key` validated against SQLite store; keys can be bootstrapped via env.
- Optional per-key rate limiting (token bucket) to be added for abuse control.

### Scaling path
- Increase OpenSearch heap and storage; split to multiple shards/indices if needed.
- Add ingestion worker concurrency and per-source rate limiting.
- Introduce cursor pagination for heavy endpoints.


