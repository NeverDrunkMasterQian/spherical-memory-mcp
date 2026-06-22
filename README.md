# 球状网络标签记忆体系 — MCP Server

<!-- mcp-name: io.github.NeverDrunkMasterQian/spherical-memory-mcp -->

一个基于三维球坐标与引力链接的 AI Agent 记忆插件，实现了"球状网络标签记忆体系"论文的核心构想。

任何支持 MCP（Model Context Protocol）的 LLM Agent，接入此插件后即可获得：
- **空间化记忆存储**：每条记忆在闭合球状空间中有唯一的坐标位置
- **引力联想检索**：记忆之间通过语义/情感/因果关联引力自组织为网络
- **类人遗忘机制**：记忆衰减但不删除，可被强关联唤醒
- **🫀 对话心跳**：自动追踪轮次，定时触发记忆固化

---

## 快速开始

### 安装

```bash
# 开发安装（推荐）
git clone <this-repo>
cd spherical-memory-mcp
pip install -e .
```

### 配置到 Agent

#### WorkBuddy

编辑 `~/.workbuddy/mcp.json`：

```json
{
  "mcpServers": {
    "spherical-memory": {
      "command": "/path/to/python",
      "args": ["-m", "spherical_memory.server"],
      "description": "球状网络标签记忆体系"
    }
  }
}
```

然后在连接器管理中启用（需要点击 **信任**）。

#### Claude Desktop

编辑 Claude Desktop 的 MCP 配置：

```json
{
  "mcpServers": {
    "spherical-memory": {
      "command": "python",
      "args": ["-m", "spherical_memory.server"]
    }
  }
}
```

#### 通用 MCP 客户端

任何支持 MCP stdio 协议的客户端，配置 `command` + `args` 同上即可。

---

## 工具总览

| 工具 | 用途 | 调用时机 |
|------|------|----------|
| `tool_store_memory` | 存储记忆节点 | 有意义交互后 |
| `tool_recall_by_gravity` | **引力联想检索** | 用户提及话题时 |
| `tool_recall_by_coordinate` | 坐标精确查询 | 知道时间/类型/事件时 |
| `tool_register_event` | 注册事件锚点 | 新项目/话题出现时 |
| `tool_link_memories` | 手动建立引力链接 | 发现深层关联时 |
| `tool_get_memory_stats` | 查看记忆概况 | 了解记忆全景 |
| `tool_decay_memories` | 执行遗忘衰减 | 每 24 小时 |
| `tool_conversation_heartbeat` | 🫀 对话心跳 | **每轮对话结束时** |

---

## 🫀 对话心跳机制

每个接入此插件的 Agent 应在**每轮对话结束时**调用 `tool_conversation_heartbeat`。

心跳工具自动追踪轮次计数，按配置的间隔（默认每 3 轮）返回 `consolidate: true`。此时 Agent 应回顾本轮对话的关键信息，批量调用 `store_memory` 写入球状空间。

```
对话流程：
  第1轮 → heartbeat → consolidate: false
  第2轮 → heartbeat → consolidate: false
  第3轮 → heartbeat → consolidate: true  ← 批量 store_memory
  第4轮 → heartbeat → consolidate: false
  ...
```

可通过环境变量 `SM_HEARTBEAT_INTERVAL` 调整间隔（默认 3）。

---

## 记忆写入原则

### 该存什么
- ✅ 用户分享的重要事实、决定、偏好
- ✅ Agent 做出的关键决策及其理由
- ✅ 有情感价值的互动
- ✅ 新知识的习得
- ✅ 项目进展的里程碑

### 不该存什么
- ❌ 日常问候、简单确认
- ❌ 重复信息
- ❌ 临时性技术细节

### 标签是引力链接的生命线
每条 `store_memory` 必须提供 **3–8 个精准的 semantic_tags**。标签质量直接决定引力检索效果。
```
"用户决定辞去大厂工作开始创业" → ["辞职", "创业", "大厂", "职业转型", "勇气"]
```

---

## 语义相似度引擎

当前默认使用 **Jaccard 标签重叠**（零外部依赖，速度快），但存在颗粒度瓶颈——语义相近但文字不同的标签（如"论文"vs"学术写作"）Jaccard = 0。

预留了**可插拔引擎接口**（`services/similarity.py`），后续接入 `bge-small-zh` embedding 后，语义相似度将从"精确匹配"升级为"向量余弦"，引力链接质量将质的飞跃。

> ⚠️ **EmbeddingSimilarityEngine 当前尚未实现**（规划中，欢迎贡献）。目前唯一切换方式是替换为其他 `SimilarityEngine` 的实现类。
>
> ```python
> # 未来切换方式（规划中）：
> # from spherical_memory.services.similarity import set_similarity_engine, EmbeddingSimilarityEngine
> # set_similarity_engine(EmbeddingSimilarityEngine(model="BAAI/bge-small-zh-v1.5"))
> ```

---

## 配置项

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `SM_DB_PATH` | `~/.spherical-memory/memory.db` | 数据库路径 |
| `SM_HEARTBEAT_INTERVAL` | 3 | 心跳固化间隔（轮） |
| `SM_LINK_THRESHOLD` | 0.3 | 引力链接建立阈值 |
| `SM_ACTIVATION_THRESHOLD` | 0.6 | 引力检索激活阈值 |
| `SM_DECAY_RATE` | 0.95 | 记忆衰减系数 |
| `SM_ENABLE_EMBEDDING` | false | 是否启用 embedding 引擎 |

---

## 架构

```
src/spherical_memory/
├── server.py              # FastMCP Server 入口，8 个工具注册
├── config.py              # 全局配置
├── db/
│   ├── schema.py          # 5 张表 + 索引
│   └── connection.py      # SQLite 连接管理（WAL 模式）
├── models/
│   ├── memory.py          # MemoryNode
│   ├── event.py           # Event
│   └── gravity_link.py    # GravityLink
└── services/
    ├── memory_service.py  # 记忆 CRUD + 球坐标计算
    ├── event_service.py   # 事件管理
    ├── gravity_service.py # 引力计算 + 链接建立
    ├── recall_service.py  # 引力扩散 + 坐标检索
    ├── decay_service.py   # 质量衰减 + 唤醒
    ├── heartbeat_service.py # 🫀 对话心跳
    └── similarity.py      # 可插拔语义引擎接口
```

---

## 核心理念

Agent的记忆体系，不应当是传统的数据库格式。Agent作为强交互载体，其记忆的录入及读取方式应更类人，这样在双方的交互中才能让自然语言有更高效率。

详见配套论文《球状网络标签记忆体系》。
