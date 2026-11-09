"""源码图·接口契约自发现(通用、零业务):从 Spring/Java 后端源码读出"接口契约"——
端点(HTTP+路径)、请求 DTO 的字段与校验规则(@NotBlank/@NotNull/@Size/@Max…)、响应类型。

与 dbmap/apimap/sitemap/page_probe 并列,是又一路"自发现":前几路从运行态探(库/流量/页面),
本路从**源码**读。把建模从"抓包/UI 逆向猜 body"升级为"读契约"——body 骨架、必填项、
"该拒"的精确规则都直接来自代码。

纯函数、可注入(喂文本即可测),不认识任何业务:怎么找仓库/哪个上下文前缀由调用方给。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

_MAPPING = re.compile(r'@(Post|Get|Put|Delete|Request)Mapping\(\s*(?:value\s*=\s*)?"([^"]*)"')
_CLASS_MAP = re.compile(r'@RequestMapping\(\s*(?:value\s*=\s*)?"([^"]*)"')
_METHOD_SIG = re.compile(r'public\s+[\w<>,\.\[\]\s]+?\s+(\w+)\s*\(([^;{]*)\)')
_REQ_BODY = re.compile(r'@RequestBody\s+(?:@Valid\s+)?(?:List<\s*(?:@Valid\s+)?)?([A-Z]\w+)')
_VALID_ANN = re.compile(r'@(NotBlank|NotNull|NotEmpty|Size|Max|Min|DecimalMax|DecimalMin|Pattern|Past|Future)(?:\(([^)]*)\))?')
_FIELD = re.compile(r'private\s+([\w<>,\.\[\]]+)\s+(\w+)\s*;')


def norm_path(*parts: str) -> str:
    """拼接并规整 URL 段(去空段、单斜杠),如 ('demand','/api/x','/y') → '/demand/api/x/y'。"""
    segs = []
    for p in parts:
        for s in (p or "").split("/"):
            if s:
                segs.append(s)
    return "/" + "/".join(segs)


def parse_dto_fields(text: str) -> list[dict]:
    """从一个 DTO 源码读字段 + 校验规则。返回 [{name,type,required,rules}]。纯函数。
    注解只在『上一个字段声明到本字段之间』的区间找,避免上一字段的注解泄漏到下一无注解字段。"""
    out = []
    prev_end = 0
    for fm in _FIELD.finditer(text):
        ftype, fname = fm.group(1), fm.group(2)
        gap = text[prev_end: fm.start()]          # 仅本字段上方、上一字段之后的区间
        rules = [{"ann": a.group(1), "arg": (a.group(2) or "").strip()} for a in _VALID_ANN.finditer(gap)]
        required = any(r["ann"] in ("NotBlank", "NotNull", "NotEmpty") for r in rules)
        out.append({"name": fname, "type": ftype, "required": required, "rules": rules})
        prev_end = fm.end()
    return out


def parse_controller(text: str, context: str = "") -> list[dict]:
    """从一个 Controller 源码读端点。返回 [{http,path,method_name,request_dto,response}]。纯函数。"""
    cm = _CLASS_MAP.search(text)
    class_prefix = cm.group(1) if cm else ""
    out = []
    for m in _MAPPING.finditer(text):
        http, path = m.group(1), m.group(2)
        if http == "Request":
            continue
        tail = text[m.end(): m.end() + 600]
        sig = _METHOD_SIG.search(tail)
        if not sig:
            continue
        rb = _REQ_BODY.search(sig.group(2))
        resp = re.search(r'public\s+([\w<>,\.\[\]]+)\s+' + re.escape(sig.group(1)), tail)
        out.append({
            "http": "POST" if http == "Post" else http.upper(),
            "path": norm_path(context, class_prefix, path),
            "method_name": sig.group(1),
            "request_dto": rb.group(1) if rb else None,
            "response": (resp.group(1) if resp else "").strip(),
        })
    return out


def build_contracts(src_root: str | Path, context: str = "", *,
                    reader: Callable[[Path], str] | None = None) -> list[dict]:
    """遍历源码根:每个 *Controller*.java 抽端点,顺 @RequestBody 找 DTO(按类名索引)读字段。
    reader 可注入(默认读盘)便于离线测试。返回端点契约列表。"""
    root = Path(src_root)
    _read = reader or (lambda p: p.read_text(encoding="utf-8", errors="ignore"))
    # DTO 索引:类名→文件(Spring 约定:*/model/req/* 或类名含 Request)
    dto_index: dict[str, Path] = {}
    for f in root.rglob("*.java"):
        if "/model/req" in f.as_posix() or "Request" in f.name:
            dto_index.setdefault(f.stem, f)
    endpoints = []
    for cf in root.rglob("*Controller*.java"):
        try:
            eps = parse_controller(_read(cf), context)
        except Exception:  # noqa: BLE001  单个文件坏了不连累其余
            continue
        for ep in eps:
            dto = ep.get("request_dto")
            ep["fields"] = parse_dto_fields(_read(dto_index[dto])) if dto in dto_index else []
            ep["controller"] = cf.stem
            endpoints.append(ep)
    return endpoints
