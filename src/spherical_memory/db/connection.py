"""SQLite 连接管理（WAL 模式，单文件持久化）"""

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from spherical_memory.config import CONFIG


class ConnectionManager:
    """线程安全的 SQLite 连接管理器"""

    def __init__(self, db_path: str | None = None):
        self._db_path = db_path or CONFIG.db_path
        self._local = threading.local()

    def _ensure_dir(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

    def _get_connection(self) -> sqlite3.Connection:
        """获取当前线程的连接（懒创建，首次调用时自动创建目录）"""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._ensure_dir()
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return self._local.conn

    @contextmanager
    def cursor(self) -> Generator[sqlite3.Cursor, None, None]:
        """获取游标的上下文管理器（自动提交/回滚）"""
        conn = self._get_connection()
        cur = conn.cursor()
        try:
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()

    def executescript(self, sql: str) -> None:
        """执行多条 SQL 语句"""
        conn = self._get_connection()
        try:
            conn.executescript(sql)
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def execute(self, sql: str, params: tuple | dict | None = None) -> sqlite3.Cursor:
        """执行单条 SQL 并返回游标"""
        conn = self._get_connection()
        cur = conn.cursor()
        try:
            if params:
                cur.execute(sql, params)
            else:
                cur.execute(sql)
            conn.commit()
            return cur
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()

    def executemany(self, sql: str, params_list: list) -> sqlite3.Cursor:
        """批量执行 SQL"""
        conn = self._get_connection()
        cur = conn.cursor()
        try:
            cur.executemany(sql, params_list)
            conn.commit()
            return cur
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()

    def fetchone(self, sql: str, params: tuple | dict | None = None) -> sqlite3.Row | None:
        """查询单行"""
        with self.cursor() as cur:
            if params:
                cur.execute(sql, params)
            else:
                cur.execute(sql)
            return cur.fetchone()

    def fetchall(self, sql: str, params: tuple | dict | None = None) -> list[sqlite3.Row]:
        """查询多行"""
        with self.cursor() as cur:
            if params:
                cur.execute(sql, params)
            else:
                cur.execute(sql)
            return cur.fetchall()

    def close(self) -> None:
        """关闭当前线程的连接"""
        if hasattr(self._local, "conn") and self._local.conn is not None:
            self._local.conn.close()
            self._local.conn = None


# 全局单例
db = ConnectionManager()
