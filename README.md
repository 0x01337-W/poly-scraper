Polymarket Data SaaS (Self-hosted)

Overview
- Self-hosted read-only data API for Polymarket, with 90-day retention and API-key auth. Traders and market makers can query markets, trades, candles, and orderbook snapshots.

Quickstart
- Copy `env.example` to `.env` and adjust as needed.
  - Set a strong `OPENSEARCH_INITIAL_ADMIN_PASSWORD`.
- Start OpenSearch only (optional for first-time setup):
  - `docker compose -f database/opensearch/docker-compose.yml up -d`
- Initialize OpenSearch templates and ILM:
  - `bash database/opensearch/scripts/setup.sh`
- Start full stack:
  - `docker compose up -d`
- (Optional) Enable trades ingester:
  - Set `ENABLE_TRADES_INGESTER=true` in `.env`
- Bootstrap an API key by setting `API_BOOTSTRAP_KEY` in `.env` (or use the planned admin CLI), then call API endpoints with header `X-API-Key`.

Key docs
- Architecture: `docs/ARCHITECTURE.md`
- API reference: `docs/API.md`
- Ingestion: `docs/INGESTION.md`
- Database (OpenSearch): `docs/DB.md`
- Operations runbook: `docs/OPERATIONS.md`
- Security: `docs/SECURITY.md`
- Testing: `docs/TESTING.md`
- Optimization: `docs/OPTIMIZATION.md`
- Roadmap: `docs/ROADMAP.md`

Components
- ingester/: collectors for Polymarket APIs (backfill + polling)
- database/: OpenSearch compose, templates, and scripts
- api/: FastAPI app with API-key auth
- frontend/: optional portal (later)

