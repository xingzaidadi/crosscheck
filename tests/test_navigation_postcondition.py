"""缺陷2a 回归:导航点击必须验证"到达目标",点了没反应不得判 PASSED。

审计复现:页面只有"订单中心"按钮,点击无任何效果仍停留工作台,旧逻辑返回 PASSED。
本测试锁死后置条件:URL/页面签名都没变 → FAILED;拿不到签名 → INCONCLUSIVE。
纯 helper 测试,不依赖 playwright。
"""
from types import SimpleNamespace

from core.ui_agent.runtime import _navigation_intent, _verify_navigation


def test_navigation_intent_detects_reach_and_record():
    assert _navigation_intent(SimpleNamespace(desired_action={"action": "reach", "target": "订单中心"}))
    assert _navigation_intent(SimpleNamespace(desired_action={"action": "open_first_record"}))
    assert _navigation_intent(SimpleNamespace(desired_action={"action": "click", "target": "查看详情"}))


def test_non_navigation_actions_are_not_nav_intent():
    assert not _navigation_intent(SimpleNamespace(desired_action={"action": "search_value", "value": "x"}))
    assert not _navigation_intent(SimpleNamespace(desired_action={"action": "click", "target": "查询"}))
    assert not _navigation_intent(SimpleNamespace(desired_action=None))


class _FakePage:
    def __init__(self, url, body_len, headings):
        self._url = url
        self._body_len = body_len
        self._headings = headings

    # _verify_navigation 调用 _page_signature(page) 走 page.url / page.locator(...)
    @property
    def url(self):
        return self._url

    def locator(self, selector):
        page = self

        class _Loc:
            def count(self_inner):
                return 1

            def inner_text(self_inner, timeout=0):
                return "x" * page._body_len if "body" in selector else ""

            def all_inner_texts(self_inner):
                return list(page._headings)

        return _Loc()


def test_no_change_after_click_is_failed():
    before = {"url": "http://app/workbench", "body_len": 100, "headings": "工作台"}
    # 点击后完全没变(仍在工作台)
    page = _FakePage("http://app/workbench", 100, ["工作台"])
    verdict = _verify_navigation(page, before)
    assert verdict["status"] == "FAILED"


def test_url_change_is_passed():
    before = {"url": "http://app/workbench", "body_len": 100, "headings": "工作台"}
    page = _FakePage("http://app/orders", 100, ["工作台"])
    assert _verify_navigation(page, before)["status"] == "PASSED"


def test_spa_view_change_is_passed():
    before = {"url": "http://app/home", "body_len": 100, "headings": "工作台"}
    # URL 不变但标题/正文变了(SPA 内切换)
    page = _FakePage("http://app/home", 250, ["订单中心"])
    assert _verify_navigation(page, before)["status"] == "PASSED"


def test_missing_baseline_is_inconclusive():
    page = _FakePage("http://app/home", 100, ["工作台"])
    assert _verify_navigation(page, None)["status"] == "INCONCLUSIVE"
