## Optimization and Scaling Guide

### Ingestion performance
- Batch size: tune bulk helper to ~1–5 MB per batch; monitor latency and failures.
- Parallelism: run multiple workers with partitioned workloads (e.g., market shards).
- Backoff: exponential with jitter; respect upstream rate limits.

### OpenSearch tuning
- Heap: set `-Xms/-Xmx` per available memory (50% rule of thumb, max 32 GB).
- Sharding: start with 1 shard; increase for higher throughput. Time-based indices for trades are already partitioned daily.
- Refresh interval: consider increasing during heavy ingestion to reduce segment churn.
- Rollover: add `max_primary_shard_size` or `max_age` policies for `trades_v1-*` if needed.

### API performance
- Use filter+sort on keyword/date fields; avoid wildcard queries.
- Add cursor-based pagination for large scans to reduce deep paging cost.
- Cache hot queries (memory/LRU) where appropriate.

### Cost controls
- Retention at 90d; compress mappings and avoid unnecessary fields.
- Snapshot (optional) to cheap storage if long-term is required (out of scope here).

### Observability (future)
- Metrics: ingestion rates, bulk failures, API latencies, OS query latency.
- Dashboards: OpenSearch Dashboards visualizations for index sizes and doc counts.


