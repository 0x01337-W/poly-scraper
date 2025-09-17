Polymarket Data SaaS (Self-hosted)

Quickstart
- Copy `env.example` to `.env` and adjust as needed.
  - Set a strong `OPENSEARCH_INITIAL_ADMIN_PASSWORD` (required by OpenSearch 2.12+).
- Start OpenSearch and services with Docker Compose:
  - `docker compose up -d`
- Initialize OpenSearch templates and ILM:
  - `bash database/opensearch/scripts/setup.sh`
- Generate an API key (placeholder CLI to be added) and call API endpoints with header `X-API-Key`.

Components
- ingester/: collectors for Polymarket APIs (backfill + polling)
- database/: OpenSearch compose, templates, and scripts
- api/: FastAPI app with API-key auth
- frontend/: optional portal (later)

