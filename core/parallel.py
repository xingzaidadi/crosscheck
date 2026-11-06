"""
保序并发池(通用)。workers<=1 退化为顺序执行(默认,等价原行为)。

用途:批量执行里只读(对账)类用例互不影响,可并行提吞吐;写入/UI 类因哨兵快照需要
"库在用例期间安静"而必须串行 —— 调度在 run_batch 里按 mode 切分,这里只提供保序并发原语。
返回结果顺序与输入一致;单项抛异常由 on_error 决定(默认重抛)。
"""
from __future__ import annotations

from typing import Any, Callable, Iterable


def run_pool(items: list, fn: Callable[[Any], Any], workers: int = 1,
             on_error: str = "raise") -> list:
    """对 items 逐个跑 fn,返回与输入同序的结果列表。workers>1 用线程池并发。
    on_error: raise=直接抛;capture=把异常对象放进结果位(不中断其它)。"""
    items = list(items)
    if workers <= 1 or len(items) <= 1:
        out = []
        for x in items:
            try:
                out.append(fn(x))
            except Exception as e:  # noqa: BLE001
                if on_error == "capture":
                    out.append(e)
                else:
                    raise
        return out

    from concurrent.futures import ThreadPoolExecutor, as_completed
    out: list = [None] * len(items)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(fn, x): i for i, x in enumerate(items)}
        for f in as_completed(futs):
            i = futs[f]
            try:
                out[i] = f.result()
            except Exception as e:  # noqa: BLE001
                if on_error == "capture":
                    out[i] = e
                else:
                    raise
    return out
