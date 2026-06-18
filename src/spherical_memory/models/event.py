"""Event 数据模型"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Event:
    """事件 --- 记忆球状空间中的极角锚点"""

    name: str
    theta: float = 0.0
    parent_id: str | None = None
    depth: int = 0
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @staticmethod
    def from_row(row) -> "Event":
        return Event(
            id=row["id"],
            name=row["name"],
            description=row["description"] or "",
            parent_id=row["parent_id"],
            theta=row["theta"],
            depth=row["depth"],
            created_at=row["created_at"],
        )

    def to_dict(self) -> dict:
        return {
            "event_id": self.id,
            "event_name": self.name,
            "description": self.description,
            "theta": self.theta,
            "parent_id": self.parent_id,
            "depth": self.depth,
            "created_at": self.created_at,
        }
