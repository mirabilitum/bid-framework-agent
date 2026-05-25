# -*- coding: utf-8 -*-
"""
Bid Framework Generator Agent
Main orchestrator: parse → analyze → generate → output Word document.
"""

import os
import json
import re
from typing import Optional, List, Dict, Any

from .document_parser import DocumentParser
from .llm_provider import create_llm_provider, BaseLLMProvider
from .llm_analyzer import LLMAnalyzer
from .llm_framework_generator import LLMFrameworkGenerator
from .document_generator import DocumentGenerator


class BidFrameworkAgentV6:
    """LLM-driven agent for generating bid response frameworks from procurement documents."""

    def __init__(
        self,
        llm_provider: str = "claude",
        api_key: Optional[str] = None,
        **provider_kwargs,
    ):
        """
        Initialize agent.

        Args:
            llm_provider: Provider name ("claude", "openai", "qwen", "mock")
            api_key: API key (optional, can use env var)
            **provider_kwargs: Additional provider arguments (e.g. model="gpt-4o")
        """
        self.llm_provider_name = llm_provider
        self.provider = create_llm_provider(llm_provider, api_key, **provider_kwargs)
        self.analyzer = LLMAnalyzer(self.provider)
        self.generator = LLMFrameworkGenerator(self.provider)
        self.doc_generator = DocumentGenerator()

    def run(
        self,
        input_file: str,
        output_file: Optional[str] = None,
        output_dir: Optional[str] = None,
        packages: Optional[List[int]] = None,
        save_intermediate: bool = False,
    ) -> str:
        """
        Generate bid framework from a procurement document.

        Args:
            input_file: Path to procurement document (PDF/DOCX/DOC)
            output_file: Output Word path (single package)
            output_dir: Output directory (multi-package)
            packages: Package IDs to process (None = all)
            save_intermediate: Save analysis/framework JSON alongside output

        Returns:
            Path to the generated Word document (or directory for multi-package)
        """
        print(f"\n{'=' * 60}")
        print("Bid Framework Generator Agent")
        print(f"Input : {os.path.basename(input_file)}")
        print(f"LLM   : {self.llm_provider_name}")
        print(f"{'=' * 60}\n")

        # --- Step 1: Parse document ---
        print("[1/6] Parsing document ...")
        parser = DocumentParser(input_file)
        full_text, paragraphs, tables = parser.parse()
        print(f"  Text: {len(full_text)} chars | Paragraphs: {len(paragraphs)} | Tables: {len(tables)}")

        # --- Step 2: LLM identifies format section ---
        print("[2/6] LLM identifying format section location ...")
        page_count = 0
        if parser.ext == ".pdf":
            page_count = parser.page_count

        format_info = self.analyzer.identify_format_section(
            full_text, parser.ext, page_count=page_count
        )
        if format_info.get("found"):
            print(f"  Found: {format_info.get('section_title', '')}")
        else:
            print("  No format section found, will use text-only analysis")

        # --- Step 3: Get format info ---
        format_images = None
        docx_format_paragraphs = None
        format_elements = None  # DOCX flat element list for direct injection

        if format_info.get("found"):
            if parser.ext == ".pdf" and self.provider.supports_vision:
                start_page = format_info.get("start_page", 0)
                end_page = format_info.get("end_page", 0)
                if start_page and end_page:
                    print(f"[3/6] Capturing format pages {start_page}-{end_page} ...")
                    fmt_pages = list(range(start_page - 1, end_page))
                    format_images = parser.screenshot_pages(fmt_pages, dpi=100)
                    print(f"  Captured {len(format_images)} page(s)")
                else:
                    print("[3/6] Page range unclear, skipping screenshots")
            elif parser.ext == ".pdf":
                print("[3/6] LLM does not support vision, skipping screenshots")
            elif parser.ext == ".docx":
                keyword = format_info.get("keyword", "")
                print(f"[3/6] Extracting DOCX format elements (keyword: {keyword or 'auto'}) ...")
                format_elements = parser.extract_format_section_elements(
                    start_keyword=keyword or None
                )
                if format_elements:
                    para_count = sum(1 for e in format_elements if e["type"] == "para")
                    table_count = sum(1 for e in format_elements if e["type"] == "table")
                    print(f"  Extracted {len(format_elements)} elements ({para_count} paragraphs, {table_count} tables)")
                    # Also provide flat paragraphs for LLM analysis
                    docx_format_paragraphs = [e for e in format_elements if e["type"] == "para"]
                else:
                    print("  No format elements found, falling back to paragraph extraction")
                    format_elements = None
                    if keyword:
                        docx_format_paragraphs = parser.extract_format_section_paragraphs(
                            start_keyword=keyword
                        )
                        if docx_format_paragraphs:
                            non_empty = sum(1 for p in docx_format_paragraphs if p["text"].strip())
                            print(f"  Fallback: {len(docx_format_paragraphs)} paragraphs ({non_empty} non-empty)")
        else:
            print("[3/6] No format section, skipping")

        # --- Step 4: LLM analysis ---
        print("[4/6] Analyzing document with LLM ...")
        analysis = self.analyzer.analyze(
            full_text, tables,
            format_page_images=format_images,
            docx_format_paragraphs=docx_format_paragraphs,
        )

        # --- Multi-package handling ---
        packages_info = analysis.get("packages", [])
        if packages_info:
            print(f"  Multi-package document: {len(packages_info)} package(s)")
            for pkg in packages_info:
                print(f"    - Package {pkg['id']}: {pkg['name']}")
            if packages is None:
                packages = self._ask_user_packages(packages_info)
        else:
            packages = None

        # Resolve output path
        if not output_file and not output_dir:
            base = os.path.splitext(os.path.basename(input_file))[0]
            output_dir = os.path.join("output", base)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        # --- Step 5+6: Generate framework(s) and Word ---
        if packages_info and packages:
            results = []
            for pkg_id in packages:
                pkg = next((p for p in packages_info if str(p["id"]) == str(pkg_id)), None)
                if pkg:
                    path = self._process_package(
                        analysis, full_text, pkg, output_dir or "output",
                        save_intermediate, format_elements=format_elements,
                    )
                    results.append(path)
            final_path = output_dir or "output"
        else:
            final_path = self._process_package(
                analysis, full_text, None,
                output_file or os.path.join(output_dir or "output", "framework.docx"),
                save_intermediate, format_elements=format_elements,
            )

        print(f"\n{'=' * 60}")
        print(f"Done! Output: {final_path}")
        print(f"{'=' * 60}\n")
        return final_path

    def _process_package(
        self,
        analysis: Dict[str, Any],
        full_text: str,
        package_info: Optional[Dict],
        output_path: str,
        save_intermediate: bool,
        format_elements: Optional[List[Dict]] = None,
    ) -> str:
        """Process a single package and return the output path."""
        label = f"Package {package_info['id']}" if package_info else "document"
        print(f"\n[5/6] Generating framework for {label} ...")
        framework = self.generator.generate(analysis, full_text)

        # Inject DOCX format content directly (bypasses LLM for format sections)
        if format_elements:
            injected = self._inject_docx_format_content(framework, format_elements)
            print(f"  DOCX injection: {injected} node(s) matched")

        # Determine output file
        if os.path.isdir(output_path):
            name = analysis.get("project_info", {}).get("name", "framework")
            if package_info:
                name += f"_pkg{package_info['id']}"
            safe = name.replace("/", "_").replace("\\", "_").replace(":", "_")
            out = os.path.join(output_path, f"{safe}.docx")
        else:
            out = output_path

        # Save intermediate JSON
        if save_intermediate:
            json_dir = os.path.dirname(out)
            base = os.path.splitext(os.path.basename(out))[0]
            with open(os.path.join(json_dir, f"{base}_analysis.json"), "w", encoding="utf-8") as f:
                json.dump(analysis, f, ensure_ascii=False, indent=2)
            fw_data = [self._node_to_dict(n) for n in framework]
            with open(os.path.join(json_dir, f"{base}_framework.json"), "w", encoding="utf-8") as f:
                json.dump({"framework": fw_data}, f, ensure_ascii=False, indent=2)

        print(f"[6/6] Generating Word document ...")
        project_name = analysis.get("project_info", {}).get("name", "")
        if package_info:
            project_name += f" - Package {package_info['id']}"
        self.doc_generator.generate(framework, out, project_name)
        print(f"  Saved: {out}")
        return out

    @staticmethod
    def _node_to_dict(node) -> dict:
        d = {"level": node.level, "title": node.title, "content": getattr(node, "content", ""),
             "children": [BidFrameworkAgentV6._node_to_dict(c) for c in node.children]}
        if getattr(node, "cover_page", None):
            d["cover_page"] = node.cover_page
        if getattr(node, "index_page", None):
            d["index_page"] = node.index_page
        if getattr(node, "elements", None):
            d["elements"] = node.elements
        return d

    # ------------------------------------------------------------------ #
    #  DOCX format content injection — flat list, title-based slicing
    # ------------------------------------------------------------------ #

    def _inject_docx_format_content(self, framework_nodes, elements: List[Dict]) -> int:
        """
        将DOCX提取的格式章节内容注入框架节点。

        通用逻辑（不依赖任何文档结构假设）：
        1. 收集框架中所有叶子节点的标题
        2. 在扁平元素列表中找到每个标题的位置（段落文本匹配）
        3. 提取该标题到下一个匹配标题之间的所有元素作为该节点的content
        4. 注入到节点的 elements 字段，渲染时优先使用

        Returns:
            注入成功的节点数
        """
        # 1. Collect all leaf/content node titles from framework (DFS)
        all_nodes = []
        self._collect_content_nodes(framework_nodes, all_nodes)
        if not all_nodes:
            return 0

        # 2. Build title index: find each title's position in elements list
        #    A "position" is the index of the paragraph whose text best matches the title
        title_positions = []  # [(node, elem_index)]
        for node in all_nodes:
            title = self._normalize_title(getattr(node, 'title', ''))
            if not title:
                continue
            idx = self._find_title_in_elements(title, elements)
            if idx is not None:
                title_positions.append((node, idx))

        if not title_positions:
            return 0

        # Sort by position in document
        title_positions.sort(key=lambda x: x[1])

        # 3. Slice elements between consecutive matched titles
        injected = 0
        for i, (node, start_idx) in enumerate(title_positions):
            # End = next matched title's position, or end of list
            if i + 1 < len(title_positions):
                end_idx = title_positions[i + 1][1]
            else:
                end_idx = len(elements)

            # Content = elements after the title paragraph, up to next title
            content_elements = elements[start_idx + 1 : end_idx]

            # Skip if free_form (LLM content should be kept)
            if getattr(node, 'is_free_form', False):
                continue

            if content_elements:
                node.elements = content_elements
                injected += 1

        return injected

    def _collect_content_nodes(self, nodes, result):
        """DFS collect all nodes that could receive injected content."""
        for node in nodes:
            children = getattr(node, 'children', [])
            if children:
                self._collect_content_nodes(children, result)
            else:
                # Leaf node
                result.append(node)
            # Also include non-leaf nodes that have content themselves
            # (some nodes have both content and children)

    def _normalize_title(self, title: str) -> str:
        """Strip [CENTER]/[RIGHT] markers for matching."""
        t = title.strip()
        for prefix in ('[CENTER]', '[RIGHT]'):
            if t.startswith(prefix):
                t = t[len(prefix):]
        return t.strip()

    def _find_title_in_elements(self, title: str, elements: List[Dict]) -> Optional[int]:
        """
        在扁平元素列表中找到与标题最匹配的段落位��。

        匹配策略（按优先级）：
        1. 精确匹配 + 加粗（最优）
        2. 精确匹配（非加粗）
        3. 去编号后匹配 + 加粗
        4. 去编号后匹配（非加粗）
        5. 包含匹配 + 加粗
        6. 包含匹配（非加粗）

        加粗段落优先，因为实际章节标题通常加粗，索引条目通常不加粗。
        """
        title_core = re.sub(
            r'^[一二三四五六七八九十百千\d]+([-—][一二三四五六七八九十百千\d]+)*\s*[、.．:：\s]\s*',
            '', title
        ).strip()
        title_no_format = re.sub(r'^格式', '', title).strip()
        title_core_no_format = re.sub(r'^格式', '', title_core).strip()

        best_idx = None
        best_score = 0  # higher = better match

        for i, elem in enumerate(elements):
            if elem.get("type") != "para":
                continue
            text = elem.get("text", "").strip()
            if not text:
                continue

            is_bold = elem.get("bold", False)
            bold_bonus = 10 if is_bold else 0  # Bold matches always rank higher

            # Exact match
            if text == title or text == title_no_format:
                score = 30 + bold_bonus
                if score > best_score:
                    best_score = score
                    best_idx = i
                if is_bold:
                    return i  # Perfect match, return immediately
                continue

            # Strip numbering from element text
            text_core = re.sub(
                r'^[一二三四五六七八九十百千\d]+([-—][一二三四五六七八九十百千\d]+)*\s*[、.．:：\s]\s*',
                '', text
            ).strip()
            text_core = re.sub(r'^格式', '', text_core).strip()

            if text_core and title_core_no_format:
                # Core exact match
                if text_core == title_core_no_format:
                    score = 20 + bold_bonus
                    if score > best_score:
                        best_score = score
                        best_idx = i
                # Containment match: pick the shorter string to check its length (min 2 chars to avoid false positives)
                elif len(min(text_core, title_core_no_format, key=len)) >= 2 and (
                    title_core_no_format in text_core or text_core in title_core_no_format
                ):
                    score = 10 + bold_bonus
                    if score > best_score:
                        best_score = score
                        best_idx = i

        return best_idx

    def _ask_user_packages(self, packages_info: List[Dict]) -> List[int]:
        """Prompt user to select packages."""
        print("\n  Which packages to process?")
        print("  Enter IDs separated by comma (e.g. 1,2), or press Enter for all:")
        user_input = input("  > ").strip()
        if not user_input:
            return [int(p["id"]) for p in packages_info]
        try:
            return [int(x.strip()) for x in user_input.split(",")]
        except ValueError:
            print("  Invalid input, processing all packages")
            return [int(p["id"]) for p in packages_info]
