"""引力计算单元测试"""

import math
import pytest
from spherical_memory.models.memory import MemoryNode
from spherical_memory.services.gravity_service import (
    jaccard_similarity,
    semantic_similarity,
    emotion_resonance,
    sphere_distance,
    compute_gravity,
    EMOTION_AFFINITY,
    EMOTION_INDEX,
)


def test_jaccard_similarity_identical():
    assert jaccard_similarity(["a", "b", "c"], ["a", "b", "c"]) == 1.0


def test_jaccard_similarity_disjoint():
    assert jaccard_similarity(["a", "b"], ["c", "d"]) == 0.0


def test_jaccard_similarity_partial():
    result = jaccard_similarity(["python", "API", "bug"], ["python", "API", "fix"])
    assert result == 2 / 4  # {python, API} / {python, API, bug, fix}


def test_jaccard_similarity_empty():
    assert jaccard_similarity([], []) == 1.0
    assert jaccard_similarity([], ["a"]) == 0.0
    assert jaccard_similarity(["a"], []) == 0.0


def test_emotion_resonance_same():
    mem_a = MemoryNode(
        content="test", memory_type="life",
        emotion_type="joy", emotion_intensity=0.8,
        phi=0.0, theta=0.0,
    )
    mem_b = MemoryNode(
        content="test2", memory_type="life",
        emotion_type="joy", emotion_intensity=0.8,
        phi=0.0, theta=0.0,
    )
    result = emotion_resonance(mem_a, mem_b)
    assert result == 1.0  # 完全相同


def test_emotion_resonance_complementary():
    mem_a = MemoryNode(
        content="test", memory_type="life",
        emotion_type="joy", emotion_intensity=0.5,
        phi=0.0, theta=0.0,
    )
    mem_b = MemoryNode(
        content="test2", memory_type="life",
        emotion_type="sadness", emotion_intensity=0.5,
        phi=0.0, theta=0.0,
    )
    result = emotion_resonance(mem_a, mem_b)
    assert result == 0.7  # joy-sadness 互补对


def test_emotion_affinity_matrix_symmetric():
    """情感亲和矩阵应是对称的"""
    for i in range(9):
        for j in range(i, 9):
            assert EMOTION_AFFINITY[i][j] == EMOTION_AFFINITY[j][i]


def test_sphere_distance_same_node():
    mem = MemoryNode(
        content="test", memory_type="life",
        phi=1.0, theta=0.5, created_at="2025-06-01T00:00:00",
    )
    assert sphere_distance(mem, mem) == 0.0


def test_compute_gravity_range(temp_db):
    """引力值应在 [0, 1] 范围内"""
    mem_a = MemoryNode(
        content="测试对话关于辞职决定", memory_type="discussion",
        emotion_type="fear", emotion_intensity=0.8, node_mass=0.7,
        semantic_tags=["辞职", "职业", "决定", "恐惧"],
        phi=0.0, theta=0.0, created_at="2025-01-01T00:00:00",
    )
    mem_b = MemoryNode(
        content="用户分享找到新工作的喜悦", memory_type="discussion",
        emotion_type="joy", emotion_intensity=0.7, node_mass=0.6,
        semantic_tags=["新工作", "职业", "喜悦", "转行"],
        phi=0.0, theta=0.5, created_at="2025-06-01T00:00:00",
    )
    gravity = compute_gravity(mem_a, mem_b)
    assert 0.0 <= gravity <= 1.0
