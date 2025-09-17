## Database (OpenSearch)

### Indices and templates
- `markets_v1`
  - Fields: `market_id (keyword)`, `title (text/keyword)`, `category (keyword)`, `status (keyword)`, `created_at (date)`, `close_time (date)`.
- `trades_v1-*`
  - Fields: `trade_id (keyword)`, `market_id (keyword)`, `ts (date)`, `price (float)`, `size (float)`, `side (keyword)`.
- `candles_v1`
  - Fields: `market_id (keyword)`, `interval (keyword)`, `open_time (date)`, `open/high/low/close/volume (float)`.
- `orderbook_snapshots_v1`
  - Fields: `market_id (keyword)`, `ts (date)`, `side (keyword)`, `levels (nested: price,size,level)`.

Templates and ILM policies are defined under `database/opensearch/templates` and `database/opensearch/ilm` and installed by `database/opensearch/scripts/setup.sh`.

### ILM/ISM policy
- `90d_delete`: single hot state, transition to delete after 90 days.

### Setup
1) Start OpenSearch (see Operations docs).
2) Run:
```
bash database/opensearch/scripts/setup.sh
```
This creates index templates, the ILM policy, and base indices (`markets_v1`, `candles_v1`).

Windows: run via Git Bash or WSL. Ensure `curl` and `jq` are available.

### Connection settings
- In Docker, use `OPENSEARCH_URL=https://opensearch:9200` with admin credentials.
- Clients in this repo disable cert verification inside containers to ease local use.

### Query patterns
- Markets: text search on title with filters and sort by `created_at`.
- Trades: filter on `market_id`, range on `ts`, sort on `ts`, paginate.
- Candles: range on `open_time` and `interval`, sort ascending.
- Orderbook: latest or nearest-at snapshot per side.


