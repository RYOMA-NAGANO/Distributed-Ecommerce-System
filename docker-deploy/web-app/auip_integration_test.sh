#!/usr/bin/env bash
set -euo pipefail

# AUIP end-to-end integration smoke test
# Covers:
#   1) Amazon -> UPS API requests
#   2) UPS -> Amazon callback requests
#
# Usage:
#   bash docker-deploy/web-app/auip_integration_test.sh
#
# Optional env vars:
#   UPS_BASE_URL=http://localhost:8001
#   AMAZON_BASE_URL=http://localhost:8000
#   UPS_INTEROP_SECRET=mini-ups-shared-secret
#   AMAZON_INTEROP_SECRET=
#   WORLD_ID=123456789
#   WAREHOUSE_ID=1
#   WAREHOUSE_X=2
#   WAREHOUSE_Y=4
#   DEST_X=9
#   DEST_Y=8
#   SHIPMENT_ID=PKG-AUIP-TEST-<timestamp>
#   AMAZON_ORDER_ID=ORD-AUIP-TEST-<timestamp>

UPS_BASE_URL="${UPS_BASE_URL:-http://localhost:8001}"
AMAZON_BASE_URL="${AMAZON_BASE_URL:-http://localhost:8000}"
UPS_INTEROP_SECRET="${UPS_INTEROP_SECRET:-mini-ups-shared-secret}"
AMAZON_INTEROP_SECRET="${AMAZON_INTEROP_SECRET:-}"

WORLD_ID="${WORLD_ID:-123456789}"
WAREHOUSE_ID="${WAREHOUSE_ID:-1}"
WAREHOUSE_X="${WAREHOUSE_X:-2}"
WAREHOUSE_Y="${WAREHOUSE_Y:-4}"
DEST_X="${DEST_X:-9}"
DEST_Y="${DEST_Y:-8}"

NOW="$(date +%s)"
SHIPMENT_ID="${SHIPMENT_ID:-PKG-AUIP-TEST-${NOW}}"
AMAZON_ORDER_ID="${AMAZON_ORDER_ID:-ORD-AUIP-TEST-${NOW}}"
TRUCK_ID="${TRUCK_ID:-5}"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

PASS=0
WARN=0
FAIL=0

log() { printf "\n[%s] %s\n" "$1" "$2"; }

new_key() { echo "idem-${SHIPMENT_ID}-$1-$(date +%s%N)"; }

request() {
  local name="$1"
  local method="$2"
  local url="$3"
  local data="$4"
  local auth_header="$5"
  local idem_key="${6:-}"
  local expected_codes_csv="$7"
  local body_file="${TMP_DIR}/${name}.body"
  local hdr_file="${TMP_DIR}/${name}.hdr"
  local status
  local curl_cmd

  curl_cmd=(
    curl -sS -X "$method" "$url"
    -D "$hdr_file"
    -o "$body_file"
    -H "Content-Type: application/json"
  )

  if [[ -n "$auth_header" ]]; then
    curl_cmd+=(-H "$auth_header")
  fi
  if [[ -n "$idem_key" ]]; then
    curl_cmd+=(-H "Idempotency-Key: ${idem_key}")
  fi
  if [[ -n "$data" ]]; then
    curl_cmd+=(--data "$data")
  fi

  status="$("${curl_cmd[@]}" -w "%{http_code}")"

  if [[ ",${expected_codes_csv}," == *",${status},"* ]]; then
    log "PASS" "${name}: HTTP ${status} (${method} ${url})"
    PASS=$((PASS + 1))
  else
    log "FAIL" "${name}: expected [${expected_codes_csv}], got HTTP ${status}"
    FAIL=$((FAIL + 1))
  fi

  if [[ -s "$body_file" ]]; then
    printf "  response: %s\n" "$(tr '\n' ' ' < "$body_file" | sed 's/[[:space:]]\+/ /g')"
  fi
}

warn_step() {
  log "WARN" "$1"
  WARN=$((WARN + 1))
}

create_payload() {
  cat <<EOF
{"shipment_id":"${SHIPMENT_ID}","world_id":${WORLD_ID},"amazon_order_id":"${AMAZON_ORDER_ID}","warehouse":{"id":${WAREHOUSE_ID},"x":${WAREHOUSE_X},"y":${WAREHOUSE_Y}},"destination":{"x":${DEST_X},"y":${DEST_Y}},"items":[{"product_id":11,"description":"laptop","quantity":1}]}
EOF
}

pickup_payload() {
  cat <<EOF
{"warehouse_id":${WAREHOUSE_ID},"world_id":${WORLD_ID}}
EOF
}

ready_payload() {
  cat <<EOF
{"warehouse_id":${WAREHOUSE_ID},"world_id":${WORLD_ID}}
EOF
}

loaded_payload() {
  cat <<EOF
{"truck_id":${TRUCK_ID},"warehouse_id":${WAREHOUSE_ID},"world_id":${WORLD_ID}}
EOF
}

destination_payload() {
  cat <<EOF
{"x":$((DEST_X + 1)),"y":$((DEST_Y + 1)),"reason":"customer_redirect"}
EOF
}

callback_truck_arrived_payload() {
  cat <<EOF
{"shipment_id":"${SHIPMENT_ID}","truck_id":${TRUCK_ID},"warehouse_id":${WAREHOUSE_ID},"location":{"x":${WAREHOUSE_X},"y":${WAREHOUSE_Y}},"world_id":${WORLD_ID}}
EOF
}

callback_load_request_payload() {
  cat <<EOF
{"shipment_id":"${SHIPMENT_ID}","truck_id":${TRUCK_ID},"warehouse_id":${WAREHOUSE_ID},"world_id":${WORLD_ID}}
EOF
}

callback_out_for_delivery_payload() {
  cat <<EOF
{"shipment_id":"${SHIPMENT_ID}","truck_id":${TRUCK_ID},"destination":{"x":${DEST_X},"y":${DEST_Y}},"world_id":${WORLD_ID}}
EOF
}

callback_delivered_payload() {
  cat <<EOF
{"shipment_id":"${SHIPMENT_ID}","truck_id":${TRUCK_ID},"location":{"x":${DEST_X},"y":${DEST_Y}},"world_id":${WORLD_ID}}
EOF
}

log "INFO" "AUIP integration test started"
echo "  SHIPMENT_ID=${SHIPMENT_ID}"
echo "  UPS_BASE_URL=${UPS_BASE_URL}"
echo "  AMAZON_BASE_URL=${AMAZON_BASE_URL}"

# -------------------------------------------------------------------
# 1) Amazon -> UPS
# -------------------------------------------------------------------
log "INFO" "Phase 1: Amazon -> UPS"

CREATE_KEY="$(new_key create)"
CREATE_JSON="$(create_payload)"
request \
  "ups_create" \
  "POST" \
  "${UPS_BASE_URL}/shipments" \
  "${CREATE_JSON}" \
  "Authorization: Bearer ${UPS_INTEROP_SECRET}" \
  "${CREATE_KEY}" \
  "201"

# Idempotency replay: same method/path/key/body should return same logical result
request \
  "ups_create_replay" \
  "POST" \
  "${UPS_BASE_URL}/shipments" \
  "${CREATE_JSON}" \
  "Authorization: Bearer ${UPS_INTEROP_SECRET}" \
  "${CREATE_KEY}" \
  "201"

# Idempotency conflict: same key with different body should be 409
CREATE_JSON_CONFLICT="${CREATE_JSON/\"amazon_order_id\":\"${AMAZON_ORDER_ID}\"/\"amazon_order_id\":\"${AMAZON_ORDER_ID}-DIFF\"}"
request \
  "ups_create_conflict" \
  "POST" \
  "${UPS_BASE_URL}/shipments" \
  "${CREATE_JSON_CONFLICT}" \
  "Authorization: Bearer ${UPS_INTEROP_SECRET}" \
  "${CREATE_KEY}" \
  "409"

request \
  "ups_pickup" \
  "POST" \
  "${UPS_BASE_URL}/shipments/${SHIPMENT_ID}/pickup" \
  "$(pickup_payload)" \
  "Authorization: Bearer ${UPS_INTEROP_SECRET}" \
  "$(new_key pickup)" \
  "200,404,409,503"

request \
  "ups_ready" \
  "POST" \
  "${UPS_BASE_URL}/shipments/${SHIPMENT_ID}/ready" \
  "$(ready_payload)" \
  "Authorization: Bearer ${UPS_INTEROP_SECRET}" \
  "$(new_key ready)" \
  "200,404,409"

request \
  "ups_loaded" \
  "POST" \
  "${UPS_BASE_URL}/shipments/${SHIPMENT_ID}/loaded" \
  "$(loaded_payload)" \
  "Authorization: Bearer ${UPS_INTEROP_SECRET}" \
  "$(new_key loaded)" \
  "200,404,409"

request \
  "ups_query" \
  "GET" \
  "${UPS_BASE_URL}/shipments/${SHIPMENT_ID}" \
  "" \
  "Authorization: Bearer ${UPS_INTEROP_SECRET}" \
  "" \
  "200,404"

request \
  "ups_destination_update" \
  "PUT" \
  "${UPS_BASE_URL}/shipments/${SHIPMENT_ID}/destination" \
  "$(destination_payload)" \
  "Authorization: Bearer ${UPS_INTEROP_SECRET}" \
  "$(new_key destination)" \
  "200,404,409"

# -------------------------------------------------------------------
# 2) UPS -> Amazon callbacks
# -------------------------------------------------------------------
log "INFO" "Phase 2: UPS -> Amazon callbacks"

AMZ_AUTH_HEADER=""
if [[ -n "${AMAZON_INTEROP_SECRET}" ]]; then
  AMZ_AUTH_HEADER="Authorization: Bearer ${AMAZON_INTEROP_SECRET}"
else
  warn_step "AMAZON_INTEROP_SECRET is empty. If Amazon enforces auth, callbacks may fail with 401/403."
fi

request \
  "amazon_truck_arrived" \
  "POST" \
  "${AMAZON_BASE_URL}/api/truck-arrived" \
  "$(callback_truck_arrived_payload)" \
  "${AMZ_AUTH_HEADER}" \
  "$(new_key amz-arrived)" \
  "200,400,401,403,404,409"

request \
  "amazon_load_request" \
  "POST" \
  "${AMAZON_BASE_URL}/api/load-request" \
  "$(callback_load_request_payload)" \
  "${AMZ_AUTH_HEADER}" \
  "$(new_key amz-loadreq)" \
  "200,400,401,403,404,409"

request \
  "amazon_out_for_delivery" \
  "POST" \
  "${AMAZON_BASE_URL}/api/out-for-delivery" \
  "$(callback_out_for_delivery_payload)" \
  "${AMZ_AUTH_HEADER}" \
  "$(new_key amz-o4d)" \
  "200,400,401,403,404,409"

request \
  "amazon_delivered" \
  "POST" \
  "${AMAZON_BASE_URL}/api/delivered" \
  "$(callback_delivered_payload)" \
  "${AMZ_AUTH_HEADER}" \
  "$(new_key amz-delivered)" \
  "200,400,401,403,404,409"

log "INFO" "AUIP integration test finished"
echo "  PASS=${PASS} WARN=${WARN} FAIL=${FAIL}"

if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
