#!/bin/bash
# Open DataTaxonomy.command — double-click launcher for macOS

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR" || exit 1

PYTHON_CMD=""
if [ -x "/opt/anaconda3/bin/python" ]; then
  PYTHON_CMD="/opt/anaconda3/bin/python"
elif command -v python >/dev/null 2>&1; then
  PYTHON_CMD="$(command -v python)"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_CMD="$(command -v python3)"
else
  echo "❌ Python not found."
  read -n 1 -s -r -p "Press any key to close..."
  exit 1
fi

echo "🎯 DataTaxonomy Launcher"
echo "========================"
echo ""
echo "1) Open Config UI"
echo "2) Open Dashboard"
echo "3) Run Full Pipeline"
echo ""
read -p "Choose (1-3): " choice

auto_open() {
  local url="$1"
  (sleep 3; open "$url") >/dev/null 2>&1 &
}

case "$choice" in
  1)
    echo ""
    echo "⚙️ Starting Config UI..."
    echo "🌐 http://localhost:8502"
    auto_open "http://localhost:8502"
    exec "$PYTHON_CMD" -m streamlit run config_ui.py --server.port 8502 --logger.level=error
    ;;
  2)
    echo ""
    echo "📊 Starting Dashboard..."
    echo "🌐 http://localhost:8501"
    auto_open "http://localhost:8501"
    exec "$PYTHON_CMD" -m streamlit run dashboard.py --server.port 8501 --logger.level=error
    ;;
  3)
    echo ""
    echo "🚀 Running Full Pipeline..."
    exec "$PYTHON_CMD" main.py
    ;;
  *)
    echo "❌ Invalid choice"
    read -n 1 -s -r -p "Press any key to close..."
    exit 1
    ;;
esac
