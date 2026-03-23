# -*- coding: utf-8 -*-
"""
LLM Analyzer (v7 split-prompt version)
Analyzes bidding documents using 3 sequential LLM calls:
  Step 1: Structure extraction (project info, scoring, skeleton, format templates)
  Step 2: Full-text search (scoring factor content retrieval)
  Step 3: Cross-fill mapping (chapter reference → scoring factor children)
"""

import os
import json
from typing import Dict, Any, List, Optional

try:
    from .llm_provider import BaseLLMProvider
    from .json_repair import extract_and_parse_json
    from .llm_utils import call_llm_with_continuation
except ImportError:
    from llm_provider import BaseLLMProvider
    from json_repair import extract_and_parse_json
    from llm_utils import call_llm_with_continuation


class LLMAnalyzer:
    """Analyzes bidding documents using LLM (3-step split prompts)"""

    PROMPT_FILES = [
        "analyze_1_structure.txt",
        "analyze_2_search.txt",
        "analyze_3_mapping.txt",
    ]

    def __init__(self, llm_provider: BaseLLMProvider, base_path: Optional[str] = None):
        self.llm_provider = llm_provider
        self.base_path = base_path
        self._prompts = self._load_prompts()

    def _prompt_dir(self) -> str:
        if self.base_path:
            return os.path.join(self.base_path, "prompts")
        return os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts")

    def _load_prompts(self) -> Dict[str, str]:
        """Load all 3 analysis prompt templates."""
        prompts = {}
        d = self._prompt_dir()
        for fname in self.PROMPT_FILES:
            path = os.path.join(d, fname)
            with open(path, "r", encoding="utf-8") as f:
                prompts[fname] = f.read()
        return prompts

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, document_text: str, tables: Optional[List[List[List[str]]]] = None,
                format_page_images: Optional[List[dict]] = None,
                docx_format_paragraphs: Optional[List[dict]] = None,
                on_progress=None, output_dir: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyze bidding document in 3 LLM steps.

        Returns:
            Dict with project_info, packages, scoring_shared, scoring_factors,
            response_format, scoring_requirements_mapping
        """
        tables_text = self._format_tables(tables) if tables else "无表格"
        format_info = ""
        if docx_format_paragraphs and isinstance(docx_format_paragraphs, list):
            format_info = f"（DOCX文档，已提取 {len(docx_format_paragraphs)} 个格式段落）"

        # Truncate for LLM context
        doc_text = document_text
        max_chars = self.llm_provider.max_input_chars
        if len(doc_text) > max_chars:
            doc_text = doc_text[:max_chars] + "\n\n...(文档过长，已截断)..."

        # Build cached system context (document text + tables).
        # ClaudeProvider caches this across Steps 1-2, saving ~90% input cost.
        system_context = f"# 招标文件全文\n\n{doc_text}\n\n# 表格内容\n\n{tables_text}"
        if format_info:
            system_context += f"\n\n# 格式信息\n\n{format_info}"

        def _save_step(name, data):
            if output_dir:
                path = os.path.join(output_dir, f"analysis_{name}.json")
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

        # --- Step 1: Structure ---
        if on_progress:
            on_progress("分析Step1: 提取项目信息与评分标准...", 1, 6)
        print("  [1/3] Extracting structure (project info, scoring, skeleton)...")

        prompt1 = self._prompts["analyze_1_structure.txt"]
        # Document text is in system_context (cached). Replace placeholder with
        # a short reference so the prompt template still reads coherently but
        # does not duplicate the full document in the user message.
        prompt1 = prompt1.replace("{document_text}", "（见system消息中的招标文件全文）")
        prompt1 = prompt1.replace("{tables_text}", "（见system消息中的表格内容）")
        prompt1 = prompt1.replace("{format_info}", format_info)

        if format_page_images:
            prompt1 += f"\n\n# 截图说明\n共附带 {len(format_page_images)} 张格式模板页面截图。\n"

        resp1 = self._call_llm(prompt1, images=format_page_images, max_tokens=8192,
                                system=system_context)
        structure = extract_and_parse_json(resp1, label="structure")
        _save_step("structure", structure)

        scoring_factors_json = json.dumps(
            structure.get("scoring_factors", []), ensure_ascii=False, indent=2
        )
        print(f"    - scoring_factors: {len(structure.get('scoring_factors', []))} items")

        # --- Step 2: Full-text search ---
        if on_progress:
            on_progress("分析Step2: 全文检索评分因素内容...", 2, 6)
        print("  [2/3] Searching document for scoring factor content...")

        prompt2 = self._prompts["analyze_2_search.txt"]
        prompt2 = prompt2.replace("{document_text}", "（见system消息中的招标文件全文）")
        prompt2 = prompt2.replace("{scoring_factors}", scoring_factors_json)

        try:
            resp2 = self._call_llm(prompt2, max_tokens=16384, max_continuations=5,
                                    system=system_context)
            search_results = extract_and_parse_json(resp2, label="search", expect_array=True)
        except Exception as e:
            print(f"    [WARNING] Step 2 parse failed: {e}. Using empty search results.")
            search_results = []
        _save_step("search", search_results)

        print(f"    - search results: {len(search_results)} items")

        # --- Step 3: Cross-fill mapping ---
        if on_progress:
            on_progress("分析Step3: 交叉填充与孤立需求识别...", 3, 6)
        print("  [3/3] Cross-filling and orphan detection...")

        prompt3 = self._prompts["analyze_3_mapping.txt"]
        prompt3 = prompt3.replace("{scoring_factors}", scoring_factors_json)
        prompt3 = prompt3.replace("{search_results}", json.dumps(search_results, ensure_ascii=False, indent=2))

        try:
            resp3 = self._call_llm(prompt3, max_tokens=8192)
            mapping = extract_and_parse_json(resp3, label="mapping", expect_array=True)
        except Exception as e:
            print(f"    [WARNING] Step 3 parse failed: {e}. Using search_results as mapping.")
            mapping = search_results
        _save_step("mapping", mapping)

        print(f"    - mapping: {len(mapping)} items")

        # --- Merge ---
        result = {
            "project_info": structure.get("project_info", {}),
            "packages": structure.get("packages", []),
            "scoring_shared": structure.get("scoring_shared", False),
            "scoring_factors": structure.get("scoring_factors", []),
            "response_format": structure.get("response_format", {}),
            "scoring_requirements_mapping": mapping,
        }

        # Inject DOCX format paragraphs if provided
        if docx_format_paragraphs:
            self._inject_docx_paragraphs(result, docx_format_paragraphs)

        print("  [OK] Analysis complete (3 steps)")
        return result

    # ------------------------------------------------------------------
    # Format section identification (unchanged)
    # ------------------------------------------------------------------

    def identify_format_section(self, document_text: str, file_ext: str,
                                 page_count: int = 0) -> dict:
        text_preview = document_text[:8000] if len(document_text) > 8000 else document_text
        prompt = f"""请阅读以下招标文件文本，找到"格式模板"章节的位置。

格式模板章节的常见名称：
- 投标文件格式、响应文件格式、电子投标文件格式
- 谈判响应文件格式、磋商响应文件格式
- 附件格式、附件--谈判响应文件格式
- 通常在第六章、第七章、第八章或附件部分

文件类型: {file_ext}
{"总页数: " + str(page_count) if page_count else ""}

请返回JSON格式（只返回JSON，不要其他文字）：
{{
  "found": true/false,
  "section_title": "章节完整标题",
  "start_page": 起始页码(1-based，仅PDF),
  "end_page": 结束页码(1-based，仅PDF),
  "keyword": "用于定位的关键词(仅DOCX)"
}}

如果文档中没有明确的格式模板章节，返回 {{"found": false}}

# 文档文本

{text_preview}"""
        try:
            response = self.llm_provider.generate(prompt, max_tokens=512)
            return extract_and_parse_json(response, label="format_section")
        except Exception as e:
            print(f"  [WARNING] 格式章节识别失败: {str(e)}")
            return {"found": False}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _call_llm(self, prompt: str, images=None, max_tokens: int = 8192,
                   max_continuations: int = 3, system: str = None) -> str:
        return call_llm_with_continuation(
            self.llm_provider, prompt, images=images,
            max_tokens=max_tokens, max_continuations=max_continuations,
            system=system,
        )

    def _inject_docx_paragraphs(self, result: Dict, docx_paras):
        if not docx_paras:
            return
        fmt = result.get("response_format", {})
        if isinstance(docx_paras, list):
            fmt["docx_paragraphs"] = docx_paras
            print(f"    - Injected {len(docx_paras)} format paragraphs")

    def _format_tables(self, tables: List[List[List[str]]]) -> str:
        if not tables:
            return "无表格"
        formatted = []
        for i, table in enumerate(tables):
            formatted.append(f"\n表格 {i+1}:")
            for row in table:
                formatted.append(" | ".join(str(cell) for cell in row))
            formatted.append("")
        return "\n".join(formatted)
