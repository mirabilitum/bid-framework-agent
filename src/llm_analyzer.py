# -*- coding: utf-8 -*-
"""
LLM Analyzer
Sends the procurement document text (+ optional page screenshots) to an LLM
and returns structured analysis JSON.
"""

import os
import json
from typing import Dict, Any, List, Optional

from .llm_provider import BaseLLMProvider


class LLMAnalyzer:
    """Analyze procurement documents with LLM to extract structured info."""

    def __init__(self, llm_provider: BaseLLMProvider):
        self.llm = llm_provider
        self.prompt_template = self._load_prompt()

    def _load_prompt(self) -> str:
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts", "analyze_prompt.txt")
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def analyze(
        self,
        document_text: str,
        tables: Optional[List[List[List[str]]]] = None,
        format_page_images: Optional[List[dict]] = None,
    ) -> Dict[str, Any]:
        """
        Analyze a procurement document.

        Args:
            document_text: Full extracted text
            tables: Extracted tables (list of row-lists)
            format_page_images: Page screenshots for vision-based format detection

        Returns:
            Structured dict with project_info, packages, scoring_factors,
            response_format, requirements, etc.
        """
        tables_text = self._format_tables(tables) if tables else "无表格"

        # Truncate very long documents to stay within context limits
        max_chars = 30_000
        if len(document_text) > max_chars:
            document_text = document_text[:max_chars] + "\n\n...(文档过长，已截断)..."

        prompt = self.prompt_template.format(document_text=document_text, tables_text=tables_text)

        if format_page_images:
            prompt += (
                f"\n\n# 截图说明\n\n"
                f"共附带 {len(format_page_images)} 张格式模板页面截图，按页码顺序排列。"
                f"请根据截图判断格式。\n"
            )

        print(f"  Sending to LLM ({len(document_text)} chars, {len(tables or [])} tables, "
              f"{len(format_page_images or [])} images) ...")

        raw = (
            self.llm.generate_with_images(prompt, images=format_page_images, max_tokens=8192)
            if format_page_images
            else self.llm.generate(prompt, max_tokens=4096)
        )

        result = self._parse_json(raw)
        self._validate(result)

        print(f"  Project : {result['project_info']['name']}")
        print(f"  Packages: {len(result['packages'])}")
        print(f"  Scoring : {len(result['scoring_factors'])} factor(s)")
        return result

    # -- helpers --

    @staticmethod
    def _format_tables(tables: List[List[List[str]]]) -> str:
        parts = []
        for i, table in enumerate(tables[:10]):
            parts.append(f"\n表格 {i + 1}:")
            for row in table:
                parts.append(" | ".join(str(c) for c in row))
            parts.append("")
        if len(tables) > 10:
            parts.append(f"\n... 还有 {len(tables) - 10} 个表格未显示")
        return "\n".join(parts)

    @staticmethod
    def _parse_json(raw: str) -> dict:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start < 0 or end <= start:
            raise ValueError("No JSON object found in LLM response")
        return json.loads(raw[start:end])

    @staticmethod
    def _validate(result: dict) -> None:
        for key in ("project_info", "packages", "scoring_factors", "response_format", "requirements"):
            if key not in result:
                raise ValueError(f"Missing required key: {key}")
        for factor in result["scoring_factors"]:
            if not all(k in factor for k in ("name", "score", "category")):
                raise ValueError(f"Invalid scoring factor: {factor}")
