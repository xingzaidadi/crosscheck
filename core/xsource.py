"""
跨源不变式对账(通用):用于『服务派生视图』类列表——列表由后端服务按派生状态
(如受理台的 acceptStatus)过滤,无单一 DB 列可做行数对账。这类列表的正确测法不是
"接口 total == SELECT COUNT",而是两条跨源不变式:

  1) 完整性(membership):接口返回的每一行,其主键都能在『记录系统表』中查到——
     不能凭空多出一行(派生视图不该捏造不存在的单据)。
  2) 一致性(consistency):对两边都该有的字段(如状态),接口值 == 库值——
     派生视图展示的字段不能和底表矛盾。

纯函数:喂进 api_rows / db_rows(两个 dict 列表)即可判,离线可测、零业务。
"""
from __future__ import annotations


def reconcile_membership(api_rows: list[dict], db_rows: list[dict], *,
                         key: str, consistency: dict | None = None) -> dict:
    """
    api_rows: 接口返回行;db_rows: 按同一批 key 从记录系统查出的行。
    key: 两边主键字段名(如 'demand_request_code' / 接口侧用 api_key_of 预先对齐)。
    consistency: {api_field: db_field} 需逐行比对一致的字段对(可空,只查完整性)。
    返回 {verdict, total, present, missing, mismatch, detail}。
    """
    db_index = {r.get(key): r for r in db_rows if r.get(key) is not None}
    missing, mismatch = [], []
    for row in api_rows:
        k = row.get(key)
        if k is None or k not in db_index:
            missing.append(k)
            continue
        if consistency:
            dbr = db_index[k]
            for af, dbf in consistency.items():
                if af in row and dbf in dbr and row[af] != dbr[dbf]:
                    mismatch.append({"key": k, "field": af, "api": row[af], "db": dbr[dbf]})
    total = len(api_rows)
    verdict = "PASS" if not missing and not mismatch else "FAIL"
    return {
        "verdict": verdict,
        "total": total,
        "present": total - len(missing),
        "missing": missing,
        "mismatch": mismatch,
        "detail": f"完整性 {total-len(missing)}/{total}" +
                  (f";一致性 {total-len(mismatch)}/{total}" if consistency else ""),
    }


def align_api_rows(api_rows: list[dict], api_key: str, out_key: str) -> list[dict]:
    """把接口行的 key 字段名对齐到库侧名(如 demandRequestCode → demand_request_code)。"""
    out = []
    for r in api_rows:
        d = dict(r)
        if api_key in d:
            d[out_key] = d[api_key]
        out.append(d)
    return out
