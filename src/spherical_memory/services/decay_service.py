"""衰减服务 --- 遗忘机制：质量衰减 & 空间沉降 & 强引力唤醒"""

from spherical_memory.config import CONFIG
import spherical_memory.db.connection as conn_module


def decay_memories(decay_rate: float = 0.95, batch_size: int = 100) -> dict:
    """执行一轮质量衰减"""

    decay_rate = decay_rate if decay_rate is not None else CONFIG.decay_rate
    batch_size = min(batch_size, CONFIG.decay_batch_size)

    # 获取当前平均质量
    avg_before_row = conn_module.db.fetchone("SELECT COALESCE(AVG(node_mass), 0) as avg FROM memories")
    avg_before = avg_before_row["avg"] if avg_before_row else 0.0

    # 衰减豁免：核心记忆（mass >= 1.0）、最近激活的、用户手动链接的
    rows = conn_module.db.fetchall(
        """SELECT id, node_mass FROM memories
           WHERE node_mass < 1.0          -- 豁免核心记忆
             AND node_mass > 0.01         -- 已经沉降的跳过
             AND (
                 last_activated IS NULL
                 OR last_activated < datetime('now', '-7 days')  -- 最近 7 天激活的豁免
             )
           ORDER BY node_mass ASC
           LIMIT ?""",
        (batch_size,),
    )

    decayed = 0
    updates = []
    for row in rows:
        new_mass = max(row["node_mass"] * decay_rate, 0.01)
        updates.append((new_mass, row["id"]))
        decayed += 1

    if updates:
        conn_module.db.executemany(
            "UPDATE memories SET node_mass = ?, updated_at = datetime('now') WHERE id = ?",
            updates,
        )

    # 统计沉降层
    sunken_row = conn_module.db.fetchone(
        "SELECT COUNT(*) as cnt FROM memories WHERE node_mass < ?",
        (CONFIG.sunken_threshold,),
    )
    sunken = sunken_row["cnt"] if sunken_row else 0

    # 衰减后平均质量
    avg_after_row = conn_module.db.fetchone("SELECT COALESCE(AVG(node_mass), 0) as avg FROM memories")
    avg_after = avg_after_row["avg"] if avg_after_row else 0.0

    return {
        "memories_processed": decayed,
        "memories_decayed": decayed,
        "memories_sunken": sunken,
        "avg_mass_before": round(avg_before, 4),
        "avg_mass_after": round(avg_after, 4),
    }


def try_awaken(memory_id: str, effective_gravity: float) -> bool:
    """
    检查是否应该通过强引力唤醒一条沉降记忆。
    唤醒条件：settled (mass < 0.1) AND effective_gravity > awakening_threshold (0.8)
    """
    row = conn_module.db.fetchone("SELECT node_mass FROM memories WHERE id = ?", (memory_id,))
    if not row:
        return False

    if row["node_mass"] < CONFIG.sunken_threshold and effective_gravity > CONFIG.awakening_threshold:
        conn_module.db.execute(
            "UPDATE memories SET node_mass = 0.3, last_activated = datetime('now'), updated_at = datetime('now') WHERE id = ?",
            (memory_id,),
        )
        return True
    return False
