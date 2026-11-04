"""
Workspace 路径解析器。框架只放通用代码 + 模板;站点配置、库连接、知识库、抓取样本等
业务数据放在用户自管的 workspace 目录里,与框架解耦。

解析优先级(高 → 低):
  1. set_workspace(path) / 入口脚本的 --workspace 参数
  2. VTA_WORKSPACE 环境变量
  3. ./workspace(仓库根下存在该目录则用)
  4. 仓库根(非破坏性回退:没建 workspace 时老布局继续能跑)
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_workspace: Path | None = None


def set_workspace(path: str | os.PathLike) -> Path:
    """显式设定 workspace(入口脚本解析 --workspace 后、测试里用)。返回解析后的绝对路径。"""
    global _workspace
    _workspace = Path(path).resolve()
    return _workspace


def workspace_root() -> Path:
    """按优先级解析 workspace 根目录。每次调用都重算,便于 set_workspace 即时生效。"""
    if _workspace is not None:
        return _workspace
    env = os.environ.get("VTA_WORKSPACE")
    if env:
        return Path(env).resolve()
    local = REPO_ROOT / "workspace"
    if local.is_dir():
        return local
    return REPO_ROOT


# ── 便捷子目录(全部挂在 workspace 根下) ──
def config_dir() -> Path:
    return workspace_root() / "config"


def profiles_dir() -> Path:
    return workspace_root() / "profiles"


def auth_dir() -> Path:
    return workspace_root() / ".auth"


def kb_dir() -> Path:
    return workspace_root() / "knowledge_base"


def captures_dir() -> Path:
    return workspace_root() / "captures"


def artifacts_dir() -> Path:
    return workspace_root() / "artifacts"


def actions_dir() -> Path:
    return workspace_root() / "actions"


def cases_dir() -> Path:
    return workspace_root() / "cases"
