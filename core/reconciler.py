"""
核对器:接口返回 vs 数据库,当场对账。

两步:
  1. 数量核对:接口各分组数量  vs  SQL COUNT(DISTINCT pk) 按同字段分组。
  2. 字段抽样:从接口结果取 N 条,按 pk 查库,逐字段比对值。

输出"一致 / 不一致 + 差在哪条哪个字段",用这个结果判断接口结果是否可信。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.query_mapper import QueryMapper
from db.client import DbClient


@dataclass
class ReconcileResult:
    consistent: bool
    count_diffs: list[str] = field(default_factory=list)   # 分组数量不一致明细
    field_diffs: list[str] = field(default_factory=list)   # 字段抽样不一致明细
    checked_groups: int = 0
    checked_rows: int = 0
    feature: str = ""                                       # 功能名,用于渲染标题

    def render(self) -> str:
        head = "一致 ✅" if self.consistent else "不一致 ❌"
        label = f"{self.feature}核对" if self.feature else "核对"
        lines = [f"[{label}] {head}  (分组 {self.checked_groups}，抽样行 {self.checked_rows})"]
        for d in self.count_diffs:
            lines.append(f"  数量差异: {d}")
        for d in self.field_diffs:
            lines.append(f"  字段差异: {d}")
        return "\n".join(lines)


class Reconciler:
    def __init__(self, db: DbClient, mapping: dict[str, Any]):
        self.db = db
        self.mapping = mapping
        self.mapper = QueryMapper(mapping)
        self.table = mapping["table"]
        self.pk = mapping["pk"]
        # 接口返回的行字段名 → 库列名。接口常用 camelCase(如 itemId/itemName),
        # 库是 snake_case(id/name),名字对不上就比不了,所以必须显式映射。
        self.response_field_map: dict[str, str] = mapping.get("response_field_map", {})

    def reconcile(self, api_params: dict[str, Any], api_response: dict[str, Any]) -> ReconcileResult:
        result = ReconcileResult(consistent=True, feature=self.mapping.get("feature", ""))
        where = self.mapper.build_where(api_params)
        from_clause = self.mapper.from_clause
        pk_ref = self.mapper.pk_ref

        # ── 1. 分组数量核对 ──
        gcfg = self.mapping.get("group_by")
        if gcfg:
            api_groups = self._extract_groups(api_response, gcfg)
            col = gcfg["sql_group_column"]
            sql = (
                f"SELECT {col} AS gkey, COUNT(DISTINCT {pk_ref}) AS c "
                f"FROM {from_clause} WHERE {where.sql} GROUP BY {col}"
            )
            db_rows = self.db.query(sql, where.params)
            db_groups = {str(r["gkey"]): int(r["c"]) for r in db_rows}
            result.checked_groups = len(api_groups)

            for gkey, api_count in api_groups.items():
                db_count = db_groups.get(str(gkey), 0)
                if api_count != db_count:
                    result.consistent = False
                    result.count_diffs.append(
                        f"分组 {gkey}: 接口={api_count} vs 库={db_count} (差 {api_count - db_count})"
                    )

        # ── 1b. 总数核对(无分组的检索接口,如 data.total vs COUNT(DISTINCT pk)) ──
        tcfg = self.mapping.get("total_check")
        if tcfg:
            api_total = self._dig(api_response, tcfg["response_path"])
            sql = f"SELECT COUNT(DISTINCT {pk_ref}) AS c FROM {from_clause} WHERE {where.sql}"
            db_total = int(self.db.query(sql, where.params)[0]["c"])
            result.checked_groups = max(result.checked_groups, 1)
            if api_total is None:
                result.consistent = False
                result.count_diffs.append(f"接口返回缺总数字段 {tcfg['response_path']}")
            elif int(api_total) != db_total:
                result.consistent = False
                result.count_diffs.append(
                    f"总数: 接口={api_total} vs 库={db_total} (差 {int(api_total) - db_total})"
                )

        # ── 2. 字段抽样核对 ──
        # 抽样只需主表的真实行:拿接口返回行的主键值,回主表按 pk 精确查一行,逐字段比值。
        # 接口字段名经 response_field_map 翻译成库列名后再比(如 itemId→id、itemName→name…)。
        fcfg = self.mapping.get("field_sample_check")
        if fcfg:
            rows = self._extract_rows(api_response)[: fcfg.get("sample_size", 5)]
            fields = fcfg.get("compare_fields", [])          # 这里写的是"库列名"
            pk_api_field = self.response_field_map.get(self.pk, self.pk)
            result.checked_rows = len(rows)
            for row in rows:
                pk_val = self._api_value(row, self.pk)
                if pk_val is None:
                    result.field_diffs.append(
                        f"接口行缺主键字段({pk_api_field}),无法比对: {row}")
                    result.consistent = False
                    continue
                db_sql = f"SELECT * FROM {self.table} WHERE {self.pk} = :pk"
                db_row = self.db.query(db_sql, {"pk": pk_val})
                if not db_row:
                    result.consistent = False
                    result.field_diffs.append(f"pk={pk_val}: 接口有,库查不到")
                    continue
                db_row = db_row[0]
                for col in fields:                            # col 是库列名
                    api_v = self._api_value(row, col)
                    db_v = db_row.get(col)
                    if not self._eq(api_v, db_v):
                        result.consistent = False
                        api_field = self.response_field_map.get(col, col)
                        result.field_diffs.append(
                            f"pk={pk_val} 字段 {col}(接口 {api_field}): "
                            f"接口={api_v!r} vs 库={db_v!r}"
                        )
        return result

    def _api_value(self, row: dict, db_column: str) -> Any:
        """按 response_field_map 把库列名翻成接口字段名后,从接口行取值。"""
        api_field = self.response_field_map.get(db_column, db_column)
        return row.get(api_field)

    # ── 解析接口返回(形状由 query_mapping 声明,不写死) ──
    def _extract_groups(self, resp: dict, gcfg: dict) -> dict[str, int]:
        node = self._dig(resp, gcfg["response_path"]) or []
        kf, cf = gcfg["group_key_field"], gcfg["group_count_field"]
        return {str(g[kf]): int(g[cf]) for g in node}

    def _extract_rows(self, resp: dict) -> list[dict]:
        # 约定:结果列表在 data.list / data.rows / data.records 之一
        for path in ("data.list", "data.rows", "data.records", "data"):
            node = self._dig(resp, path)
            if isinstance(node, list):
                return node
        return []

    @staticmethod
    def _dig(obj: Any, dotted: str) -> Any:
        cur = obj
        for part in dotted.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return None
        return cur

    @staticmethod
    def _eq(a: Any, b: Any) -> bool:
        if a is None or b is None:
            return a == b
        # 宽松比对:接口常给字符串,库给数字
        if isinstance(a, (int, float)) or isinstance(b, (int, float)):
            try:
                return float(a) == float(b)
            except (ValueError, TypeError):
                return str(a) == str(b)
        return str(a) == str(b)
