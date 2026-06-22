"""球状网络标签记忆体系 - 全局配置"""

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MemoryConfig:
    """记忆系统配置"""

    # 数据库路径（默认在用户目录下创建）
    db_path: str = field(
        default_factory=lambda: str(
            Path.home() / ".spherical-memory" / "memory.db"
        )
    )

    # ---------- 引力计算 ----------
    # 引力阈值：建立链接的最低引力强度
    link_threshold: float = 0.3
    # 引力阈值：检索激活的最低引力强度
    activation_threshold: float = 0.6
    # 每次 store_memory 最多建立的新链接数
    max_new_links_per_store: int = 10
    # 每次 store_memory 候选集上限
    max_candidates: int = 40

    # ---------- 检索参数 ----------
    # 引力扩散默认深度
    default_diffusion_depth: int = 2
    # 引力扩散最大深度
    max_diffusion_depth: int = 3
    # 默认激活上限
    default_max_activations: int = 8

    # ---------- 遗忘衰减 ----------
    # 每轮衰减系数
    decay_rate: float = 0.95
    # 每轮处理上限
    decay_batch_size: int = 100
    # 沉降层阈值
    sunken_threshold: float = 0.1
    # 强引力唤醒阈值
    awakening_threshold: float = 0.8

    # ---------- 冷启动 ----------
    # 记忆数低于此值，引力检索自动降级
    cold_start_threshold: int = 20
    # 冷启动时放宽的链接阈值
    cold_start_link_threshold: float = 0.2

    # ---------- 关联因子权重 ----------
    # 语义相似度权重（在 association_factor 中）
    semantic_weight: float = 0.5
    # 情感共鸣度权重
    emotion_weight: float = 0.3
    # 因果关联度权重
    causal_weight: float = 0.2

    # ---------- 节点质量权重 ----------
    mass_personality_weight: float = 0.50
    mass_activation_weight: float = 0.25
    mass_event_core_weight: float = 0.15
    mass_emotion_intensity_weight: float = 0.10

    # ---------- 语义相似度引擎 ----------
    # 引擎名称: "jaccard" (默认) | "embedding" (需安装 sentence-transformers)
    similarity_engine: str = "jaccard"

    # ---------- Embedding（可选） ----------
    enable_embedding: bool = False
    embedding_model: str = "BAAI/bge-small-zh-v1.5"

    # ---------- 对话心跳 ----------
    # 每 N 轮触发一次记忆固化
    heartbeat_interval: int = 3

    @classmethod
    def from_env(cls) -> "MemoryConfig":
        """从环境变量加载部分配置"""
        config = cls()
        env_map = {
            "SM_DB_PATH": "db_path",
            "SM_LINK_THRESHOLD": ("link_threshold", float),
            "SM_ACTIVATION_THRESHOLD": ("activation_threshold", float),
            "SM_DECAY_RATE": ("decay_rate", float),
            "SM_HEARTBEAT_INTERVAL": ("heartbeat_interval", int),
            "SM_ENABLE_EMBEDDING": ("enable_embedding", lambda x: x.lower() == "true"),
            "SM_EMBEDDING_MODEL": "embedding_model",
        }
        for env_key, target in env_map.items():
            val = os.environ.get(env_key)
            if val is not None:
                if isinstance(target, tuple):
                    attr, conv = target
                    setattr(config, attr, conv(val))
                else:
                    setattr(config, target, val)
        return config


# 全局默认配置实例
CONFIG = MemoryConfig.from_env()
