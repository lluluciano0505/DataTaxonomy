#!/bin/bash
# start_web.sh — 一键启动网页配置器
# 直接双击运行或在终端执行: ./start_web.sh

cd "$(dirname "$0")" || exit 1

echo "🚀 启动 DataTaxonomy 网页配置器..."
echo "📱 访问：http://localhost:8502"
echo ""

# 启动 streamlit
python -m streamlit run config_ui.py --server.port 8502 --logger.level=error

# 如果希望自动打开浏览器（需要延迟），可取消注释下面行：
# sleep 3 && open "http://localhost:8502" &
