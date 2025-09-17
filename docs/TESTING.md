## Testing and Validation

### Ingestion tests
- Unit tests for payload normalization (markets, trades) using fixtures.
- Idempotency tests: re-run the same batch; assert no duplicates are created (via deterministic IDs).

### API tests
- Contract tests for each endpoint: status codes, required params, schema of responses.
- Pagination tests: page/limit bounds and sorting correctness.

### Data validation
- Spot-check candles vs recomputed OHLCV from trades for sampled windows.
- Daily sanity metrics: trades per market per day; alert on large deviations.

### Tooling
- Python: `pytest`, `httpx` test client, FastAPI `TestClient`.
- Optional: Postman collection with example requests (export in `docs/postman_collection.json`).


