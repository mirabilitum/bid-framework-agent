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
import re
from typing import Dict, Any, List, Optional

try:
    from .llm_provider import BaseLLMProvider
    from .json_repair import extract_and_parse_json
    from .llm_utils import call_llm_with_continuation
except ImportError:
    from llm_provider import BaseLLMProvider
    from json_repair import extract_and_parse_json
    from llm_utils import call_llm_with_continuation


def _pre_repair_json(text: str) -> str:
    """Insert missing commas between array/object endings and the next string key.

    Only called as a fallback when initial JSON parsing fails, so false positives
    inside string values are not a concern in practice.
    """
    return re.sub(r'([}\]])([ \t]*\n[ \t]*)(")', r'\1,\2\3', text)


class LLMAnalyzer:
    """Analyzes bidding documents using LLM (4-step split prompts)"""

    PROMPT_FILES = [
        "analyze_0_packages.txt",
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
        """Load all 4 analysis prompt templates."""
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

    def identify_lots(self, document_text: str,
                      tables: Optional[List[List[List[str]]]] = None) -> Dict[str, Any]:
        """
        Lightweight Step 0: identify packages/lots before full analysis.
        Returns lot_info dict with keys: total_lots, lots, lot_ranges.
        Falls back to {"total_lots": 1, "lots": [{"id":"1","name":"单包"}]} on error.
        """
        max_chars = self.llm_provider.max_input_chars
        doc_text = document_text[:max_chars] if len(document_text) > max_chars else document_text
        tables_text = self._format_tables(tables) if tables else ""

        prompt0 = self._prompts["analyze_0_packages.txt"]
        prompt0 = prompt0.replace("{document_text}", doc_text)
        if tables_text and tables_text != "无表格":
            prompt0 += f"\n\n# Extracted Tables\n\n{tables_text}"

        try:
            resp0 = self._call_llm(prompt0, max_tokens=4096)
            try:
                result = extract_and_parse_json(resp0, label="packages_pre") or {}
            except Exception as e1:
                print(f"  [WARNING] identify_lots JSON解析失败: {e1}，尝试修复...", flush=True)
                result = extract_and_parse_json(_pre_repair_json(resp0), label="packages_pre") or {}
            return result
        except Exception as e:
            print(f"  [WARNING] identify_lots failed: {e}. Using single-lot fallback.", flush=True)
            return {"total_lots": 1, "lots": [{"id": "1", "name": "单包"}]}

    def analyze(self, document_text: str, tables: Optional[List[List[List[str]]]] = None,
                format_page_images: Optional[List[dict]] = None,
                docx_format_paragraphs: Optional[List[dict]] = None,
                on_progress=None, output_dir: Optional[str] = None,
                lot_context: Optional[Dict[str, Any]] = None,
                target_package: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Analyze bidding document in up to 4 LLM steps.

        Args:
            lot_context: Pre-identified lot info from identify_lots(). If provided,
                         Step 0 is skipped and this is used directly.
            target_package: Dict with id and name. If provided, analysis is restricted to this package.

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

        pkg_instruction = ""
        if target_package:
            pkg_id = target_package.get("id", "")
            pkg_name = target_package.get("name", "")
            pkg_instruction = f"【重要指令】当前任务仅针对【包编号：{pkg_id}，包名称：{pkg_name}】。请只提取、检索和分析该包的评分标准和格式要求，严格忽略其他所有包的内容。\n\n"

        def _save_step(name, data):
            if output_dir:
                path = os.path.join(output_dir, f"analysis_{name}.json")
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

        # --- Step 0: Package pre-analysis (skipped if lot_context provided) ---
        if lot_context is not None:
            packages_pre = lot_context
            print("  [0/4] Using pre-identified lot context (skipping Step 0).")
            _save_step("packages_pre", packages_pre)
        else:
            if on_progress:
                on_progress("分析Step0: 预分析包/标段信息...", 0, 6)
            print("  [0/4] Pre-analyzing packages/lots...")

            prompt0 = self._prompts["analyze_0_packages.txt"]
            prompt0 = prompt0.replace("{document_text}", doc_text)

            packages_pre = {}
            try:
                resp0 = self._call_llm(prompt0, max_tokens=4096)
                try:
                    packages_pre = extract_and_parse_json(resp0, label="packages_pre") or {}
                except Exception as e1:
                    print(f"    [WARNING] Step 0 JSON解析失败: {e1}，尝试修复...", flush=True)
                    packages_pre = extract_and_parse_json(_pre_repair_json(resp0), label="packages_pre") or {}
            except Exception as e:
                print(f"    [WARNING] Step 0 parse failed: {e}. Skipping pre-analysis.", flush=True)
            _save_step("packages_pre", packages_pre)
            print(f"    - total_lots: {packages_pre.get('total_lots', '?')}")

        # --- Step 1: Structure ---
        if on_progress:
            on_progress("分析Step1: 提取项目信息与评分标准...", 1, 6)
        print("  [1/4] Extracting structure (project info, scoring, skeleton)...")

        prompt1 = self._prompts["analyze_1_structure.txt"]
        prompt1 = prompt1.replace("{target_package_instruction}", pkg_instruction)
        prompt1 = prompt1.replace("{document_text}", doc_text)
        prompt1 = prompt1.replace("{tables_text}", tables_text)
        prompt1 = prompt1.replace("{format_info}", format_info)

        if format_page_images:
            prompt1 += f"\n\n# 截图说明\n共附带 {len(format_page_images)} 张格式模板页面截图。\n"

        if packages_pre and packages_pre.get("total_lots", 1) > 1:
            prompt1 += (
                f"\n\n# 预分析包信息（参考）\n"
                f"{json.dumps(packages_pre, ensure_ascii=False, indent=2)}\n"
            )
        resp1 = self._call_llm(prompt1, images=format_page_images, max_tokens=8192)
        print(f"    - Step 1 LLM响应: {len(resp1)} 字符，正在解析JSON...", flush=True)
        structure = extract_and_parse_json(resp1, label="structure")
        _save_step("structure", structure)

        scoring_factors_json = json.dumps(
            structure.get("scoring_factors", []), ensure_ascii=False, indent=2
        )
        print(f"    - scoring_factors: {len(structure.get('scoring_factors', []))} items")

        # --- Step 2: Full-text search ---
        if on_progress:
            on_progress("分析Step2: 全文检索评分因素内容...", 2, 6)
        print("  [2/4] Searching document for scoring factor content...")

        prompt2 = self._prompts["analyze_2_search.txt"]
        prompt2 = prompt2.replace("{target_package_instruction}", pkg_instruction)
        prompt2 = prompt2.replace("{document_text}", doc_text)
        prompt2 = prompt2.replace("{scoring_factors}", scoring_factors_json)

        try:
            resp2 = self._call_llm(prompt2, max_tokens=16384, max_continuations=5)
            print(f"    - Step 2 LLM响应: {len(resp2)} 字符，正在解析JSON...", flush=True)
            search_results = extract_and_parse_json(resp2, label="search", expect_array=True)
        except Exception as e:
            print(f"    [WARNING] Step 2 解析失败: {e}", flush=True)
            print(f"    使用空搜索结果继续...", flush=True)
            search_results = []
        _save_step("search", search_results)

        print(f"    - search results: {len(search_results)} items")

        # --- Step 3: Cross-fill mapping ---
        if on_progress:
            on_progress("分析Step3: 交叉填充与孤立需求识别...", 3, 6)
        print("  [3/4] Cross-filling and orphan detection...")

        prompt3 = self._prompts["analyze_3_mapping.txt"]
        prompt3 = prompt3.replace("{target_package_instruction}", pkg_instruction)
        prompt3 = prompt3.replace("{scoring_factors}", scoring_factors_json)
        prompt3 = prompt3.replace("{search_results}", json.dumps(search_results, ensure_ascii=False, indent=2))

        try:
            resp3 = self._call_llm(prompt3, max_tokens=8192)
            print(f"    - Step 3 LLM响应: {len(resp3)} 字符，正在解析JSON...", flush=True)
            mapping = extract_and_parse_json(resp3, label="mapping", expect_array=True)
        except Exception as e:
            print(f"    [WARNING] Step 3 解析失败: {e}", flush=True)
            print(f"    使用search_results作为mapping继续...", flush=True)
            mapping = search_results
        _save_step("mapping", mapping)

        print(f"    - mapping: {len(mapping)} items")

        # --- Merge ---
        # packages: prefer Step 1 result; fall back to Step 0 pre-analysis
        packages_from_structure = structure.get("packages", [])
        fallback_lots = [
            lot for lot in packages_pre.get("lots", [])
            if isinstance(lot, dict) and lot.get("id") and lot.get("name")
        ]
        result = {
            "project_info": structure.get("project_info", {}),
            "packages": packages_from_structure if packages_from_structure else fallback_lots,
            "packages_pre": packages_pre,
            "scoring_shared": structure.get("scoring_shared", False),
            "scoring_factors": structure.get("scoring_factors", []),
            "response_format": structure.get("response_format", {}),
            "scoring_requirements_mapping": mapping,
        }

        # Inject DOCX format paragraphs if provided
        if docx_format_paragraphs:
            self._inject_docx_paragraphs(result, docx_format_paragraphs)

        print("  [OK] Analysis complete (4 steps)")
        return result

    # ------------------------------------------------------------------
    # Format section identification (unchanged)
    # ------------------------------------------------------------------

    def identify_format_section(self, document_text: str, file_ext: str,
                                 page_count: int = 0,
                                 docx_para_list: Optional[List[dict]] = None) -> dict:
        """
        Identify the format template section location in a procurement document.

        For PDF: returns start_page / end_page.
        For DOCX with docx_para_list: returns start_para / end_para (paragraph indices).
        """
        # --- Shared description of what a format section is ---
        FORMAT_DESC = """格式模板章节的常见名称：
- 投标文件格式、响应文件格式、电子投标文件格式
- 谈判响应文件格式、磋商响应文件格式
- 附件格式、附件--谈判响应文件格式
- 通常在第六章、第七章、第八章或附件部分

注意：
1. 目录中会出现章节名称，请找真正的正文章节起点，不是目录条目
2. 如果格式章节内容只有"详见附件"等字样，记录该情况但仍标记found=true
3. 章节结束位置取下一个同级章节标题之前"""

        if file_ext == ".docx" and docx_para_list is not None and not docx_para_list:
            print("  [WARNING] docx_para_list is empty (table-only document?), falling back to text preview")
        if file_ext == ".docx" and docx_para_list:
            para_lines = "\n".join(
                f"[{p['idx']}] {p['text'][:80]}" for p in docx_para_list
            )
            prompt = f"""以下是招标/磋商文件DOCX的段落列表（格式：[段落序号] 内容）。

{FORMAT_DESC}

请返回JSON（只返回JSON，不要其他文字）：
{{
  "found": true/false,
  "section_title": "章节完整标题",
  "start_para": 起始段落序号(整数，格式章节标题所在行),
  "end_para": 结束段落序号(整数，下一个同级章节标题前一行)
}}

如无格式模板章节，返回 {{"found": false}}

# 段落列表

{para_lines}"""
        else:
            text_preview = document_text[:8000] if len(document_text) > 8000 else document_text
            prompt = f"""请阅读以下招标文件文本，找到格式模板章节的位置。

{FORMAT_DESC}

文件类型: {file_ext}
{"总页数: " + str(page_count) if page_count else ""}

请返回JSON（只返回JSON，不要其他文字）：
{{
  "found": true/false,
  "section_title": "章节完整标题",
  "start_page": 起始页码(1-based，仅PDF),
  "end_page": 结束页码(1-based，仅PDF),
  "keyword": "用于定位的关键词(仅DOCX)"
}}

如无格式模板章节，返回 {{"found": false}}

# 文档文本

{text_preview}"""

        try:
            response = self.llm_provider.generate(prompt, max_tokens=256)
            result = extract_and_parse_json(response, label="format_section")
            if file_ext == ".docx" and docx_para_list:
                result["_mode"] = "para_idx"
            return result
        except Exception as e:
            print(f"  [WARNING] 格式章节识别失败: {str(e)}")
            return {"found": False}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _call_llm(self, prompt: str, images=None, max_tokens: int = 8192,
                   max_continuations: int = 3) -> str:
        return call_llm_with_continuation(
            self.llm_provider, prompt, images=images,
            max_tokens=max_tokens, max_continuations=max_continuations,
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
