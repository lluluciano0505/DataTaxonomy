#!/bin/bash
# start_web.command — macOS double-click wrapper (delegates to start_web.sh)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

exec "$SCRIPT_DIR/start_web.sh"
