"""衰减机制单元测试"""

from spherical_memory.db import connection as conn_module
from spherical_memory.services.memory_service import store_memory, get_memory
from spherical_memory.services.decay_service import decay_memories, try_awaken


def test_decay_reduces_mass(temp_db):
    """测试衰减降低节点质量"""
    result = store_memory(
        content="一些不太重要的日常闲聊",
        memory_type="life",
        semantic_tags=["闲聊", "日常"],
        personality_match=0.3,
    )
    mem_before = get_memory(result["memory_id"])
    original_mass = mem_before.node_mass

    decay_result = decay_memories(decay_rate=0.5, batch_size=100)
    assert decay_result["memories_decayed"] >= 1

    mem_after = get_memory(result["memory_id"])
    assert mem_after.node_mass < original_mass


def test_core_memory_exempt_from_decay(temp_db):
    """测试核心记忆（mass=1.0）不受衰减影响 — 手动设置 mass=1.0"""
    result = store_memory(
        content="这是我最核心的人格记忆——永远不能忘记",
        memory_type="emotion",
        semantic_tags=["核心", "人格"],
        personality_match=1.0,
        emotion_intensity=1.0,
    )
    # 手动设置 mass 为 1.0（核心记忆）
    conn_module.db.execute(
        "UPDATE memories SET node_mass = 1.0 WHERE id = ?",
        (result["memory_id"],),
    )

    mem = get_memory(result["memory_id"])
    assert mem.node_mass == 1.0

    decay_memories(decay_rate=0.5, batch_size=100)
    mem_after = get_memory(result["memory_id"])

    # mass=1.0 的核心记忆不应衰减
    assert mem_after.node_mass == 1.0


def test_awaken_sunken_memory(temp_db):
    """测试强引力唤醒沉降记忆"""
    result = store_memory(
        content="很久以前的记忆，已经沉睡了",
        memory_type="life",
        semantic_tags=["过去的", "沉睡"],
    )

    # 手动设置低质量
    conn_module.db.execute(
        "UPDATE memories SET node_mass = 0.05 WHERE id = ?",
        (result["memory_id"],),
    )

    row = conn_module.db.fetchone("SELECT id FROM memories WHERE node_mass < 0.1")
    assert row is not None

    awakened = try_awaken(row["id"], effective_gravity=0.85)
    assert awakened is True

    mem_after = get_memory(row["id"])
    assert mem_after.node_mass == 0.3  # 部分恢复
