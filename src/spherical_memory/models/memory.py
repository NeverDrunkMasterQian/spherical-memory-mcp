"""Memory 数据模型"""

import json
import uuid
from dataclasses import dataclass, field
import datetime as dt
from datetime import datetime, timezone


@dataclass
class MemoryNode:
    """记忆节点 -- 球状记忆空间中的基本单元"""

    content: str
    memory_type: str  # coding|creation|discussion|planning|emotion|life|learning
    phi: float = 0.0
    theta: float = 0.0
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # 质量分量
    node_mass: float = 0.5
    personality_match: float = 0.5
    activation_count: int = 0
    event_core_degree: float = 0.3
    emotion_intensity: float = 0.3

    # 情感与语义
    emotion_type: str = "neutral"
    semantic_tags: list[str] = field(default_factory=list)
    sub_type: str | None = None

    # 摘要
    summary: str = ""

    # 文件溯源
    source_uri: str | None = None

    # 时间戳
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_activated: str | None = None
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @staticmethod
    def from_row(row) -> "MemoryNode":
        """从 SQLite Row 构造"""
        tags = row["semantic_tags"] or "[]"
        try:
            tags_list = json.loads(tags)
        except (json.JSONDecodeError, TypeError):
            tags_list = []
        return MemoryNode(
            id=row["id"],
            content=row["content"],
            summary=row["summary"] or "",
            phi=row["phi"],
            theta=row["theta"],
            memory_type=row["memory_type"],
            sub_type=row["sub_type"],
            node_mass=row["node_mass"],
            personality_match=row["personality_match"],
            activation_count=row["activation_count"],
            event_core_degree=row["event_core_degree"],
            emotion_intensity=row["emotion_intensity"],
            emotion_type=row["emotion_type"] or "neutral",
            semantic_tags=tags_list,
            created_at=row["created_at"],
            last_activated=row["last_activated"],
            updated_at=row["updated_at"],
            source_uri=row["source_uri"] if "source_uri" in row.keys() else None,
        )

    def to_dict(self) -> dict:
        d = {
            "memory_id": self.id,
            "summary": self.summary or self.content[:100],
            "content": self.content,
            "memory_type": self.memory_type,
            "sub_type": self.sub_type,
            "node_mass": round(self.node_mass, 4),
            "emotion_type": self.emotion_type,
            "semantic_tags": self.semantic_tags,
            "created_at": self.created_at,
        }
        if self.source_uri:
            d["source_uri"] = self.source_uri
        return d

    def tags_json(self) -> str:
        return json.dumps(self.semantic_tags, ensure_ascii=False)
