"""事件管理服务"""

import math
import spherical_memory.db.connection as conn_module
from spherical_memory.db.schema import get_meta, set_meta
from spherical_memory.models.event import Event


def register_event(name: str, parent_id: str | None = None, description: str = "") -> dict:
    """注册新事件，自动分配极角 theta"""
    # 确定深度与父事件
    depth = 0
    parent_theta = None
    if parent_id:
        parent = conn_module.db.fetchone("SELECT * FROM events WHERE id = ?", (parent_id,))
        if parent:
            depth = parent["depth"] + 1
            parent_theta = parent["theta"]

    # 同级事件重新均匀分配 theta
    if parent_id:
        siblings = conn_module.db.fetchall(
            "SELECT * FROM events WHERE parent_id = ? ORDER BY theta", (parent_id,)
        )
    else:
        siblings = conn_module.db.fetchall(
            "SELECT * FROM events WHERE depth = 0 ORDER BY theta"
        )

    n = len(siblings) + 1
    if parent_theta is not None:
        # 子事件：在父事件附近偏移
        delta = math.pi / (n + 1) * 0.3
        for i, sib in enumerate(siblings):
            child_theta = parent_theta - delta * (n - 1) / 2 + delta * i
            conn_module.db.execute("UPDATE events SET theta = ? WHERE id = ?", (child_theta, sib["id"]))
        # 新子事件 theta
        theta = parent_theta - delta * (n - 1) / 2 + delta * (n - 1)
    else:
        # 顶级事件均匀分布 [0, pi]
        for i, sib in enumerate(siblings):
            child_theta = math.pi * (i + 1) / (n + 1)
            conn_module.db.execute("UPDATE events SET theta = ? WHERE id = ?", (child_theta, sib["id"]))
        theta = math.pi * n / (n + 1)

    event = Event(
        name=name,
        theta=theta,
        parent_id=parent_id,
        depth=depth,
        description=description,
    )
    conn_module.db.execute(
        """INSERT INTO events (id, name, description, parent_id, theta, depth)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (event.id, event.name, event.description, event.parent_id, event.theta, event.depth),
    )

    # 返回同级事件列表
    if parent_id:
        sibling_list = conn_module.db.fetchall(
            "SELECT name FROM events WHERE parent_id = ? AND id != ? ORDER BY theta",
            (parent_id, event.id),
        )
    else:
        sibling_list = conn_module.db.fetchall(
            "SELECT name FROM events WHERE depth = 0 AND id != ? ORDER BY theta",
            (event.id,),
        )
    parent_name = None
    if parent_id:
        p_row = conn_module.db.fetchone("SELECT name FROM events WHERE id = ?", (parent_id,))
        if p_row:
            parent_name = p_row["name"]

    return {
        "event_id": event.id,
        "event_name": event.name,
        "theta": event.theta,
        "parent_event": parent_name,
        "sibling_events": [s["name"] for s in sibling_list],
    }


def get_event(event_id: str) -> Event | None:
    row = conn_module.db.fetchone("SELECT * FROM events WHERE id = ?", (event_id,))
    return Event.from_row(row) if row else None


def list_events(parent_id: str | None = None) -> list[Event]:
    if parent_id:
        rows = conn_module.db.fetchall("SELECT * FROM events WHERE parent_id = ? ORDER BY theta", (parent_id,))
    else:
        rows = conn_module.db.fetchall("SELECT * FROM events WHERE depth = 0 ORDER BY theta")
    return [Event.from_row(r) for r in rows]
