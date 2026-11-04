"""读取 <workspace>/config/db.yaml、credentials.yaml。真实值不入库(见 .gitignore)。"""
from __future__ import annotations

from typing import Any

import yaml

from core.workspace import config_dir


def _load(name: str) -> dict[str, Any]:
    path = config_dir() / name
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def db_config() -> dict[str, Any]:
    """
    返回 db.yaml 内容。支持两种结构:
      - 老式:{readonly: {dsn}, write: {dsn}}(sqlite 测试)
      - 新式:{databases: {<名>: {host,port,user,password,database}}}(真实多库)
    """
    return _load("db.yaml")


def db_params(name: str) -> dict[str, Any] | None:
    """按库名取显式连接参数(host/port/user/password/database)。没有则 None。"""
    cfg = _load("db.yaml")
    dbs = cfg.get("databases") or {}
    p = dbs.get(name)
    if not p:
        return None
    # 挡掉占位
    if any("TODO" in str(v) for v in p.values()):
        return None
    return p


def readonly_dsn() -> str:
    """兼容老式 sqlite 测试:返回 readonly.dsn。"""
    cfg = _load("db.yaml")
    ro = (cfg.get("readonly") or {}).get("dsn", "")
    return ro if ro and "TODO" not in ro else ""


def credentials() -> dict[str, Any]:
    return _load("credentials.yaml")


def site_credentials(site: str) -> dict[str, Any]:
    """取某站点账号(credentials.yaml 的 sites.<site>)。供 B 模式声明式登录用;没有则空。"""
    cfg = _load("credentials.yaml")
    return (cfg.get("sites") or {}).get(site) or {}
