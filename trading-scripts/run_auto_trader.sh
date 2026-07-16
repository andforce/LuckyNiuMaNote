#!/bin/bash
cd -- "$(dirname -- "${BASH_SOURCE[0]}")" || exit 1
source .venv/bin/activate
exec python scripts/auto_trader_nostalgia_for_infinity.py
