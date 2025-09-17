## Ingestion

### Sources
- Gamma API (markets)
- Data-API (trades)
- (Planned) Order book snapshots via CLOB REST and optional WS deltas

### Workers
- Markets worker
  - Polls `GET /markets` on Gamma.
  - Normalizes payload and creates/updates `markets_v1` documents using deterministic IDs (`market_id` or fallback hash).
- Trades worker
  - Polls `POLYMARKET_TRADES_BASE`.
  - Normalizes timestamp (`ts` ISO8601), `market_id` (from `conditionId` if needed), and `side`.
  - Routes documents to `trades_v1-YYYY.MM.DD` by `ts`.
  - Deterministic `_id` from `{txHash}:{asset}:{ts}` with hash fallback.
  - Idempotent upserts (`_op_type: index`) to avoid duplicates.

### Backfill and polling
- Backfill runs a time-windowed loop (oldest to newest) with pagination; checkpoint last processed `ts`.
- Polling runs at configured intervals, ingesting since last checkpoint.
- Deduplication via deterministic IDs and idempotent upserts.

### Candles derivation (planned)
### Candles derivation
- Compute OHLCV for `1m,5m,1h` timeboxes aligned to boundaries.
- Key: `{market_id, interval, open_time}`; write to `candles_v1` via idempotent upserts.
- Worker scans trades within each interval, computes OHLCV, and advances a checkpoint per interval.

### Orderbook snapshots (planned)
### Orderbook snapshots
- Periodic top-N depth snapshots by side; key `(market_id, ts, side)`.
- Configurable `ORDERBOOK_MARKET_IDS` to limit scope; future WS deltas can be added post-MVP.

### Configuration
- Poll intervals: `POLL_INTERVAL_MARKETS_MS`, `POLL_INTERVAL_TRADES_MS`.
- Feature flags: `ENABLE_TRADES_INGESTER`.
- OpenSearch connection: `OPENSEARCH_URL`, credentials.
- Trades backfill: `TRADES_PAGE_SIZE`, `TRADES_BACKFILL_DAYS`, `TRADES_BACKFILL_WINDOW_MINUTES`, `TRADES_CHECKPOINT_PATH`.
- Candles: `ENABLE_CANDLES_WORKER`, `CANDLES_INTERVALS`, `CANDLES_LOOKBACK_MINUTES`, `CANDLES_TRADES_FETCH_LIMIT`, `CANDLES_POLL_MS`, `CANDLES_CHECKPOINT_DIR`.
- Orderbook: `ENABLE_ORDERBOOK_WORKER`, `ORDERBOOK_MARKET_IDS`, `ORDERBOOK_DEPTH`, `ORDERBOOK_POLL_MS`, `ORDERBOOK_CHECKPOINT_PATH`, `POLYMARKET_CLOB_BASE`.

### Operational notes
- OpenSearch in this stack is HTTPS; set `OPENSEARCH_URL=https://opensearch:9200` inside Docker.
- Use bulk writes with reasonable batch sizes and retries; monitor failures and log sample errors.


