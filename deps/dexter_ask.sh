#!/bin/bash
# Dexter 单问 shell 包装 — 供 Python bridge.py 调用
# 环境变量 DEEPSEEK_API_KEY 由 bridge.py 注入
set -e
export PATH="$HOME/.bun/bin:$PATH"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEXTER_DIR="$SCRIPT_DIR/../vendor/dexter"
cd "$DEXTER_DIR"
exec bun run ./ask.ts "$1"
