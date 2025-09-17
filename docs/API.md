## API Reference

Base URL: `http://localhost:8080`

Authentication: send header `X-API-Key: <key>` with every request.

### Conventions
- Timestamps: ISO8601 with timezone (e.g., `2025-09-17T12:34:56Z`).
- Pagination: offset/limit for now; cursor-based for trades is planned.
- Errors: HTTP status codes with JSON `{ "error": { "code": string, "message": string } }` planned; current implementation returns FastAPI default errors.

### Health
GET `/health`
Response: `{ "status": "ok" }`

### Markets
GET `/v1/markets`
- Query params:
  - `q` (string; optional): free-text over title/category/description.
  - `category` (string; optional)
  - `status` (string; optional)
  - `page` (int; default 1)
  - `limit` (int; default 100, max 1000)
Response:
```
{ "data": [ { ...market fields..., "_id": "..." } ], "page": 1, "limit": 100 }
```

GET `/v1/markets/{market_id}` (planned)
- Returns a single market document.

Example:
```
curl -H "X-API-Key: $KEY" "http://localhost:8080/v1/markets?q=election&status=open&limit=10"
```

### Trades
GET `/v1/trades`
- Query params:
  - `market_id` (string; required)
  - `from` (timestamp; optional)
  - `to` (timestamp; optional)
  - `sort` (string; default `ts:desc`)
  - `page` (int; default 1)
  - `limit` (int; default 100, max 1000)
Response:
```
{ "data": [ { ...trade fields..., "_id": "...", "_index": "trades_v1-YYYY.MM.DD" } ], "page": 1, "limit": 100 }
```

Example:
```
curl -H "X-API-Key: $KEY" "http://localhost:8080/v1/trades?market_id=abc&from=2025-09-16T00:00:00Z&to=2025-09-17T00:00:00Z&limit=50"
```

### Candles
GET `/v1/candles`
- Query params:
  - `market_id` (string; required)
  - `interval` (enum `1m|5m|1h`; required)
  - `from` (timestamp; required)
  - `to` (timestamp; required)
Response:
```
{ "market_id": "...", "interval": "1m", "candles": [ { "open_time": "...", "open": 0.1, "high": 0.2, "low": 0.1, "close": 0.15, "volume": 123.4 } ] }
```

### Orderbook
GET `/v1/orderbook`
- Query params:
  - `market_id` (string; required)
  - `side` (enum `bid|ask`; default `bid`)
  - `at` (timestamp; optional; returns the latest snapshot at/<= time)
Response:
```
{ "market_id": "...", "side": "bid", "ts": "...", "levels": [ { "price": 0.1, "size": 100, "level": 1 } ] }
```

### Notes
- Rate limiting: per-key token bucket to be added; expect `429 Too Many Requests` with `Retry-After` when exceeded.
- Schema stability: field names reflect upstream data; consult OpenSearch mappings in `database/opensearch/templates`.


