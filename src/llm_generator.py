# -*- coding: utf-8 -*-
"""
LLM Framework Generator
Sends analysis results to an LLM and returns a hierarchical framework structure.
"""

import os
import json
from typing import Dict, Any, List
from dataclasses import dataclass, field

from .llm_provider import BaseLLMProvider


@dataclass
class FrameworkNode:
    """A node in the bid framework tree."""
    level: int
    title: str
    content: str = ""
    children: List["FrameworkNode"] = field(default_factory=list)
    cover_page: dict = field(default_factory=dict)
    index_page: dict = field(default_factory=dict)


class LLMFrameworkGenerator:
    """Generate bid response frameworks via LLM."""

    def __init__(self, llm_provider: BaseLLMProvider):
        self.llm = llm_provider
        self.prompt_template = self._load_prompt()

    def _load_prompt(self) -> str:
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts", "generate_prompt.txt")
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def generate(self, analysis: Dict[str, Any], document_text: str = "") -> List[FrameworkNode]:
        """
        Generate framework from analysis result.

        Args:
            analysis: dict from LLMAnalyzer
            document_text: original document text (for reference)

        Returns:
            List of top-level FrameworkNode objects
        """
        max_chars = 10_000
        if len(document_text) > max_chars:
            document_text = document_text[:max_chars] + "\n\n...(文档过长，已截断)..."

        prompt = self.prompt_template.format(
            analysis_json=json.dumps(analysis, ensure_ascii=False, indent=2),
            document_text=document_text or "（原始文档未提供）",
        )

        print("  Sending analysis to LLM for framework generation ...")
        raw = self.llm.generate(prompt, max_tokens=4096)

        data = self._parse_json(raw)
        if "framework" not in data:
            raise ValueError("LLM response missing 'framework' key")

        nodes = self._to_nodes(data["framework"])
        total = sum(self._count(n) for n in nodes)
        print(f"  Top-level: {len(nodes)} | Total nodes: {total}")
        return nodes

    def nodes_to_dict(self, nodes: List[FrameworkNode]) -> dict:
        """Serialise FrameworkNode tree back to a JSON-friendly dict."""
        def _ser(n: FrameworkNode) -> dict:
            d: Dict[str, Any] = {"level": n.level, "title": n.title, "content": n.content, "children": [_ser(c) for c in n.children]}
            if n.cover_page:
                d["cover_page"] = n.cover_page
            if n.index_page:
                d["index_page"] = n.index_page
            return d
        return {"framework": [_ser(n) for n in nodes]}

    # -- helpers --

    @staticmethod
    def _parse_json(raw: str) -> dict:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start < 0 or end <= start:
            raise ValueError("No JSON object found in LLM response")
        return json.loads(raw[start:end])

    @classmethod
    def _to_nodes(cls, items: List[dict]) -> List[FrameworkNode]:
        nodes = []
        for item in items:
            node = FrameworkNode(
                level=item["level"],
                title=item["title"],
                content=item.get("content", ""),
                children=cls._to_nodes(item.get("children", [])),
                cover_page=item.get("cover_page", {}),
                index_page=item.get("index_page", {}),
            )
            nodes.append(node)
        return nodes

    @classmethod
    def _count(cls, node: FrameworkNode) -> int:
        return 1 + sum(cls._count(c) for c in node.children)
