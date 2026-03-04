#!/bin/bash
# startup.sh — Convenient startup script for DataTaxonomy

set -e

echo "🎯 DataTaxonomy Local App"
echo "========================="
echo ""

# Check if config.yaml exists
if [ ! -f "config.yaml" ]; then
    echo "❌ config.yaml not found!"
    echo "Please create config.yaml first."
    exit 1
fi

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "❌ .env not found!"
    echo "Creating from template..."
    cp .env.example .env
    echo "⚠️  Please edit .env and add your OPENROUTER_API_KEY"
    exit 1
fi

# Check API key
if ! grep -q "OPENROUTER_API_KEY" .env || grep -q "OPENROUTER_API_KEY=your_key_here" .env; then
    echo "❌ OPENROUTER_API_KEY not set in .env!"
    echo "Please edit .env and add your API key."
    exit 1
fi

echo "✅ Configuration OK"
echo ""

# Option selection
echo "Choose what to run:"
echo "1) Process data only (no dashboard)"
echo "2) Full pipeline (process + dashboard)"
echo "3) Dashboard only (skip processing)"
echo ""
read -p "Enter choice (1-3): " choice

case $choice in
    1)
        echo ""
        echo "📊 Processing data..."
        python main.py --no-dashboard
        ;;
    2)
        echo ""
        echo "🚀 Running full pipeline..."
        python main.py
        ;;
    3)
        echo ""
        echo "📈 Launching dashboard..."
        streamlit run dashboard.py
        ;;
    *)
        echo "❌ Invalid choice"
        exit 1
        ;;
esac
