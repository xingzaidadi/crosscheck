"""通用插件注册表(零业务):把框架的可插拔实现收口到**一处**,一处注册、一处查找。

过去四类扩展点各写各的分发,风格不一(字典 / if-elif / 写死 import / 外部数据):
  case_reader  用例读取器(按文件扩展名分发)        —— 换用例格式不改 core
  login_mode   登录模式(manual / credential / …)     —— 换鉴权方式不改 core
  adapter      操作·感知适配器(api / ui / …)          —— 换驱动方式不改 core(兑现 Adapter ABC 开闭承诺)
  ui_kit       UI 套件选择器预设(数据态)             —— 换前端框架不改 core

现在统一成 kind→key→impl 的三层表:core 启动时登记内置实现;workspace/plugins/*.py
在首次查找时被执行,可追加实现而**不碰框架码**(接入新业务零改框架码)。
各 kind 的 key 语义与 impl 形态由调用方约定(函数 / 工厂 / 数据皆可),registry 只管登记与查找。
"""
from __future__ import annotations

import importlib.util
from typing import Any

_REG: dict[str, dict[str, Any]] = {}
_WS_LOADED = False


def register(kind: str, key: str, impl: Any = None):
    """登记实现。两种用法:
      register("adapter", "api", factory)        直接登记
      @register("case_reader", ".md")            当装饰器(被装饰对象即 impl)
    """
    def _put(obj):
        _REG.setdefault(kind, {})[key] = obj
        return obj
    return _put if impl is None else _put(impl)


def _load_workspace_plugins() -> None:
    """惰性执行 workspace/plugins/*.py(仅一次):让 workspace 用 registry.register 追加实现,
    无需改动 core。无 plugins 目录或个别文件加载失败都不致命(框架照常用内置实现)。"""
    global _WS_LOADED
    if _WS_LOADED:
        return
    _WS_LOADED = True
    try:
        from core.workspace import workspace_root
        pdir = workspace_root() / "plugins"
        if not pdir.is_dir():
            return
        for f in sorted(pdir.glob("*.py")):
            if f.name.startswith("_"):
                continue
            try:
                spec = importlib.util.spec_from_file_location(f"ws_plugin_{f.stem}", f)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)  # 执行即注册(模块体内调 registry.register)
            except Exception:  # noqa: BLE001  单个插件坏了不连累其余
                pass
    except Exception:  # noqa: BLE001
        pass


def get(kind: str, key: str, default: Any = None) -> Any:
    """查实现;无则返回 default(适合有兜底的 kind,如 reader 回退 xlsx)。"""
    _load_workspace_plugins()
    return _REG.get(kind, {}).get(key, default)


def resolve(kind: str, key: str) -> Any:
    """查实现;无则抛错并列出已注册 key(适合无兜底的 kind,如 adapter / login_mode)。"""
    _load_workspace_plugins()
    impl = _REG.get(kind, {}).get(key)
    if impl is None:
        raise KeyError(f"未注册的 {kind}:{key!r}(已注册:{sorted(_REG.get(kind, {}))})")
    return impl


def keys(kind: str) -> list[str]:
    """某 kind 下已注册的 key(可发现性:一处看全某类插件)。"""
    _load_workspace_plugins()
    return sorted(_REG.get(kind, {}))
