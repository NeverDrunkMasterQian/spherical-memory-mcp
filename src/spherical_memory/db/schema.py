"""数据库 Schema 定义与初始化"""

import spherical_memory.db.connection as conn_module

SCHEMA_SQL = """
-- ===================== memories 核心记忆节点表 =====================
CREATE TABLE IF NOT EXISTS memories (
    id              TEXT PRIMARY KEY,
    content         TEXT NOT NULL,
    summary         TEXT,

    -- 球坐标：r 不持久化，由 created_at 动态计算
    phi             REAL NOT NULL,
    theta           REAL NOT NULL DEFAULT 0.0,

    -- 记忆类型
    memory_type     TEXT NOT NULL,
    sub_type        TEXT,

    -- 质量系统
    node_mass       REAL NOT NULL DEFAULT 0.5,
    personality_match   REAL NOT NULL DEFAULT 0.5,
    activation_count    INTEGER NOT NULL DEFAULT 0,
    event_core_degree  REAL NOT NULL DEFAULT 0.3,
    emotion_intensity  REAL NOT NULL DEFAULT 0.3,

    -- 情感标签
    emotion_type    TEXT DEFAULT 'neutral',

    -- 语义标签（JSON 数组字符串）
    semantic_tags   TEXT DEFAULT '[]',

    -- 向量嵌入（BLOB，可选）
    embedding       BLOB,

    -- 文件溯源：记录记忆对应的源文件路径
    source_uri      TEXT,

    -- 时间戳
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    last_activated  TEXT,
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ===================== events 事件注册表 =====================
CREATE TABLE IF NOT EXISTS events (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT,
    parent_id       TEXT,
    theta           REAL NOT NULL,
    depth           INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (parent_id) REFERENCES events(id)
);

-- ===================== memory_events 记忆-事件关联表 =====================
CREATE TABLE IF NOT EXISTS memory_events (
    memory_id       TEXT NOT NULL,
    event_id        TEXT NOT NULL,
    is_primary      INTEGER NOT NULL DEFAULT 0,
    core_degree     REAL NOT NULL DEFAULT 0.3,
    PRIMARY KEY (memory_id, event_id),
    FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE,
    FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
);

-- ===================== gravity_links 引力链接表 =====================
CREATE TABLE IF NOT EXISTS gravity_links (
    id                  TEXT PRIMARY KEY,
    source_id           TEXT NOT NULL,
    target_id           TEXT NOT NULL,

    -- 引力强度
    gravity_strength    REAL NOT NULL,

    -- 关联因子分解
    semantic_similarity REAL DEFAULT 0.0,
    emotion_resonance   REAL DEFAULT 0.0,
    causal_relation     REAL DEFAULT 0.0,

    -- 链接元数据
    is_auto_generated   INTEGER NOT NULL DEFAULT 1,
    link_sources        TEXT DEFAULT '[]',

    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now')),

    FOREIGN KEY (source_id) REFERENCES memories(id) ON DELETE CASCADE,
    FOREIGN KEY (target_id) REFERENCES memories(id) ON DELETE CASCADE,

    UNIQUE(source_id, target_id),
    CHECK(source_id < target_id)
);

-- ===================== system_meta 系统元数据 =====================
CREATE TABLE IF NOT EXISTS system_meta (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL,
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ===================== 索引 =====================
CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(memory_type);
CREATE INDEX IF NOT EXISTS idx_memories_subtype ON memories(memory_type, sub_type);
CREATE INDEX IF NOT EXISTS idx_memories_mass ON memories(node_mass DESC);
CREATE INDEX IF NOT EXISTS idx_memories_type_created ON memories(memory_type, created_at);
CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at);
CREATE INDEX IF NOT EXISTS idx_memories_activated ON memories(last_activated);

CREATE INDEX IF NOT EXISTS idx_events_parent ON events(parent_id);
CREATE INDEX IF NOT EXISTS idx_events_theta ON events(theta);

CREATE INDEX IF NOT EXISTS idx_gravity_source ON gravity_links(source_id);
CREATE INDEX IF NOT EXISTS idx_gravity_target ON gravity_links(target_id);
CREATE INDEX IF NOT EXISTS idx_gravity_strength ON gravity_links(gravity_strength DESC);
CREATE INDEX IF NOT EXISTS idx_gravity_source_strength ON gravity_links(source_id, gravity_strength DESC);
CREATE INDEX IF NOT EXISTS idx_gravity_target_strength ON gravity_links(target_id, gravity_strength DESC);

CREATE INDEX IF NOT EXISTS idx_me_memory ON memory_events(memory_id);
CREATE INDEX IF NOT EXISTS idx_me_event ON memory_events(event_id);
CREATE INDEX IF NOT EXISTS idx_me_primary ON memory_events(memory_id, is_primary);
"""

FTS_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    summary, content, content=memories, content_rowid=rowid
);
"""

# 触发器：保持 FTS 索引与 memories 表同步
FTS_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, summary, content) VALUES (new.rowid, new.summary, new.content);
END;

CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, summary, content) VALUES('delete', old.rowid, old.summary, old.content);
END;

CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, summary, content) VALUES('delete', old.rowid, old.summary, old.content);
    INSERT INTO memories_fts(rowid, summary, content) VALUES (new.rowid, new.summary, new.content);
END;
"""


def init_db() -> None:
    """初始化数据库（幂等，可多次调用）"""
    db = conn_module.db
    db.executescript(SCHEMA_SQL)
    # 兼容旧数据库：添加 source_uri 列
    _migrate_add_column(db, "memories", "source_uri", "TEXT")
    # FTS 使用独立 execute 避免事务冲突
    try:
        db.execute(FTS_SQL)
    except Exception:
        pass  # 已存在
    try:
        db.execute(FTS_TRIGGERS)
    except Exception:
        pass


def _migrate_add_column(db, table: str, column: str, col_type: str) -> None:
    """兼容迁移：若列不存在则添加（SQLite 不支持 IF NOT EXISTS for columns）"""
    try:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
    except Exception:
        pass  # 列已存在


def get_meta(key: str) -> str | None:
    """读取元数据"""
    row = conn_module.db.fetchone("SELECT value FROM system_meta WHERE key = ?", (key,))
    return row["value"] if row else None


def set_meta(key: str, value: str) -> None:
    """写入元数据（upsert）"""
    conn_module.db.execute(
        "INSERT INTO system_meta (key, value, updated_at) VALUES (?, ?, datetime('now')) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
        (key, value),
    )
