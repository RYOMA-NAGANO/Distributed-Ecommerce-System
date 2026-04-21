#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

python3 -m grpc_tools.protoc \
  -I"${SCRIPT_DIR}/src" \
  --python_out="${SCRIPT_DIR}" \
  "${SCRIPT_DIR}/src/world_ups.proto" \
  "${SCRIPT_DIR}/src/world_amazon.proto"
