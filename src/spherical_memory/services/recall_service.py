"""检索服务 --- 引力扩散检索 & 坐标精确查询"""

from datetime import datetime

from spherical_memory.config import CONFIG
import spherical_memory.db.connection as conn_module
from spherical_memory.db.schema import get_meta
from spherical_memory.models.memory import MemoryNode
from spherical_memory.models.gravity_link import GravityLink
from spherical_memory.services.gravity_service import (
    jaccard_similarity,
    get_neighbor_links,
    _compute_r,
)
from spherical_memory.services.memory_service import (
    get_memory,
    increment_activation,
)


def _wrap_cold_start(raw_result: dict) -> dict:
    """将坐标查询结果包装成引力检索的返回结构"""
    return {
        "entry_point": None,
        "activated_memories": raw_result.get("memories", []),
        "activation_stats": {
            "total_candidates": raw_result.get("total_count", 0),
            "activated_count": len(raw_result.get("memories", [])),
            "avg_gravity": 0.0,
        },
        "_cold_start": True,
    }


def _find_entry_points(
    query_tags: list[str],
    memory_type_filter: list[str] | None = None,
    time_from: str | None = None,
    time_to: str | None = None,
    top_n: int = 5,
) -> list[MemoryNode]:
    """通过 query_tags 找到入口记忆节点（基于 Jaccard + node_mass）"""

    # 基础查询
    conditions = ["1=1"]
    params = []

    if memory_type_filter:
        placeholders = ",".join(["?" for _ in memory_type_filter])
        conditions.append(f"memory_type IN ({placeholders})")
        params.extend(memory_type_filter)

    if time_from:
        conditions.append("created_at >= ?")
        params.append(time_from)
    if time_to:
        conditions.append("created_at <= ?")
        params.append(time_to)

    where_clause = " AND ".join(conditions)
    rows = conn_module.db.fetchall(
        f"SELECT * FROM memories WHERE {where_clause} ORDER BY node_mass DESC LIMIT 200",
        tuple(params),
    )

    if not rows:
        return []

    # 按 Jaccard 相似度排序
    scored = []
    for row in rows:
        mem = MemoryNode.from_row(row)
        if query_tags:
            score = jaccard_similarity(query_tags, mem.semantic_tags)
        else:
            score = mem.node_mass  # 无标签时按质量排序
        scored.append((mem, score))

    scored.sort(key=lambda x: (x[1], x[0].node_mass), reverse=True)
    return [m for m, _ in scored[:top_n]]


def recall_by_coordinate(
    memory_type: str | None = None,
    event_id: str | None = None,
    time_from: str | None = None,
    time_to: str | None = None,
    keyword: str | None = None,
    limit: int = 10,
    sort_by: str = "time_desc",
) -> dict:
    """通过球坐标三轴交叉精确定位记忆"""

    conditions = ["1=1"]
    params = []

    if memory_type:
        conditions.append("memory_type = ?")
        params.append(memory_type)

    if event_id:
        conditions.append(
            "id IN (SELECT memory_id FROM memory_events WHERE event_id = ?)"
        )
        params.append(event_id)

    if time_from:
        conditions.append("created_at >= ?")
        params.append(time_from)
    if time_to:
        conditions.append("created_at <= ?")
        params.append(time_to)

    if keyword:
        conditions.append(
            "(summary LIKE ? OR content LIKE ?)"
        )
        params.append(f"%{keyword}%")
        params.append(f"%{keyword}%")

    where_clause = " AND ".join(conditions)

    order_clause = {
        "time_desc": "created_at DESC",
        "time_asc": "created_at ASC",
        "mass_desc": "node_mass DESC",
    }.get(sort_by, "created_at DESC")

    rows = conn_module.db.fetchall(
        f"SELECT * FROM memories WHERE {where_clause} ORDER BY {order_clause} LIMIT ?",
        tuple(params + [min(limit, 20)]),
    )

    # 总计数
    count_row = conn_module.db.fetchone(
        f"SELECT COUNT(*) as cnt FROM memories WHERE {where_clause}",
        tuple(params),
    )

    memories = []
    for row in rows:
        mem = MemoryNode.from_row(row)
        r = _compute_r(mem.created_at)
        # 获取事件名
        event_rows = conn_module.db.fetchall(
            """SELECT e.name FROM events e
               JOIN memory_events me ON e.id = me.event_id
               WHERE me.memory_id = ?""",
            (mem.id,),
        )
        event_names = [e["name"] for e in event_rows]
        memories.append({
            "memory_id": mem.id,
            "summary": mem.summary or mem.content[:100],
            "content": mem.content,
            "coordinate": {"r": round(r, 4), "phi": round(mem.phi, 4), "theta": round(mem.theta, 4)},
            "node_mass": round(mem.node_mass, 4),
            "created_at": mem.created_at,
            "event_names": event_names,
            "source_uri": mem.source_uri,
        })

    return {
        "memories": memories,
        "total_count": count_row["cnt"] if count_row else 0,
    }


def recall_by_gravity(
    query: str,
    query_tags: list[str],
    max_activations: int = 8,
    gravity_threshold: float = 0.6,
    memory_type_filter: list[str] | None = None,
    time_range: dict | None = None,
    depth: int = 2,
) -> dict:
    """
    引力联想检索 --- 从入口节点沿引力链接扩散，激活相关记忆。
    这是整个插件最核心的差异化能力。
    """

    # ---------- 冷启动降级 ----------
    total = conn_module.db.fetchone("SELECT COUNT(*) as cnt FROM memories")
    if total and total["cnt"] < CONFIG.cold_start_threshold:
        from_ts = None
        to_ts = None
        if time_range:
            from_ts = time_range.get("from")
            to_ts = time_range.get("to")
        return _wrap_cold_start(recall_by_coordinate(
            memory_type=memory_type_filter[0] if memory_type_filter else None,
            keyword=query_tags[0] if query_tags else query,
            time_from=from_ts,
            time_to=to_ts,
            limit=max_activations,
        ))

    # ---------- 1. 定位入口节点 ----------
    from_ts = None
    to_ts = None
    if time_range:
        from_ts = time_range.get("from")
        to_ts = time_range.get("to")

    entries = _find_entry_points(
        query_tags, memory_type_filter, from_ts, to_ts, top_n=3
    )

    # 无入口时回退到坐标查询
    if not entries:
        return _wrap_cold_start(recall_by_coordinate(
            keyword=query_tags[0] if query_tags else query,
            limit=max_activations,
        ))

    # 选 node_mass 最高的作为入口
    entry = max(entries, key=lambda m: m.node_mass)

    # ---------- 2. BFS 扩散 ----------
    max_activations = min(max_activations, CONFIG.default_max_activations)
    depth = min(depth, CONFIG.max_diffusion_depth)

    queue: list[tuple[str, float, list[str]]] = [
        (entry.id, 1.0, [entry.id])
    ]
    activated: dict[str, dict] = {
        entry.id: {
            "gravity": 1.0,
            "path": [entry.id],
            "link_types": [],
        }
    }

    while queue and len(activated) < max_activations:
        current_id, incoming_gravity, path = queue.pop(0)
        if len(path) > depth:
            continue

        neighbors = get_neighbor_links(current_id, threshold=gravity_threshold, limit=5)

        for link in neighbors:
            neighbor_id = link.other_end(current_id)
            effective_gravity = incoming_gravity * link.gravity_strength

            if effective_gravity < gravity_threshold:
                continue
            if neighbor_id in activated and activated[neighbor_id]["gravity"] >= effective_gravity:
                continue
            if neighbor_id == entry.id:
                continue

            new_path = path + [neighbor_id]
            activated[neighbor_id] = {
                "gravity": effective_gravity,
                "path": new_path,
                "link_types": _link_type_labels(link),
            }
            queue.append((neighbor_id, effective_gravity, new_path))

    # ---------- 3. 排序并返回 ----------
    sorted_activated = sorted(
        activated.items(), key=lambda x: x[1]["gravity"], reverse=True
    )[:max_activations]

    # 更新激活计数
    for mem_id, _ in sorted_activated:
        increment_activation(mem_id)
    increment_activation(entry.id)

    activated_memories = []
    for mem_id, info in sorted_activated:
        mem = get_memory(mem_id)
        if not mem:
            continue
        r = _compute_r(mem.created_at)
        activated_memories.append({
            "memory_id": mem.id,
            "summary": mem.summary or mem.content[:100],
            "content": mem.content,
            "coordinate": {"r": round(r, 4), "phi": round(mem.phi, 4), "theta": round(mem.theta, 4)},
            "node_mass": round(mem.node_mass, 4),
            "gravity_strength": round(info["gravity"], 4),
            "activation_path": info["path"],
            "link_types": info["link_types"],
            "source_uri": mem.source_uri,
        })

    return {
        "entry_point": {
            "memory_id": entry.id,
            "summary": entry.summary or entry.content[:100],
            "node_mass": round(entry.node_mass, 4),
        },
        "activated_memories": activated_memories,
        "activation_stats": {
            "total_candidates": len(activated),
            "activated_count": len(activated_memories),
            "avg_gravity": round(
                sum(m["gravity_strength"] for m in activated_memories) / len(activated_memories),
                4,
            ) if activated_memories else 0.0,
        },
    }


def _link_type_labels(link: GravityLink) -> list[str]:
    """将引力链接各分量转为标签列表"""
    labels = []
    if link.semantic_similarity > 0.3:
        labels.append("semantic")
    if link.emotion_resonance > 0.3:
        labels.append("emotion")
    if link.causal_relation > 0.3:
        labels.append("causal")
    if not labels:
        labels.append("semantic")
    return labels
