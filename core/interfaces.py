"""
通用内核的抽象与数据结构 —— 整个框架的架构核心。

这里定义"介质无关"的契约:执行器只依赖这些抽象,不认识 Playwright/HTTP/MQ。
日后换接口测试、批处理测试,只需新增一个 Adapter 实现,内核与下面的数据结构不动。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ───────────────────────── 用例 / 预期数据结构 ─────────────────────────

@dataclass
class DbAssertion:
    """一条数据库断言:按 where 查库,校验行数与字段值。"""
    db: str
    table: str
    where: str
    row_count: int | None = None
    row_count_min: int | None = None   # "至少 N 行"(追加/事件表,行数依配置而定,不宜断精确值)
    fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class Expected:
    """用例预期:页面预期(文案可读) + DB 精确断言 + diff 安全网。"""
    page: list[str] = field(default_factory=list)
    db: list[DbAssertion] = field(default_factory=list)
    allowed_tables: list[str] = field(default_factory=list)  # diff_guard


@dataclass
class TestCase:
    """一条结构化用例。步骤可粗,预期必须可机器判定。"""
    case_id: str
    feature: str
    account_ref: str                       # 指向凭据文件里的账号,不含明文
    data_prep: str | None
    steps: list[str]
    expected: Expected
    cleanup: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)  # 原始 yaml,留档


# ───────────────────────── 操作结果 ─────────────────────────

@dataclass
class ActionResult:
    """适配器执行一次操作后的回执。截获提交接口返回放这里。"""
    ok: bool
    api_status: int | None = None          # 截获的提交接口 HTTP 码
    api_body: Any = None                   # 截获的响应体
    page_texts: list[str] = field(default_factory=list)  # 页面可见文案/标志
    error: str | None = None


# ───────────────────────── 适配器抽象(可插拔) ─────────────────────────

class Adapter(ABC):
    """
    操作层 + 感知层的统一契约。

    - PlaywrightAdapter:驱动浏览器,测 UI 逻辑时用
    - ApiAdapter:直接调接口,API-first,能走接口就别开浏览器
    - 日后:MqAdapter / JobAdapter / CliAdapter …… 内核都不用改
    """

    @abstractmethod
    def setup(self, case: TestCase) -> None:
        """准备环境:登录/复用 Session、打开入口等。"""

    @abstractmethod
    def perform(self, case: TestCase, marker: str) -> ActionResult:
        """按知识库回放步骤,用 marker 作为造数唯一标记值。"""

    @abstractmethod
    def teardown(self) -> None:
        """释放资源(关浏览器/关连接)。"""


# ───────────────────────── 判定结果 ─────────────────────────

class Verdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    PARTIAL = "partial"
    BLOCKED = "blocked"
    INVALID_SPEC = "invalid_spec"
    ENV_ERROR = "env_error"   # 登录失败/脏库作废等,不计入功能失败
    ABORTED = "aborted"       # 哨兵发现标记外变化,本次作废重跑
    SKIP = "skip"             # 未建模/未人审/非本期支持 —— 批量跑里透明跳过


@dataclass
class CaseResult:
    case_id: str
    verdict: Verdict
    # 失败时给"预期X vs 实际Y,差在哪字段"
    details: list[str] = field(default_factory=list)
    cleanup_ok: bool = True
    duration_s: float = 0.0
    # 批量报告展示用(可选)
    title: str = ""
    kind: str = ""
    mode: str = ""
    evidence: str = ""     # 截图证据路径,报告里链接
    video: str = ""        # 操作过程录像(webm)路径,报告里内嵌/链接
    report: dict = field(default_factory=dict)  # 结构化证据(做了什么/预期/实际/表/SQL/数据),富报告渲染用
    # 走单对账·执行保真度(全可选,默认空 —— 加法接入,不影响既有构造/判定)
    act_via: str = ""      # 本次实际执行路径:ui | api(空=未判定)
    ui_triggered: bool = False  # 被测写动作是否由页面触发(录到的接口往返里有该写调用)
    fidelity: dict = field(default_factory=dict)  # 打分:{score,grade,dims[...]}
    audit: dict = field(default_factory=dict)     # 审计:声明vs实际/UI触发调用/三源一致/落盘路径
    required_assertions: list[str] = field(default_factory=list)
    executed_assertions: list[str] = field(default_factory=list)
