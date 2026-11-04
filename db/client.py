"""
DB 访问。只读优先:查询/校验用只读连接;写操作(造数/清理)走独立测试账号连接。

规模化建议:写操作用独立测试账号或接密钥系统 —— 未配妥不开写入类用例,遇到时告警不卡死。
"""
from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


def _engine_from_params(p: dict) -> Engine:
    """
    用显式参数建 MySQL 引擎。密码走 quote_plus 转义后拼 URL,
    避免密码里的特殊字符(- / 等)被 URL 解析吃掉导致 Access denied
    —— 这是真实库上踩过的坑:直接拼明文密码会偶发鉴权失败。
    """
    user = quote_plus(str(p["user"]))
    pwd = quote_plus(str(p["password"]))
    host = p["host"]
    port = p.get("port", 3306)
    db = p["database"]
    driver = p.get("driver", "mysql+pymysql")
    url = f"{driver}://{user}:{pwd}@{host}:{port}/{db}?charset=utf8mb4"
    return create_engine(url, pool_pre_ping=True, pool_recycle=1800)


class DbClient:
    def __init__(
        self,
        dsn_readonly: str | None = None,
        dsn_write: str | None = None,
        *,
        readonly_params: dict | None = None,
        write_params: dict | None = None,
    ):
        """
        两种建连方式:
          - dsn_readonly / dsn_write:直接给 SQLAlchemy URL(sqlite 测试用)。
          - readonly_params / write_params:显式 {host,port,user,password,database}。
            真实 MySQL 用这个,密码特殊字符才不会把鉴权拼坏。
        """
        if readonly_params:
            self._ro: Engine = _engine_from_params(readonly_params)
        elif dsn_readonly:
            self._ro = create_engine(dsn_readonly, pool_pre_ping=True)
        else:
            raise ValueError("必须提供 dsn_readonly 或 readonly_params")

        if write_params:
            self._rw: Engine | None = _engine_from_params(write_params)
        elif dsn_write:
            self._rw = create_engine(dsn_write, pool_pre_ping=True)
        else:
            self._rw = None

    def query(self, sql: str, params: dict | None = None) -> list[dict[str, Any]]:
        """只读查询。校验/快照都走这里。"""
        with self._ro.connect() as conn:
            rows = conn.execute(text(sql), params or {})
            return [dict(r._mapping) for r in rows]

    def count_distinct(self, table: str, pk: str, where: str) -> int:
        """核对用:COUNT(DISTINCT 主键)。"""
        sql = f"SELECT COUNT(DISTINCT {pk}) AS c FROM {table} WHERE {where}"
        return int(self.query(sql)[0]["c"])

    def execute_write(self, sql: str, params: dict | None = None) -> int:
        """写操作(清理造数)。必须走 self._rw(独立测试账号)。"""
        if self._rw is None:
            raise RuntimeError("未配置写连接,拒绝写操作(只读优先)")
        with self._rw.begin() as conn:
            result = conn.execute(text(sql), params or {})
            return result.rowcount

    def columns(self, table: str) -> list[str]:
        """列出表的字段名。自动建模把接口参数往这些列上匹配。"""
        dialect = self._ro.dialect.name
        if dialect == "sqlite":
            rows = self.query(f"PRAGMA table_info({table})")
            return [r["name"] for r in rows]
        # MySQL / 多数库走 INFORMATION_SCHEMA
        rows = self.query(
            "SELECT COLUMN_NAME AS name FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_NAME = :t ORDER BY ORDINAL_POSITION",
            {"t": table},
        )
        return [r["name"] for r in rows]

    def close(self) -> None:
        """释放连接池(测试/关停时调用,避免占用文件句柄)。"""
        self._ro.dispose()
        if self._rw is not None:
            self._rw.dispose()
