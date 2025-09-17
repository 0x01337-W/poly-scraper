## Security

### Authentication
- Header `X-API-Key` required for all non-health endpoints.
- Keys stored in SQLite (`api/keys.db` by default via volume `api-data`).
- Bootstrap: set `API_BOOTSTRAP_KEY` (and optional `API_BOOTSTRAP_EXPIRES_AT`) in `.env` before starting the API.

### Authorization
- Single tenant, read-only. All valid keys have the same data access rights initially.
- Plan type (`weekly|monthly`) recorded for operational purposes; can be used to derive quotas.

### Rate limiting (planned)
- Per-key token bucket with two limits:
  - Short-term RPS: `API_RATE_RPS`.
  - Long-term daily cap: `API_DAILY_CAP`.
- Return `429 Too Many Requests` once exceeded and include `Retry-After`.

### Data integrity
- Deterministic IDs for idempotency; ingestion should use upserts to avoid duplicates.
- Input validation via Pydantic schemas (to be added) ensures strict parameter handling.

### Transport
- OpenSearch runs with TLS inside Docker; client verification disabled in-container for local dev.
- Externally expose only via secure reverse proxy (e.g., Nginx with TLS) for production.

### Key management (planned CLI)
- Commands: create, list, revoke.
- Export/import for backup.


