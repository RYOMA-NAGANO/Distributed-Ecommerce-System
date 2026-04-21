#!/bin/bash
set -e

until python3 manage.py run_ups_daemon --timeout "${UPS_DAEMON_TIMEOUT:-5}"
do
    echo "Initial World handshake failed, retrying in ${WORLD_RETRY_SECONDS:-5} seconds..."
    sleep "${WORLD_RETRY_SECONDS:-5}"
done

echo "Initial World handshake succeeded. Keeping ups-daemon container alive."
tail -f /dev/null
