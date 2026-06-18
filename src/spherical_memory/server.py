"""
球状网络标签记忆体系 — MCP Server 入口

为任何接入的 MCP 兼容 Agent 提供球状记忆空间能力：
- 三维球坐标记忆存储
- 引力链接与联想检索
- 记忆衰减与唤醒
"""

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from spherical_memory.db.schema import init_db
from spherical_memory.services.event_service import register_event
from spherical_memory.services.memory_service import (
    store_memory,
    get_memory,
    get_memory_stats,
)
from spherical_memory.services.gravity_service import (
    compute_gravity_detailed,
    get_neighbor_links,
    get_link_between,
    _upsert_link,
)
from spherical_memory.services.recall_service import (
    recall_by_gravity,
    recall_by_coordinate,
)
from spherical_memory.services.decay_service import decay_memories
from spherical_memory.services.heartbeat_service import conversation_heartbeat
from spherical_memory.models.memory import MemoryNode
from spherical_memory.models.gravity_link import GravityLink

# ==================== MCP Server 初始化 ====================

mcp = FastMCP(
    "spherical-memory",
    instructions="球状网络标签记忆体系 — 为 Agent 提供空间化记忆能力。记忆不再是无差别的数据，而是存在于三维球坐标空间中的节点，通过关联引力自组织为闭合球状网络。",
)

# ==================== 七项 MCP 工具 ====================


@mcp.tool()
def tool_store_memory(
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
    """存储一条新记忆到球状记忆空间。

    每次对话产生值得记住的信息时调用此工具。应在对话自然停顿点（如完成一个话题时）批量调用，而非逐句调用。

    参数:
        content: 记忆内容全文（必填）
        memory_type: 一级类型（必填）。可选值：coding（编码开发）、creation（内容创作）、discussion（讨论交流）、planning（规划决策）、emotion（情感陪伴）、life（生活记录）、learning（知识学习）
        event_ids: 所属事件ID列表，最多3个。不提供则挂在默认事件上
        personality_match: 此记忆与 Agent 人格核心的匹配度 0-1（可选，默认0.5）。0=与人格无关，1=高度相关
        emotion_intensity: 情感强度 0-1（可选，默认0.3）。0=完全中性，1=极度强烈的情感冲击
        emotion_type: 情感类型（可选，默认neutral）。可选值：joy（喜悦）、sadness（悲伤）、anger（愤怒）、fear（恐惧）、surprise（惊讶）、disgust（厌恶）、trust（信任）、anticipation（期待）、neutral（中性）
        semantic_tags: 语义标签列表（强烈建议提供，3-8个精准关键词）。❌ 不提供会导致引力检索效果极差！标签是引力链接的生命线。推荐：["项目名", "核心概念", "关键实体"]
        summary: 记忆摘要（可选）。不提供则自动截取前100字
        sub_type: 二级子类型（可选）。如 coding.bugfix, creation.writing 等
    """
    return store_memory(
        content=content,
        memory_type=memory_type,
        event_ids=event_ids,
        personality_match=personality_match,
        emotion_intensity=emotion_intensity,
        emotion_type=emotion_type,
        semantic_tags=semantic_tags,
        summary=summary,
        sub_type=sub_type,
    )


@mcp.tool()
def tool_recall_by_gravity(
    query: str,
    query_tags: list[str],
    max_activations: int = 8,
    gravity_threshold: float = 0.6,
    memory_type_filter: list[str] | None = None,
    time_range: dict | None = None,
    depth: int = 2,
) -> dict:
    """【核心工具】引力联想检索 — 从入口节点沿引力链接扩散，激活相关联的记忆。

    这是球状记忆体系最核心的差异化能力。当用户提到某个话题、需要联想回忆、或说"你还记得..."时，优先使用此工具。

    参数:
        query: 查询描述文本（必填）。纯自然语言，如"用户又提到了辞职的想法"
        query_tags: 从 query 中提取的关键标签（必填！）。❌ 必填！MCP Server 无推理能力，必须由你从 query 中提取核心概念作为标签。示例：用户说"我又想辞职了" → 提取 ["辞职", "职业", "决定"]
        max_activations: 最大激活记忆数（可选，默认8，上限8）
        gravity_threshold: 引力阈值（可选，默认0.6）。低于此值的链接不会被激活。需要更宽泛联想时降至0.4，需要精确匹配时升至0.8
        memory_type_filter: 限制记忆类型范围（可选）
        time_range: 时间范围（可选）。格式：{"from": "2025-06-01", "to": "2025-12-31"}
        depth: 引力扩散深度（可选，默认2，上限3）。深度越大召回越多但噪声也越多
    """
    return recall_by_gravity(
        query=query,
        query_tags=query_tags,
        max_activations=max_activations,
        gravity_threshold=gravity_threshold,
        memory_type_filter=memory_type_filter,
        time_range=time_range,
        depth=depth,
    )


@mcp.tool()
def tool_recall_by_coordinate(
    memory_type: str | None = None,
    event_id: str | None = None,
    time_range: dict | None = None,
    keyword: str | None = None,
    limit: int = 10,
    sort_by: str = "time_desc",
) -> dict:
    """坐标精确查询 — 通过时间/类型/事件三轴交叉定位记忆。

    当用户明确指定了时间范围或类型时使用。适合精确查找，不适合联想检索。

    参数:
        memory_type: 精确匹配记忆类型（可选）。可选值同 store_memory
        event_id: 精确匹配事件ID（可选）
        time_range: 时间范围（可选）。格式：{"from": "2025-06-01", "to": "2025-12-31"}
        keyword: 内容关键词（可选），用于全文搜索
        limit: 返回数量上限（可选，默认10，上限20）
        sort_by: 排序方式（可选，默认time_desc）。可选：time_desc（时间倒序）、time_asc（时间正序）、mass_desc（质量降序）
    """
    from_ts = time_range.get("from") if time_range else None
    to_ts = time_range.get("to") if time_range else None
    return recall_by_coordinate(
        memory_type=memory_type,
        event_id=event_id,
        time_from=from_ts,
        time_to=to_ts,
        keyword=keyword,
        limit=limit,
        sort_by=sort_by,
    )


@mcp.tool()
def tool_register_event(
    event_name: str,
    parent_event_id: str | None = None,
    description: str | None = None,
) -> dict:
    """注册一个新事件到事件空间，自动分配极角坐标。

    对话中出现新的项目、任务、话题等独立事件线索时调用。Agent 应主动识别事件边界，而非被动等用户声明。
    例如："我们开始开发一个新功能" → 注册事件"XX功能开发"；"换个话题，聊聊你的童年" → 注册事件"童年回忆"

    参数:
        event_name: 事件名称（必填）。简洁明确，如"川西旅行"、"Python课程开发"、"辞职与转行"
        parent_event_id: 父事件ID（可选）。用于创建子事件
        description: 事件描述（可选）
    """
    return register_event(
        name=event_name,
        parent_id=parent_event_id,
        description=description or "",
    )


@mcp.tool()
def tool_link_memories(
    source_id: str,
    target_id: str,
    link_type: str,
    strength_override: float | None = None,
) -> dict:
    """手动为两条记忆建立引力链接，补充自动计算的不足。

    当你在对话中识别到两条记忆存在明确的深层关联时调用。自动算法遗漏的因果/类比/对照关系，由此工具补充。
    手动建立的链接权重高于自动链接。

    参数:
        source_id: 源记忆ID（必填）
        target_id: 目标记忆ID（必填）
        link_type: 链接类型（必填）。可选：semantic（语义相关）、emotion（情感共鸣）、causal（因果关联）
        strength_override: 手动指定关联因子 0-1（可选）。不提供则自动计算
    """
    mem_a = get_memory(source_id)
    mem_b = get_memory(target_id)
    if not mem_a or not mem_b:
        return {"error": "一条或两条记忆不存在", "source_id": source_id, "target_id": target_id}

    if strength_override is not None:
        factor = strength_override
        sem = 1.0 if link_type == "semantic" else 0.0
        emo = 1.0 if link_type == "emotion" else 0.0
        cau = 1.0 if link_type == "causal" else 0.0
    else:
        detail = compute_gravity_detailed(mem_a, mem_b)
        factor = detail["association_factor"]
        sem = detail["semantic_similarity"]
        emo = detail["emotion_resonance"]
        cau = detail["causal_relation"]

    distance = compute_gravity_detailed(mem_a, mem_b)["distance"]
    gravity = (mem_a.node_mass * mem_b.node_mass) / (distance ** 2 + 0.01) * factor
    gravity = min(gravity, 1.0)

    link = GravityLink(
        source_id=source_id,
        target_id=target_id,
        gravity_strength=gravity,
        semantic_similarity=sem,
        emotion_resonance=emo,
        causal_relation=cau,
        is_auto_generated=False,
        link_sources=[link_type],
    )
    _upsert_link(link)

    return {
        "link_id": link.id,
        "gravity_strength": round(gravity, 4),
        "source_summary": mem_a.summary or mem_a.content[:80],
        "target_summary": mem_b.summary or mem_b.content[:80],
    }


@mcp.tool()
def tool_get_memory_stats(detail_level: str = "summary") -> dict:
    """查看记忆空间的整体状况。

    包含总记忆数、类型分布、大质量节点、最近记忆、衰减状态等。
    在对话开始时了解记忆全景，或用户问"你记得多少东西？"时调用。

    参数:
        detail_level: 详细程度（可选，默认summary）。可选：summary（概要）、detailed（详细）
    """
    return get_memory_stats(detail_level)


@mcp.tool()
def tool_decay_memories(
    decay_rate: float = 0.95,
    batch_size: int = 100,
) -> dict:
    """执行一轮记忆质量衰减（遗忘机制）。

    低质量记忆会沉降但不删除，未来可被强引力链接唤醒。
    建议定期调用（如每24小时或每100轮对话），而非每次对话都调用。

    参数:
        decay_rate: 每轮衰减系数（可选，默认0.95）。0.95表示每条衰减记忆的质量乘以0.95
        batch_size: 每轮处理的记忆数上限（可选，默认100）
    """
    return decay_memories(decay_rate=decay_rate, batch_size=batch_size)


@mcp.tool()
def tool_conversation_heartbeat() -> dict:
    """对话心跳 — 追踪轮次并自动触发记忆固化。

    🫀 每轮对话结束时调用此工具。它会自动统计轮次数，在达到配置的间隔时返回 consolidate=true，提示你应该执行一次记忆固化（批量 store_memory）。

    返回:
        turn_count: 当前总轮次
        consolidate: 是否应该执行记忆固化（批量写入 store_memory）
        turns_since_consolidation: 距上次固化已过轮数
        next_consolidation_at: 下次触发固化的轮次
    """
    return conversation_heartbeat()


# ==================== MCP Resources ====================


@mcp.resource("memory://usage-guide")
def resource_usage_guide() -> str:
    """Agent 使用指南 — 连接时自动获取"""
    return """# 球状网络标签记忆体系 — 使用指南

## 核心理念
记忆不是数据库记录，而是存在于三维球坐标空间中的星云节点。
每条记忆有唯一坐标（时间径向、类型方位角、事件极角），彼此通过关联引力链接。

## 工具使用优先级
1. `tool_store_memory` — 每次有意义交互后存储
2. `tool_register_event` — 识别到新事件线索时主动注册
3. `tool_recall_by_gravity` — **最常用检索**，联想回忆时优先使用
4. `tool_recall_by_coordinate` — 精确时间/类型/事件查询
5. `tool_link_memories` — 发现深层关联时手动建立链接
6. `tool_get_memory_stats` — 了解记忆全景
7. `tool_decay_memories` — 定期衰减（建议每24小时一次）

## 调用节奏
- 对话自然停顿点批量 store_memory，不要逐句存
- 事件边界出现时立即 register_event
- 用户提到任何话题时，先 recall_by_gravity 联想相关记忆
- 🫀 每轮对话结束时必须调用 tool_conversation_heartbeat，当 consolidate=true 时执行批量 store_memory

## 对话心跳（🫀 重要！）
- 每轮对话结束时调用 tool_conversation_heartbeat
- 该工具自动追踪轮次，每隔 N 轮返回 consolidate=true
- consolidate=true 时：回顾本轮对话的关键信息，批量调用 store_memory 写入
- 默认每 3 轮固化一次，可通过环境变量 SM_HEARTBEAT_INTERVAL 调整

## 该存什么
- ✅ 用户分享的重要事实、决定、偏好
- ✅ Agent 做出的关键决策及其理由
- ✅ 有情感价值的互动（用户兴奋/失落/信任流露）
- ✅ 新知识的习得（用户学到了什么）
- ✅ 项目进展的里程碑
- ❌ 日常问候、重复确认、临时性技术细节

## 标签质量（最重要！）
- semantic_tags 是引力检索的生命线
- 每条记忆必须提供 3-8 个精准关键词
- 标签应覆盖：主题、关键实体、核心概念、情感关键词
- 例："用户分享了他辞去大厂工作开始创业的经历" → ["辞职", "创业", "大厂", "职业转型", "勇气"]

## 情感标注
- emotion_type 从9种情感中选择：joy/sadness/anger/fear/surprise/disgust/trust/anticipation/neutral
- emotion_intensity 0-1：日常对话0.2-0.3，重要决定0.5-0.7，极度情感冲击0.8-1.0

## recall_by_gravity 的 query_tags
- 必填！从用户的表述中提取 3-5 个核心概念词
- 例如用户说"我又想辞职了" → ["辞职", "职业", "决定", "不满"]
- 标签质量直接决定入口定位准确度，进而决定联想质量
"""


@mcp.resource("memory://space-overview")
def resource_space_overview() -> str:
    """记忆空间概况 — 连接时自动获取"""
    stats = get_memory_stats("summary")
    return json.dumps(stats, ensure_ascii=False, indent=2)


# ==================== 启动入口 ====================


def main():
    """MCP Server 启动入口"""
    init_db()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
