"""语义相似度引擎 — 可插拔接口

默认使用 Jaccard 标签重叠（零外部依赖），预留 Embedding 引擎接口。
"""

from abc import ABC, abstractmethod
from spherical_memory.models.memory import MemoryNode


class SimilarityEngine(ABC):
    """语义相似度计算引擎的抽象基类"""

    @abstractmethod
    def compute(self, mem_a: MemoryNode, mem_b: MemoryNode) -> float:
        """计算两条记忆的语义相似度，返回 [0, 1] 的值"""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """引擎名称"""
        ...


class JaccardSimilarityEngine(SimilarityEngine):
    """基于 Jaccard 系数的标签重叠度计算（MVP 默认引擎）

    公式: |tags_A ∩ tags_B| / |tags_A ∪ tags_B|
    零外部依赖，速度极快，但需要标签精确匹配。
    瓶颈: "论文" 和 "学术写作" Jaccard = 0，语义相近但文字不同。
    """

    @property
    def name(self) -> str:
        return "jaccard"

    def compute(self, mem_a: MemoryNode, mem_b: MemoryNode) -> float:
        tags_a = mem_a.semantic_tags
        tags_b = mem_b.semantic_tags
        if not tags_a and not tags_b:
            return 1.0
        if not tags_a or not tags_b:
            return 0.0
        set_a = set(tags_a)
        set_b = set(tags_b)
        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        return intersection / union if union > 0 else 0.0


# 全局引擎实例（可在配置中切换）
_similarity_engine: SimilarityEngine = JaccardSimilarityEngine()


def get_similarity_engine() -> SimilarityEngine:
    return _similarity_engine


def set_similarity_engine(engine: SimilarityEngine) -> None:
    global _similarity_engine
    _similarity_engine = engine
