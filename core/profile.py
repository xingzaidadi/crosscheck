"""
Site Profile:把"某个站点"的身份(登录方式 / 基础 URL / 库绑定 / 知识库目录 / 抓取默认值)
从代码里抽出来,放进 <workspace>/profiles/<site>.yaml。换一套页面、换一套库 = 新写一个
profile,内核(抓包/建模/对账)一行不改。这是工具解耦站点身份、走向通用的关键点。

模板见 templates/profile.example.yaml。
账号明文不在 profile 里 —— 放 <workspace>/config/credentials.yaml(不提交),profile 只引字段名。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from core.workspace import auth_dir, profiles_dir


@dataclass
class LoginConfig:
    mode: str = "manual"                     # manual(A 人工登一次) | credential(B 声明式自动登)
    login_url: str = ""
    liveness_url: str | None = None          # 判活打开的页;空则用 base_url
    logged_in_selector: str | None = None    # 该选择器存在即判"已登录";空则看是否被打回 /login
    steps: list[dict] = field(default_factory=list)  # B 模式的声明式填表步骤


@dataclass
class Profile:
    site: str
    base_url: str = ""
    login: LoginConfig = field(default_factory=LoginConfig)
    db_readonly: str | None = None           # 指向 db.yaml 的 databases.<名>
    knowledge_base: str = "knowledge_base"   # 该站点知识库根(可每站点一套)
    defaults: dict[str, Any] = field(default_factory=dict)  # probe 默认目标
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def session_file(self) -> str:
        """登录态按站点隔离:<workspace>/.auth/<site>.json。"""
        return str(auth_dir() / f"{self.site}.json")


def _coerce(data: dict[str, Any], source: Path) -> Profile:
    login_raw = data.get("login") or {}
    login = LoginConfig(
        mode=login_raw.get("mode", "manual"),
        login_url=login_raw.get("login_url", ""),
        liveness_url=login_raw.get("liveness_url"),
        logged_in_selector=login_raw.get("logged_in_selector"),
        steps=login_raw.get("steps") or [],
    )
    db_raw = data.get("db") or {}
    return Profile(
        site=data.get("site") or source.stem,
        base_url=data.get("base_url", ""),
        login=login,
        db_readonly=db_raw.get("readonly"),
        knowledge_base=data.get("knowledge_base", "knowledge_base"),
        defaults=data.get("defaults") or {},
        raw=data,
    )


def load_profile(name_or_path: str) -> Profile:
    """按名(profiles/<名>.yaml)或直接路径加载。"""
    p = Path(name_or_path)
    if p.suffix in (".yaml", ".yml") and p.exists():
        path = p
    else:
        path = profiles_dir() / f"{name_or_path}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"找不到 Site Profile: {path};现有 profile: {list_profiles()}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return _coerce(data, path)


def list_profiles() -> list[str]:
    pdir = profiles_dir()
    if not pdir.exists():
        return []
    return sorted(f.stem for f in pdir.glob("*.yaml") if not f.stem.startswith("_"))
