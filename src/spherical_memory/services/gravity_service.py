"""引力计算服务 --- 关联引力核心算法"""

import json
import math
import datetime as dt
from datetime import datetime

from spherical_memory.config import CONFIG
import spherical_memory.db.connection as conn_module
from spherical_memory.db.schema import get_meta, set_meta
from spherical_memory.models.memory import MemoryNode
from spherical_memory.models.gravity_link import GravityLink
from spherical_memory.services.similarity import get_similarity_engine

# ==================== 情感亲和矩阵 ====================
EMOTIONS = [
    "joy", "sadness", "anger", "fear",
    "surprise", "disgust", "trust", "anticipation", "neutral"
]
EMOTION_INDEX = {e: i for i, e in enumerate(EMOTIONS)}

# 预定义 9x9 情感亲和矩阵
EMOTION_AFFINITY = [
    #  joy  sad  ang  fea  sur  dis  tru  ant  neu
    [1.0, 0.7, 0.3, 0.3, 0.4, 0.2, 0.5, 0.4, 0.5],  # joy
    [0.7, 1.0, 0.5, 0.4, 0.3, 0.3, 0.3, 0.3, 0.5],  # sadness
    [0.3, 0.5, 1.0, 0.6, 0.3, 0.6, 0.2, 0.3, 0.5],  # anger
    [0.3, 0.4, 0.6, 1.0, 0.5, 0.3, 0.7, 0.4, 0.5],  # fear
    [0.4, 0.3, 0.3, 0.5, 1.0, 0.3, 0.2, 0.5, 0.5],  # surprise
    [0.2, 0.3, 0.6, 0.3, 0.3, 1.0, 0.1, 0.2, 0.5],  # disgust
    [0.5, 0.3, 0.2, 0.7, 0.2, 0.1, 1.0, 0.4, 0.5],  # trust
    [0.4, 0.3, 0.3, 0.4, 0.5, 0.2, 0.4, 1.0, 0.5],  # anticipation
    [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5],  # neutral
]

# ==================== 类型-phi 映射 ====================
TYPE_PHASE = {
    "coding": 0.0,
    "creation": 2 * math.pi / 7,
    "discussion": 4 * math.pi / 7,
    "planning": 6 * math.pi / 7,
    "emotion": 8 * math.pi / 7,
    "life": 10 * math.pi / 7,
    "learning": 12 * math.pi / 7,
}

# 记录每类已有的子类型（用于 phi 偏移）
_subtype_registry: dict[str, dict[str, int]] = {}


def _load_subtype_registry() -> dict[str, dict[str, int]]:
    """从 system_meta 恢复子类型注册表，保证重启后 phi 一致"""
    try:
        raw = get_meta("subtype_registry")
        if raw:
            # JSON keys must be str, restore from parsed dict
            parsed = json.loads(raw)
            return {k: {sk: int(sv) for sk, sv in v.items()} for k, v in parsed.items()}
    except Exception:
        pass
    return {}


def _save_subtype_registry() -> None:
    """将子类型注册表持久化到 system_meta"""
    try:
        set_meta("subtype_registry", json.dumps(_subtype_registry, ensure_ascii=False))
    except Exception:
        pass


def _compute_phi(memory_type: str, sub_type: str | None = None) -> float:
    """计算方位角 phi"""
    base = TYPE_PHASE.get(memory_type, 0.0)
    if not sub_type:
        return base + (2 * math.pi / 14)  # 扇区中心

    if memory_type not in _subtype_registry:
        _subtype_registry[memory_type] = {}

    registry = _subtype_registry[memory_type]
    if sub_type not in registry:
        registry[sub_type] = len(registry) + 1
        _save_subtype_registry()  # 持久化新增子类型

    n = len(registry)
    k = registry[sub_type]
    return base + (k / (n + 1)) * (2 * math.pi / 7)


def _get_time_span() -> tuple[float, float]:
    """获取 earliest_time 和 latest_time，无数据时返回默认值"""
    try:
        et = get_meta("earliest_time")
        lt = get_meta("latest_time")
        if not et or not lt:
            return 0.0, 0.0
        return float(et), float(lt)
    except Exception:
        return 0.0, 0.0


def _parse_datetime(dt_str: str) -> datetime:
    """兼容 SQLite 默认格式和 ISO 格式，解析为 UTC 时间"""
    for fmt in (None, "%Y-%m-%d %H:%M:%S"):
        try:
            if fmt:
                d = datetime.strptime(dt_str, fmt)
            else:
                d = datetime.fromisoformat(dt_str)
            # 处理为 UTC（naive datetime 假定为 UTC）
            return d.replace(tzinfo=dt.timezone.utc)
        except (ValueError, TypeError):
            continue
    return datetime.now(dt.timezone.utc)


def _compute_r(created_at_str: str) -> float:
    """根据原始时间戳动态计算归一化 r"""
    et, lt = _get_time_span()
    if et >= lt:
        return 1.0
    ts = _parse_datetime(created_at_str).timestamp()
    return (ts - et) / (lt - et)


def _r_diff(mem_a: MemoryNode, mem_b: MemoryNode) -> float:
    """两个记忆之间的归一化时间差"""
    et, lt = _get_time_span()
    if et >= lt:
        return 0.0
    ts_a = _parse_datetime(mem_a.created_at).timestamp()
    ts_b = _parse_datetime(mem_b.created_at).timestamp()
    return abs(ts_a - ts_b) / (lt - et)


def sphere_distance(mem_a: MemoryNode, mem_b: MemoryNode) -> float:
    """三维球坐标空间距离"""
    r_diff_val = _r_diff(mem_a, mem_b)
    # phi 是环形坐标，取最短弧差
    phi_a = mem_a.phi % (2 * math.pi)
    phi_b = mem_b.phi % (2 * math.pi)
    phi_diff_raw = abs(phi_a - phi_b)
    phi_diff = min(phi_diff_raw, 2 * math.pi - phi_diff_raw)

    theta_a = mem_a.theta % math.pi
    theta_b = mem_b.theta % math.pi
    theta_diff = abs(theta_a - theta_b)

    return math.sqrt(r_diff_val ** 2 + phi_diff ** 2 + theta_diff ** 2)


def jaccard_similarity(tags_a: list[str], tags_b: list[str]) -> float:
    """Jaccard 系数 --- 标签集合重叠度（保留以兼容测试）"""
    from spherical_memory.models.memory import MemoryNode
    # 通过传入仅含 tags 的临时节点调用引擎
    engine = get_similarity_engine()
    mem_a = MemoryNode(content="", memory_type="life", phi=0, theta=0, semantic_tags=list(tags_a))
    mem_b = MemoryNode(content="", memory_type="life", phi=0, theta=0, semantic_tags=list(tags_b))
    return engine.compute(mem_a, mem_b)


def semantic_similarity(mem_a: MemoryNode, mem_b: MemoryNode) -> float:
    """语义相似度：使用当前配置的相似度引擎"""
    return get_similarity_engine().compute(mem_a, mem_b)


def emotion_resonance(mem_a: MemoryNode, mem_b: MemoryNode) -> float:
    """情感共鸣度"""
    idx_a = EMOTION_INDEX.get(mem_a.emotion_type, 8)
    idx_b = EMOTION_INDEX.get(mem_b.emotion_type, 8)
    base_affinity = EMOTION_AFFINITY[idx_a][idx_b]

    min_i = min(mem_a.emotion_intensity, mem_b.emotion_intensity)
    max_i = max(mem_a.emotion_intensity, mem_b.emotion_intensity)
    intensity_factor = min_i / max_i if max_i > 0 else 1.0

    return base_affinity * intensity_factor


def _shared_event_overlap(mem_a: MemoryNode, mem_b: MemoryNode) -> float:
    """两条记忆共享事件的比例"""
    try:
        events_a = conn_module.db.fetchall(
            "SELECT event_id FROM memory_events WHERE memory_id = ?", (mem_a.id,)
        )
        events_b = conn_module.db.fetchall(
            "SELECT event_id FROM memory_events WHERE memory_id = ?", (mem_b.id,)
        )
    except Exception:
        return 0.0
    set_a = {e["event_id"] for e in events_a}
    set_b = {e["event_id"] for e in events_b}
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    shared = len(set_a & set_b)
    min_events = min(len(set_a), len(set_b))
    return shared / min_events if min_events > 0 else 0.0


def causal_relation(mem_a: MemoryNode, mem_b: MemoryNode) -> float:
    """因果关联度"""
    r_diff_val = _r_diff(mem_a, mem_b)
    time_proximity = math.exp(-r_diff_val * 5)
    shared = _shared_event_overlap(mem_a, mem_b)
    return 0.3 * time_proximity + 0.4 * shared
    # explicit_causal_tag 部分由 link_memories 工具补充


def association_factor(mem_a: MemoryNode, mem_b: MemoryNode) -> float:
    """关联因子综合值"""
    sem = semantic_similarity(mem_a, mem_b)
    emo = emotion_resonance(mem_a, mem_b)
    cau = causal_relation(mem_a, mem_b)

    return (
        CONFIG.semantic_weight * sem
        + CONFIG.emotion_weight * emo
        + CONFIG.causal_weight * cau
    )


def compute_gravity(mem_a: MemoryNode, mem_b: MemoryNode) -> float:
    """计算两条记忆之间的引力强度"""
    distance = sphere_distance(mem_a, mem_b)
    factor = association_factor(mem_a, mem_b)
    gravity = (mem_a.node_mass * mem_b.node_mass) / (distance ** 2 + 0.01) * factor
    return min(gravity, 1.0)


def compute_gravity_detailed(
    mem_a: MemoryNode, mem_b: MemoryNode
) -> dict:
    """计算引力并返回各分量详情"""
    distance = sphere_distance(mem_a, mem_b)
    sem = semantic_similarity(mem_a, mem_b)
    emo = emotion_resonance(mem_a, mem_b)
    cau = causal_relation(mem_a, mem_b)
    factor = (
        CONFIG.semantic_weight * sem
        + CONFIG.emotion_weight * emo
        + CONFIG.causal_weight * cau
    )
    gravity = (mem_a.node_mass * mem_b.node_mass) / (distance ** 2 + 0.01) * factor
    return {
        "gravity_strength": min(gravity, 1.0),
        "distance": distance,
        "association_factor": factor,
        "semantic_similarity": sem,
        "emotion_resonance": emo,
        "causal_relation": cau,
    }


def auto_link_new_memory(memory: MemoryNode) -> list[dict]:
    """
    新记忆存入时，自动计算引力并建立链接。
    遵循"近邻优先 + 大质量节点优先"原则。
    """
    total = conn_module.db.fetchone("SELECT COUNT(*) as cnt FROM memories") or {"cnt": 0}
    if total["cnt"] <= 1:
        return []

    # 1. 确定候选集（用有序列表+去重保证确定性）
    link_threshold = CONFIG.link_threshold
    if total["cnt"] < CONFIG.cold_start_threshold:
        link_threshold = CONFIG.cold_start_link_threshold

    candidates = []
    seen = {memory.id}

    # 同类型记忆 top 20
    for row in conn_module.db.fetchall(
        "SELECT id FROM memories WHERE memory_type = ? AND id != ? "
        "ORDER BY node_mass DESC LIMIT 20",
        (memory.memory_type, memory.id),
    ):
        cid = row["id"]
        if cid not in seen:
            candidates.append(cid)
            seen.add(cid)

    # 同事件记忆 top 10
    for row in conn_module.db.fetchall(
        """SELECT m.id FROM memories m
           JOIN memory_events me ON m.id = me.memory_id
           WHERE me.event_id IN (
               SELECT event_id FROM memory_events WHERE memory_id = ?
           )
           AND m.id != ?
           ORDER BY m.node_mass DESC LIMIT 10""",
        (memory.id, memory.id),
    ):
        cid = row["id"]
        if cid not in seen:
            candidates.append(cid)
            seen.add(cid)

    # 大质量枢纽节点 top 10
    for row in conn_module.db.fetchall(
        "SELECT id FROM memories WHERE id != ? AND node_mass > 0.5 "
        "ORDER BY node_mass DESC LIMIT 10",
        (memory.id,),
    ):
        cid = row["id"]
        if cid not in seen:
            candidates.append(cid)
            seen.add(cid)

    # 去重，取前 CONFIG.max_candidates
    candidate_list = candidates[: CONFIG.max_candidates]

    # 2. 对每个候选计算引力
    links_created = []
    for cand_id in candidate_list:
        cand_row = conn_module.db.fetchone("SELECT * FROM memories WHERE id = ?", (cand_id,))
        if not cand_row:
            continue
        cand = MemoryNode.from_row(cand_row)

        detail = compute_gravity_detailed(memory, cand)
        if detail["gravity_strength"] >= link_threshold:
            link = GravityLink(
                source_id=memory.id,
                target_id=cand.id,
                gravity_strength=detail["gravity_strength"],
                semantic_similarity=detail["semantic_similarity"],
                emotion_resonance=detail["emotion_resonance"],
                causal_relation=detail["causal_relation"],
            )
            _upsert_link(link)
            links_created.append({
                "memory_id": cand.id,
                "summary": cand.summary or cand.content[:80],
                "gravity_strength": round(detail["gravity_strength"], 4),
            })

    # 按引力排序，只保留最相关的结果
    links_created.sort(key=lambda x: x["gravity_strength"], reverse=True)
    return links_created[:10]


def _upsert_link(link: GravityLink) -> None:
    """插入或更新引力链接（无向边）"""
    import json
    import sqlite3
    try:
        conn_module.db.execute(
            """INSERT INTO gravity_links
               (id, source_id, target_id, gravity_strength, semantic_similarity,
                emotion_resonance, causal_relation, is_auto_generated, link_sources)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                link.id, link.source_id, link.target_id,
                link.gravity_strength, link.semantic_similarity,
                link.emotion_resonance, link.causal_relation,
                int(link.is_auto_generated),
                json.dumps(link.link_sources, ensure_ascii=False),
            ),
        )
    except sqlite3.IntegrityError:
        # 链接已存在（UNIQUE 约束冲突），更新引力强度
        conn_module.db.execute(
            """UPDATE gravity_links SET
               gravity_strength = ?, semantic_similarity = ?,
               emotion_resonance = ?, causal_relation = ?,
               updated_at = datetime('now')
               WHERE source_id = ? AND target_id = ?""",
            (
                link.gravity_strength, link.semantic_similarity,
                link.emotion_resonance, link.causal_relation,
                link.source_id, link.target_id,
            ),
        )


def get_neighbor_links(memory_id: str, threshold: float = 0.0, limit: int = 10) -> list[GravityLink]:
    """获取某记忆节点的所有引力邻居"""
    rows = conn_module.db.fetchall(
        """SELECT * FROM gravity_links
           WHERE (source_id = ? OR target_id = ?)
             AND gravity_strength >= ?
           ORDER BY gravity_strength DESC LIMIT ?""",
        (memory_id, memory_id, threshold, limit),
    )
    return [GravityLink.from_row(r) for r in rows]


def get_link_between(a_id: str, b_id: str) -> GravityLink | None:
    """查询两条记忆之间是否存在引力链接"""
    s, t = sorted([a_id, b_id])
    row = conn_module.db.fetchone(
        "SELECT * FROM gravity_links WHERE source_id = ? AND target_id = ?",
        (s, t),
    )
    return GravityLink.from_row(row) if row else None


# 模块加载时从持久化恢复子类型注册表
_subtype_registry = _load_subtype_registry()
