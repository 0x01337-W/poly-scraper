#!/usr/bin/env bash
set -euo pipefail

OS_URL="${OPENSEARCH_URL:-http://localhost:9200}"

echo "Creating index templates..."
curl -sS -X PUT "$OS_URL/_index_template/markets_v1" -H 'Content-Type: application/json' --data-binary @"$(dirname "$0")/../templates/markets_v1.json" | jq -r '.acknowledged'
curl -sS -X PUT "$OS_URL/_index_template/trades_v1"  -H 'Content-Type: application/json' --data-binary @"$(dirname "$0")/../templates/trades_v1.json"  | jq -r '.acknowledged'
curl -sS -X PUT "$OS_URL/_index_template/candles_v1" -H 'Content-Type: application/json' --data-binary @"$(dirname "$0")/../templates/candles_v1.json" | jq -r '.acknowledged'
curl -sS -X PUT "$OS_URL/_index_template/orderbook_snapshots_v1" -H 'Content-Type: application/json' --data-binary @"$(dirname "$0")/../templates/orderbook_snapshots_v1.json" | jq -r '.acknowledged'

echo "Creating ILM policy 90d_delete..."
curl -sS -X PUT "$OS_URL/_plugins/_ism/policies/90d_delete" -H 'Content-Type: application/json' --data-binary @"$(dirname "$0")/../ilm/90d_delete.json" | jq '.policy.policy_id' || true

echo "Setup complete."

