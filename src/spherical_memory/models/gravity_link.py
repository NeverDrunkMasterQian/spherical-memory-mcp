"""GravityLink 数据模型"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class GravityLink:
    """引力链接 --- 记忆节点之间的双边吸引关系"""

    source_id: str
    target_id: str
    gravity_strength: float
    semantic_similarity: float = 0.0
    emotion_resonance: float = 0.0
    causal_relation: float = 0.0
    is_auto_generated: bool = True
    link_sources: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def __post_init__(self):
        # 强制保持 source_id < target_id（无向边）
        if self.source_id > self.target_id:
            self.source_id, self.target_id = self.target_id, self.source_id

    @staticmethod
    def from_row(row) -> "GravityLink":
        import json
        sources = row["link_sources"] or "[]"
        try:
            sources_list = json.loads(sources)
        except (json.JSONDecodeError, TypeError):
            sources_list = []
        return GravityLink(
            id=row["id"],
            source_id=row["source_id"],
            target_id=row["target_id"],
            gravity_strength=row["gravity_strength"],
            semantic_similarity=row["semantic_similarity"],
            emotion_resonance=row["emotion_resonance"],
            causal_relation=row["causal_relation"],
            is_auto_generated=bool(row["is_auto_generated"]),
            link_sources=sources_list,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def other_end(self, memory_id: str) -> str:
        """给定一端，返回另一端"""
        if memory_id == self.source_id:
            return self.target_id
        if memory_id == self.target_id:
            return self.source_id
        raise ValueError(f"memory_id {memory_id} not in link {self.id}")
