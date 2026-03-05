#!/bin/bash
# start_web.sh — one-click launcher for the web configurator
# Double-click to run or execute in terminal: ./scripts/start_web.sh

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR" || exit 1

echo "🚀 Starting DataTaxonomy web configurator..."
echo "📱 Open: http://localhost:8502"
echo ""

# Start streamlit
python -m streamlit run config_ui.py --server.port 8502 --logger.level=error

# If you want to auto-open the browser (requires a delay), uncomment the line below:
# sleep 3 && open "http://localhost:8502" &
