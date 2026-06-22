"""对话心跳服务 — 自动追踪轮次并触发记忆固化"""

from datetime import datetime, timezone

from spherical_memory.config import CONFIG
from spherical_memory.db.schema import get_meta, set_meta


def _ensure_counter() -> int:
    """初始化或读取当前轮次计数"""
    val = get_meta("heartbeat_counter")
    if val is None:
        set_meta("heartbeat_counter", "0")
        set_meta("heartbeat_since_consolidation", "0")
        set_meta("heartbeat_last_consolidation", datetime.now(timezone.utc).isoformat())
        return 0
    return int(val)


def auto_advance() -> dict | None:
    """
    寄生式心跳 — 在任何工具调用时自动推进计数器。
    不需要 Agent 显式调用 heartbeat，只要用了 recall 或 store 就自动走。

    返回: 如果本轮应该 consolidate，返回信号 dict；否则返回 None
    """
    counter = _ensure_counter()
    counter += 1
    set_meta("heartbeat_counter", str(counter))

    since = get_meta("heartbeat_since_consolidation") or "0"
    since = int(since) + 1
    set_meta("heartbeat_since_consolidation", str(since))

    interval = CONFIG.heartbeat_interval
    last_consolidation = get_meta("heartbeat_last_consolidation") or "never"

    if counter % interval == 0:
        set_meta("heartbeat_since_consolidation", "0")
        set_meta("heartbeat_last_consolidation", datetime.now(timezone.utc).isoformat())
        return {
            "consolidate": True,
            "turn_count": counter,
            "message": "本轮对话应执行记忆固化，批量调用 store_memory 存入本次对话的关键信息",
        }
    return None


def conversation_heartbeat() -> dict:
    """
    对话心跳 — 只读查询当前状态（兼容旧版用法）。
    不自增计数器，计数已寄生在核心工具（store/recall 等）的 auto_advance() 中。
    重复调用此工具不会导致双重计数。
    """
    counter = _ensure_counter()
    since = int(get_meta("heartbeat_since_consolidation") or "0")
    interval = CONFIG.heartbeat_interval
    consolidate = counter % interval == 0
    last_consolidation = get_meta("heartbeat_last_consolidation") or "never"

    next_at = counter + (interval - (counter % interval)) if counter % interval != 0 else counter + interval

    return {
        "turn_count": counter,
        "turns_since_consolidation": since,
        "consolidate": consolidate,
        "next_consolidation_at": next_at,
        "last_consolidation": last_consolidation,
        "heartbeat_interval": interval,
    }
