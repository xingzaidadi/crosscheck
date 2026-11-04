"""
浏览器适配器(Playwright)。只有"测 UI 逻辑"时才用它;纯落库校验优先走 ApiAdapter。

要点:
- 登录态:storageState 存文件复用;过期/401 按 auth.relogin_on 自动重登一次,仍败判 env_error。
- 回放优先:按 page_model 选择器回放;选择器失效才 AI 自愈并回写知识库。
- 截获提交接口:page.on("response") 抓 submit 接口返回,放进 ActionResult。
- Playwright 为主干,需要 CDP 专有能力再 context.new_cdp_session() drop 下去。
"""
from __future__ import annotations

from adapters.base import BaseAdapter
from core.interfaces import ActionResult, TestCase


class PlaywrightAdapter(BaseAdapter):
    def __init__(self, kb, credentials, headless: bool = True):
        super().__init__(kb)
        self.credentials = credentials       # 账号明文在凭据文件,不入知识库
        self.headless = headless
        self._browser = None
        self._context = None
        self._page = None

    def setup(self, case: TestCase) -> None:
        pm = self.kb.page_model(case.feature)
        auth = pm.get("auth", {})
        # TODO: 启动 chromium;若 session_file 存在则 storage_state 复用,否则 login 并保存
        # TODO: 打开入口 pm["entry"];校验 auth["login_check_selector"] 确认已登录
        _ = auth

    def perform(self, case: TestCase, marker: str) -> ActionResult:
        pm = self.kb.page_model(case.feature)
        # TODO: 注册 page.on("response") 截获 pm["api"] 的返回
        # TODO: 打开 dialog,按 fields 填值(marker 代入唯一字段,如名称)
        # TODO: 回放失败(选择器失效)→ 触发 AI 自愈 → 更新知识库 → 重试一次
        # TODO: 点 submit;按 success_indicator 读页面标志 → page_texts
        _ = (pm, marker)
        return ActionResult(ok=False, error="TODO: PlaywrightAdapter.perform 未实现")

    def teardown(self) -> None:
        # TODO: close context / browser
        ...
