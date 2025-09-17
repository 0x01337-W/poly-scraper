## Operations Runbook

### Prerequisites
- Docker Desktop
- Git Bash or WSL (for running `database/opensearch/scripts/setup.sh`)

### Environment
1) Copy `.env.example` to `.env` and edit values.
2) Important: set a strong `OPENSEARCH_INITIAL_ADMIN_PASSWORD`.
3) Ensure `OPENSEARCH_URL` uses HTTPS when running in Docker: `https://opensearch:9200`.

### Bring up OpenSearch only
```
docker compose -f database/opensearch/docker-compose.yml up -d
```

Initialize templates and ILM:
```
bash database/opensearch/scripts/setup.sh
```

### Bring up full stack
```
docker compose up -d
```

Services:
- `opensearch`, `opensearch-dashboards`, `polyscraper-api`, `polyscraper-ingester`.

### Health checks
- OpenSearch: `curl -k -u admin:$OPENSEARCH_INITIAL_ADMIN_PASSWORD https://localhost:9200/_cluster/health`
- API: `curl -H "X-API-Key: $KEY" http://localhost:8080/health`

### API key management
- Bootstrap via env: set `API_BOOTSTRAP_KEY` in `.env` before first start.
- Store path: `API_KEY_DB_PATH` (default `/data/keys.db` inside container volume `api-data`).
- Admin CLI (planned) will support create/list/revoke.

### Troubleshooting
- If API/ingester cannot connect to OpenSearch, verify scheme is HTTPS in `OPENSEARCH_URL`.
- Run `docker logs opensearch` and `docker logs polyscraper-api` for errors.
- Ensure templates installed: check `GET /_index_template` in OpenSearch Dashboards (Kibana-compatible).


