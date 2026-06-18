"""共享测试夹具"""

import os
import tempfile
import pytest
from spherical_memory.config import MemoryConfig
from spherical_memory.db.connection import ConnectionManager
from spherical_memory.db.schema import init_db


@pytest.fixture
def temp_db():
    """创建临时数据库进行测试"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    config = MemoryConfig(db_path=path)
    import spherical_memory.db.connection as conn_module
    import spherical_memory.config as cfg_module

    old_db = conn_module.db
    old_config = cfg_module.CONFIG

    conn_module.db = ConnectionManager(db_path=path)
    cfg_module.CONFIG = config
    init_db()

    yield path

    conn_module.db.close()
    conn_module.db = old_db
    cfg_module.CONFIG = old_config
    os.unlink(path)
