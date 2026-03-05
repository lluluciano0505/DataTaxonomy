#!/bin/bash
# run.sh — 最简单的启动脚本
# 直接运行本脚本即可：./run.sh

cd "$(dirname "$0")" || exit 1

python3 launcher.py
