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


def conversation_heartbeat() -> dict:
    """
    对话心跳 — 每轮对话结束时由 Agent 调用。
    自动追踪轮次计数，按 heartbeat_interval 触发记忆固化信号。

    返回:
        {
            "turn_count": 当前总轮次,
            "turns_since_consolidation": 自上次固化以来的轮次数,
            "consolidate": true/false 是否应该执行记忆固化,
            "last_consolidation": 上次固化的时间
        }
    """
    counter = _ensure_counter()
    counter += 1
    set_meta("heartbeat_counter", str(counter))

    since = get_meta("heartbeat_since_consolidation") or "0"
    since = int(since) + 1
    set_meta("heartbeat_since_consolidation", str(since))

    interval = CONFIG.heartbeat_interval
    consolidate = counter % interval == 0

    last_consolidation = get_meta("heartbeat_last_consolidation") or "never"

    if consolidate:
        set_meta("heartbeat_since_consolidation", "0")
        set_meta("heartbeat_last_consolidation", datetime.now(timezone.utc).isoformat())
        since = 0

    return {
        "turn_count": counter,
        "turns_since_consolidation": since,
        "consolidate": consolidate,
        "next_consolidation_at": counter + (interval - (counter % interval)),
        "last_consolidation": last_consolidation,
        "heartbeat_interval": interval,
    }
