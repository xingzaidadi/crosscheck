"""
核心:把检索接口的请求参数,按 query_mapping 知识,确定性地翻译成 SQL WHERE 条件。

不让 AI 临场猜。映射规则写在知识库 query_mapping/<feature>.json,人工确认一次。
支持 op: eq / like / in /（可扩展 gt/lt/between），枚举翻译,固定条件。

安全:值一律走 SQLAlchemy 绑定参数(:p0, :p1 …),不做字符串拼接,杜绝注入。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class WhereClause:
    """一段可直接喂给 SQLAlchemy 的 WHERE:sql 用命名占位符,params 是绑定值。"""
    sql: str
    params: dict[str, Any] = field(default_factory=dict)


# "不筛选"哨兵值:这些值表示前端没选该条件,不能进 WHERE(否则会把数据滤空)。
# 真实接口里 -1 / "-1" / 空串 / 空数组都是"全部"的意思。
DEFAULT_SENTINELS: tuple = (None, "", -1, "-1")


class QueryMapper:
    def __init__(self, mapping: dict[str, Any]):
        self.mapping = mapping
        self.param_map: dict[str, dict] = mapping.get("param_map", {})
        self.fixed_where: str = mapping.get("fixed_where", "").strip()
        # 主表 + 可选别名 + 可选关联表(接口的某些隐含过滤往往落在关联表,
        # 单表 WHERE 表达不了,必须 join —— 这是实证得到的结论)。
        self.table: str = mapping.get("table", "")
        self.alias: str = mapping.get("table_alias", "").strip()
        self.pk: str = mapping.get("pk", "id")
        self.joins: list[dict] = mapping.get("joins", []) or []

    @property
    def from_clause(self) -> str:
        """FROM 子句:主表(可带别名)+ 声明的 JOIN。有 join 时数量核对必须 COUNT(DISTINCT pk)。"""
        base = f"{self.table} {self.alias}".strip() if self.alias else self.table
        parts = [base]
        for j in self.joins:
            jtype = (j.get("type") or "JOIN").upper()
            tbl = j["table"]
            al = j.get("alias", "").strip()
            on = j["on"]
            tbl_ref = f"{tbl} {al}".strip() if al else tbl
            parts.append(f"{jtype} {tbl_ref} ON {on}")
        return " ".join(parts)

    @property
    def pk_ref(self) -> str:
        """带别名限定的主键引用(有 join 时避免列名歧义)。"""
        return f"{self.alias}.{self.pk}" if self.alias else self.pk

    @property
    def has_joins(self) -> bool:
        return bool(self.joins)

    def _is_sentinel(self, spec: dict, value: Any) -> bool:
        """判断该值是否"不筛选"。param_map 可用 skip_values 自定义额外哨兵。"""
        if value == [] or value == {}:
            return True
        sentinels = set(DEFAULT_SENTINELS) | set(spec.get("skip_values", []))
        try:
            return value in sentinels
        except TypeError:        # 不可哈希(如 list),上面已处理空容器
            return False

    def build_where(self, api_params: dict[str, Any]) -> WhereClause:
        """接口请求参数 → WHERE。未声明参数、哨兵值均忽略。"""
        conditions: list[str] = []
        params: dict[str, Any] = {}
        i = 0

        if self.fixed_where:
            conditions.append(f"({self.fixed_where})")

        for api_key, raw_value in api_params.items():
            spec = self.param_map.get(api_key)
            if spec is None or self._is_sentinel(spec, raw_value):
                continue  # 未声明或"不筛选",跳过
            col = spec["column"]
            if col == "_SKIP_":
                continue  # 显式声明不参与主表 WHERE(如关联表字段)
            value = self._translate_enum(spec, raw_value)
            op = spec.get("op", "eq")

            if op == "eq":
                key = f"p{i}"; i += 1
                conditions.append(f"{col} = :{key}")
                params[key] = value
            elif op == "like":
                key = f"p{i}"; i += 1
                wrap = spec.get("wrap", "%{v}%")
                conditions.append(f"{col} LIKE :{key}")
                params[key] = wrap.replace("{v}", str(value))
            elif op == "in":
                values = value if isinstance(value, (list, tuple)) else [value]
                keys = []
                for v in values:
                    key = f"p{i}"; i += 1
                    keys.append(f":{key}")
                    params[key] = v
                conditions.append(f"{col} IN ({', '.join(keys)})")
            else:
                raise ValueError(f"query_mapping 不支持的 op: {op}（参数 {api_key}）")

        sql = " AND ".join(conditions) if conditions else "1=1"
        return WhereClause(sql=sql, params=params)

    @staticmethod
    def _translate_enum(spec: dict, value: Any) -> Any:
        table = spec.get("enum_translation")
        if not table:
            return value
        if isinstance(value, (list, tuple)):
            return [table.get(v, v) for v in value]
        return table.get(value, value)

    def unknown_params(self, api_params: dict[str, Any]) -> list[str]:
        """返回接口传了、但 param_map 没声明的参数名（提示知识库待补）。"""
        return [k for k, v in api_params.items()
                if k not in self.param_map and v not in (None, "")]
