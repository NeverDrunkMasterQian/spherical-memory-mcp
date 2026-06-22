"""记忆存储与检索端到端测试"""

import pytest
from spherical_memory.services.event_service import register_event
from spherical_memory.services.memory_service import store_memory, get_memory, get_memory_stats
from spherical_memory.services.recall_service import recall_by_gravity, recall_by_coordinate


def test_store_and_retrieve_single(temp_db):
    """测试存储单条记忆"""
    result = store_memory(
        content="用户分享了一次难忘的川西旅行经历，提到了贡嘎雪山",
        memory_type="life",
        semantic_tags=["川西", "旅行", "贡嘎雪山", "徒步"],
    )
    assert "memory_id" in result
    assert result["coordinate"]["r"] >= 0.0
    assert result["coordinate"]["r"] <= 1.0
    assert result["node_mass"] > 0.0

    mem = get_memory(result["memory_id"])
    assert mem is not None
    assert "川西" in mem.content


def test_multiple_stores_and_recall(temp_db):
    """测试多条记忆存储后引力检索"""
    # 存储 3 条相关记忆
    store_memory(
        content="用户决定辞去现在的工作，觉得没有成长空间",
        memory_type="discussion",
        semantic_tags=["辞职", "职业", "成长", "决定"],
        emotion_type="fear",
        emotion_intensity=0.7,
        personality_match=0.8,
    )
    store_memory(
        content="用户开始学习编程，报名了在线课程",
        memory_type="learning",
        semantic_tags=["编程", "学习", "在线课程", "转行"],
    )
    store_memory(
        content="用户找到了第一份远程开发工作，非常开心",
        memory_type="life",
        semantic_tags=["远程工作", "开发", "新工作", "喜悦"],
        emotion_type="joy",
        emotion_intensity=0.8,
    )

    # 检查统计
    stats = get_memory_stats()
    assert stats["total_memories"] == 3

    # 引力检索（冷启动降级为坐标查询也可接受）
    result = recall_by_gravity(
        query="用户又提到了辞职的想法",
        query_tags=["辞去", "职业", "决定"],  # 标签匹配第一条记忆的 tags
        gravity_threshold=0.3,
    )
    # 冷启动时降级为坐标查询，检查返回的 activated_memories
    assert len(result["activated_memories"]) >= 1
    assert result.get("_cold_start") is True


def test_coordinate_recall(temp_db):
    """测试坐标检索"""
    store_memory(
        content="写了一篇关于Python装饰器的博客",
        memory_type="creation",
        semantic_tags=["Python", "装饰器", "博客"],
    )
    store_memory(
        content="修复了一个内存泄漏的bug",
        memory_type="coding",
        semantic_tags=["bug", "内存泄漏", "修复"],
    )

    result = recall_by_coordinate(memory_type="creation")
    assert result["total_count"] >= 1

    result2 = recall_by_coordinate(keyword="bug")
    assert result2["total_count"] >= 1


def test_event_creation(temp_db):
    """测试事件注册"""
    event_result = register_event("辞职与转行")
    assert "event_id" in event_result
    assert event_result["theta"] > 0.0

    # 在事件下存储记忆
    mem_result = store_memory(
        content="用户第一次提出辞职想法",
        memory_type="discussion",
        event_ids=[event_result["event_id"]],
        semantic_tags=["辞职", "第一次"],
    )
    assert mem_result["coordinate"]["theta"] == pytest.approx(event_result["theta"], abs=0.001)
