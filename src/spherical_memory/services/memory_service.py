"""记忆管理服务 --- 记忆节点的存储、查询、坐标计算"""

import json
import math
from datetime import datetime

from spherical_memory.config import CONFIG
import spherical_memory.db.connection as conn_module
from spherical_memory.db.schema import get_meta, set_meta
from spherical_memory.models.memory import MemoryNode
from spherical_memory.services.gravity_service import (
    _compute_phi,
    _compute_r,
    auto_link_new_memory,
)


def _compute_node_mass(
    personality_match: float,
    activation_count: int,
    event_core_degree: float,
    emotion_intensity: float,
) -> float:
    """计算节点初始质量"""
    # 激活频率归一化：0 次激活 = 0.3, 10 次以上 = 1.0
    act_norm = min(activation_count / 10.0, 1.0)
    mass = (
        CONFIG.mass_personality_weight * personality_match
        + CONFIG.mass_activation_weight * act_norm
        + CONFIG.mass_event_core_weight * event_core_degree
        + CONFIG.mass_emotion_intensity_weight * emotion_intensity
    )
    return max(0.1, min(mass, 1.0))


def store_memory(
    content: str,
    memory_type: str,
    event_ids: list[str] | None = None,
    personality_match: float = 0.5,
    emotion_intensity: float = 0.3,
    emotion_type: str = "neutral",
    semantic_tags: list[str] | None = None,
    summary: str | None = None,
    sub_type: str | None = None,
) -> dict:
    """存储一条新记忆到球状记忆空间"""

    # 1. 坐标计算
    phi = _compute_phi(memory_type, sub_type)

    # theta 由主事件决定
    theta = 0.0
    if event_ids:
        first_event = conn_module.db.fetchone("SELECT theta FROM events WHERE id = ?", (event_ids[0],))
        if first_event:
            theta = first_event["theta"]

    # 2. 节点质量
    node_mass = _compute_node_mass(personality_match, 0, 0.3, emotion_intensity)

    # 3. 摘要
    if not summary:
        summary = content[:100]

    # 4. 语义标签
    tags = semantic_tags or []
    tags_json = json.dumps(tags, ensure_ascii=False)

    # 5. 创建记忆节点
    mem = MemoryNode(
        content=content,
        memory_type=memory_type,
        phi=phi,
        theta=theta,
        node_mass=node_mass,
        personality_match=personality_match,
        emotion_intensity=emotion_intensity,
        emotion_type=emotion_type,
        semantic_tags=tags,
        sub_type=sub_type,
        summary=summary or "",
    )

    conn_module.db.execute(
        """INSERT INTO memories
           (id, content, summary, phi, theta, memory_type, sub_type,
            node_mass, personality_match, activation_count, event_core_degree,
            emotion_intensity, emotion_type, semantic_tags, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0.3, ?, ?, ?, ?)""",
        (
            mem.id, mem.content, mem.summary, mem.phi, mem.theta,
            mem.memory_type, mem.sub_type, mem.node_mass,
            mem.personality_match, mem.emotion_intensity,
            mem.emotion_type, tags_json, mem.created_at,
        ),
    )

    # 6. 更新系统时间元数据
    now_ts = datetime.now().timestamp()
    et = get_meta("earliest_time")
    if not et or now_ts < float(et):
        set_meta("earliest_time", str(now_ts))
    set_meta("latest_time", str(now_ts))

    # 7. 关联事件
    if event_ids:
        for eid in event_ids:
            try:
                conn_module.db.execute(
                    "INSERT INTO memory_events (memory_id, event_id, is_primary) VALUES (?, ?, ?)",
                    (mem.id, eid, 1 if eid == event_ids[0] else 0),
                )
            except Exception:
                pass

    # 8. 自动建立引力链接
    links = auto_link_new_memory(mem)

    # 9. 构建返回
    r = _compute_r(mem.created_at)
    return {
        "memory_id": mem.id,
        "coordinate": {"r": round(r, 4), "phi": round(phi, 4), "theta": round(theta, 4)},
        "node_mass": round(node_mass, 4),
        "gravity_links_created": len(links),
        "related_memories": links,
    }


def get_memory(memory_id: str) -> MemoryNode | None:
    row = conn_module.db.fetchone("SELECT * FROM memories WHERE id = ?", (memory_id,))
    return MemoryNode.from_row(row) if row else None


def increment_activation(memory_id: str) -> None:
    """激活计数 +1，更新最后激活时间"""
    conn_module.db.execute(
        """UPDATE memories SET
           activation_count = activation_count + 1,
           last_activated = datetime('now'),
           updated_at = datetime('now')
           WHERE id = ?""",
        (memory_id,),
    )


def recalculate_mass(memory_id: str) -> float:
    """重新计算节点质量"""
    row = conn_module.db.fetchone("SELECT * FROM memories WHERE id = ?", (memory_id,))
    if not row:
        return 0.0
    mem = MemoryNode.from_row(row)
    act_norm = min(mem.activation_count / 10.0, 1.0)
    new_mass = (
        CONFIG.mass_personality_weight * mem.personality_match
        + CONFIG.mass_activation_weight * act_norm
        + CONFIG.mass_event_core_weight * mem.event_core_degree
        + CONFIG.mass_emotion_intensity_weight * mem.emotion_intensity
    )
    new_mass = max(0.1, min(new_mass, 1.0))
    conn_module.db.execute(
        "UPDATE memories SET node_mass = ?, updated_at = datetime('now') WHERE id = ?",
        (new_mass, memory_id),
    )
    return new_mass


def get_memory_stats(detail_level: str = "summary") -> dict:
    """获取记忆空间概况"""
    stats = conn_module.db.fetchone("""
        SELECT
            COUNT(*) as total_memories,
            COALESCE(AVG(node_mass), 0) as avg_mass,
            COALESCE(SUM(CASE WHEN node_mass < 0.1 THEN 1 ELSE 0 END), 0) as below_threshold
        FROM memories
    """)
    event_count = conn_module.db.fetchone("SELECT COUNT(*) as cnt FROM events")
    link_count = conn_module.db.fetchone("SELECT COUNT(*) as cnt FROM gravity_links")

    # 类型分布
    type_dist = {}
    for t in ["coding", "creation", "discussion", "planning", "emotion", "life", "learning"]:
        row = conn_module.db.fetchone("SELECT COUNT(*) as cnt FROM memories WHERE memory_type = ?", (t,))
        type_dist[t] = row["cnt"] if row else 0

    # top 大质量节点（最多 5 个）
    top_mass = conn_module.db.fetchall(
        "SELECT id, summary, node_mass, memory_type FROM memories ORDER BY node_mass DESC LIMIT 5"
    )

    # 最近记忆（最多 5 条）
    recent = conn_module.db.fetchall(
        "SELECT id, summary, created_at FROM memories ORDER BY created_at DESC LIMIT 5"
    )

    result = {
        "total_memories": stats["total_memories"] if stats else 0,
        "total_events": event_count["cnt"] if event_count else 0,
        "total_gravity_links": link_count["cnt"] if link_count else 0,
        "type_distribution": type_dist,
        "top_mass_memories": [
            {
                "memory_id": r["id"],
                "summary": r["summary"] or "",
                "node_mass": round(r["node_mass"], 4),
                "type": r["memory_type"],
            }
            for r in top_mass
        ],
        "recent_memories": [
            {
                "memory_id": r["id"],
                "summary": r["summary"] or "",
                "created_at": r["created_at"],
            }
            for r in recent
        ],
        "decay_status": {
            "avg_mass": round(stats["avg_mass"], 4) if stats else 0.0,
            "memories_below_threshold": stats["below_threshold"] if stats else 0,
        },
    }

    return result
