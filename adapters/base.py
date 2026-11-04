"""适配器基类:提供知识库注入等公共能力,具体操作由子类实现。"""
from __future__ import annotations

from core.interfaces import Adapter
from core.knowledge import KnowledgeBase


class BaseAdapter(Adapter):
    def __init__(self, kb: KnowledgeBase):
        self.kb = kb
