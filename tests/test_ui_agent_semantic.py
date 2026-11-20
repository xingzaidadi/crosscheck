from core.ui_agent.semantic import equivalent


def test_semantic_aliases_match_common_ui_language():
    assert equivalent("处理中", "待处理")
    assert equivalent("订单明细", "详情页")
    assert equivalent("Search", "查询")
    assert not equivalent("删除", "详情")
