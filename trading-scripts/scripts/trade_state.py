"""交易状态持久化 — 重启后恢复冷却时间"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

STATE_DIR = Path(__file__).resolve().parents[1].parent / "memory" / "trading"
STATE_DIR.mkdir(parents=True, exist_ok=True)


def load_trade_times(strategy_name: str) -> dict:
    path = STATE_DIR / f"{strategy_name}_state.json"
    if path.exists():
        try:
            with open(path, "r") as f:
                data = json.load(f)
            times = data.get("last_trade_time", {})
            logger.info(f"已恢复交易状态 [{strategy_name}]: {times}")
            return times
        except Exception as e:
            logger.warning(f"读取状态文件失败 [{strategy_name}]: {e}")
    return {}


def save_trade_times(strategy_name: str, last_trade_time: dict):
    path = STATE_DIR / f"{strategy_name}_state.json"
    try:
        with open(path, "w") as f:
            json.dump({"last_trade_time": last_trade_time}, f, indent=2)
    except Exception as e:
        logger.warning(f"保存状态文件失败 [{strategy_name}]: {e}")
