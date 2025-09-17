## Roadmap

### MVP checklist
- [x] Monorepo scaffold and Docker Compose
- [x] OpenSearch templates and 90-day ILM
- [x] Markets ingestion (polling)
- [ ] Trades ingestion: pagination, backfill, idempotent upserts, checkpoints
- [ ] Candles derivation worker (1m/5m/1h) and endpoint validation
- [ ] Orderbook snapshots (forward-only), endpoint validation
- [ ] API: `GET /v1/markets/{market_id}`
- [ ] API: cursor-based pagination for trades
- [ ] API: rate limiting per API key
- [ ] Admin CLI for key management
- [ ] Documentation: complete docs and examples

### Post-MVP
- WebSocket MARKET consumer and delta compaction
- Frontend portal (docs + admin key UI)
- Monitoring and alerting (metrics, logs, dashboards)
- Data completeness reports per market
- PowerShell setup script for Windows


