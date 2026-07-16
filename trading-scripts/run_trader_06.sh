#!/bin/bash
cd -- "$(dirname -- "${BASH_SOURCE[0]}")" || exit 1
source .venv/bin/activate
exec python scripts/trader_06_bb_mean_reversion.py
