#!/bin/bash
# run.sh — simplest startup script
# Run this script directly: ./scripts/run.sh

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR" || exit 1

python3 launcher.py
