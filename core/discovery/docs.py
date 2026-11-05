"""
文档源(PRD / 技术方案):把 .docx 解成段落并建关键词检索,给自发现提供"业务口径"。
无外部依赖 —— .docx 本质是 zip,正文在 word/document.xml 的 <w:t> 节点(含表格单元格)。
建模期用:按字段/功能关键词检索出相关口径段落,交给人(或 LLM)判断该怎么填/断言。
文档是业务输入,放 <workspace>/docs/;本模块是通用代码。
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def docx_paragraphs(path: str | Path) -> list[str]:
    """解 .docx 为段落文本列表(含表格里的段落,扁平化)。"""
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if n == "word/document.xml" or re.match(r"word/(header|footer)\d*\.xml", n)]
        paras: list[str] = []
        for n in ["word/document.xml"] + [x for x in names if x != "word/document.xml"]:
            try:
                root = ET.fromstring(z.read(n))
            except Exception:  # noqa: BLE001
                continue
            for p in root.iter(_W + "p"):
                t = "".join(node.text for node in p.iter(_W + "t") if node.text).strip()
                if t:
                    paras.append(t)
    return paras


class DocIndex:
    """多份文档的段落索引 + 关键词检索。"""

    def __init__(self, paths: list[str | Path]):
        self.entries: list[tuple[str, str]] = []   # (来源文件, 段落)
        for p in paths:
            name = Path(p).name
            for para in docx_paragraphs(p):
                self.entries.append((name, para))

    def __len__(self) -> int:
        return len(self.entries)

    def search(self, terms: list[str], k: int = 6, context: int = 1) -> list[dict]:
        """按关键词命中数排序返回相关段落(带前后 context 段上下文)。"""
        terms = [t for t in terms if t]
        scored = []
        for i, (src, para) in enumerate(self.entries):
            score = sum(para.count(t) for t in terms)
            if score:
                scored.append((score, i))
        scored.sort(key=lambda x: x[0], reverse=True)
        out = []
        for score, i in scored[:k]:
            lo, hi = max(0, i - context), min(len(self.entries), i + context + 1)
            ctx = " ⏎ ".join(self.entries[j][1] for j in range(lo, hi))
            out.append({"source": self.entries[i][0], "score": score, "text": ctx})
        return out
