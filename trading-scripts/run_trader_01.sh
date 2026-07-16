#!/bin/bash
cd -- "$(dirname -- "${BASH_SOURCE[0]}")" || exit 1
source .venv/bin/activate
exec python scripts/trader_01_boll_macd.py
