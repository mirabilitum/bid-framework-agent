# -*- coding: utf-8 -*-
"""
Bid Framework Generator Agent
Main orchestrator: parse → analyze → generate → output Word document.
"""

import os
import json
import re
from copy import deepcopy
from typing import Optional, List, Dict, Any

from .document_parser import DocumentParser
from .llm_provider import create_llm_provider, BaseLLMProvider
from .llm_analyzer import LLMAnalyzer
from .llm_framework_generator import LLMFrameworkGenerator
from .document_generator import DocumentGenerator


class BidFrameworkAgentV7:
    """LLM-driven agent for generating bid response frameworks from procurement documents."""

    def __init__(
        self,
        llm_provider: str = "claude",
        api_key: Optional[str] = None,
        base_path: Optional[str] = None,
        **provider_kwargs,
    ):
        """
        Initialize agent.

        Args:
            llm_provider: Provider name ("claude", "openai", "qwen", "mock")
            api_key: API key (optional, can use env var)
            base_path: Base directory for prompts (for PyInstaller frozen exe)
            **provider_kwargs: Additional provider arguments (e.g. model="gpt-4o")
        """
        self.llm_provider_name = llm_provider
        self.provider = create_llm_provider(llm_provider, api_key, **provider_kwargs)
        self.analyzer = LLMAnalyzer(self.provider, base_path=base_path)
        self.generator = LLMFrameworkGenerator(self.provider, base_path=base_path)
        self.doc_generator = DocumentGenerator()

    def run(
        self,
        input_file: str,
        output_file: Optional[str] = None,
        output_dir: Optional[str] = None,
        packages: Optional[List[int]] = None,
        save_intermediate: bool = True,
        font_settings: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Generate bid framework from a procurement document.

        Args:
            input_file: Path to procurement document (PDF/DOCX/DOC)
            output_file: Output Word path (single package)
            output_dir: Output directory (multi-package)
            packages: Package IDs to process (None = all)
            save_intermediate: Save analysis/framework JSON alongside output
            font_settings: Optional font config dict (font_name, cover_title_size, title_size, body_size)

        Returns:
            Path to the generated Word document (or directory for multi-package)
        """
        # Apply font settings to document generator
        if font_settings:
            from .document_generator import DocumentGenerator
            self.doc_generator = DocumentGenerator(font_config=font_settings)
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

        # --- Step 1.5: Identify lots/packages (before expensive analysis) ---
        print("[1.5/6] Identifying packages/lots ...")
        lot_info = self.analyzer.identify_lots(full_text, tables)
        lot_list = [
            lot for lot in lot_info.get("lots", [])
            if isinstance(lot, dict) and lot.get("id") and lot.get("name")
        ]
        total_lots = lot_info.get("total_lots", len(lot_list))
        if len(lot_list) > 1:
            # LLM returned the full lot list — ask user to select
            print(f"\n  识别到 {total_lots} 个包/标段")
            if packages is None:
                packages = self._ask_user_packages(lot_list)
        elif total_lots > 1:
            # LLM returned count only, no detail — build placeholder lots and ask user
            print(f"\n  识别到 {total_lots} 个包/标段（包名待分析后确认）")
            lot_list = [{"id": str(i), "name": f"第{i}包"} for i in range(1, total_lots + 1)]
            if packages is None:
                packages = self._ask_user_packages(lot_list)
        else:
            print(f"  单包文档，无需选择")

        # --- Step 2: LLM identifies format section ---
        print("[2/6] LLM identifying format section location ...")
        page_count = 0
        docx_para_list = None

        if parser.ext == ".pdf":
            import fitz
            doc = fitz.open(input_file)
            page_count = len(doc)
            doc.close()
        elif parser.ext == ".docx":
            from docx import Document as _DocxDoc
            from docx.oxml.ns import qn as _qn
            _doc = _DocxDoc(input_file)
            _body = _doc.element.body
            # Use only top-level body paragraphs to match para_idx_map in document_parser
            _top_paras = [elem for elem in _body if elem.tag.endswith('}p')]
            docx_para_list = []
            for i, elem in enumerate(_top_paras):
                text = "".join(r.text or "" for r in elem.findall(_qn('w:r'))).strip()
                if not text:
                    text = (elem.text or "").strip()
                if text:
                    docx_para_list.append({"idx": i, "text": text})

        format_info = self.analyzer.identify_format_section(
            full_text, parser.ext, page_count=page_count,
            docx_para_list=docx_para_list,
        )
        if format_info.get("found"):
            print(f"  Found: {format_info.get('section_title', '')}")
        else:
            print("  No format section found, will use text-only analysis")

        # --- Step 3: Get format info ---
        format_images = None
        docx_format_paragraphs = None
        format_elements = None

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
                start_para = format_info.get("start_para")
                end_para   = format_info.get("end_para")
                section_title = format_info.get("section_title", "")

                if start_para is not None:
                    try:
                        start_para = int(start_para)
                        end_para = int(end_para) if end_para is not None else None
                    except (TypeError, ValueError):
                        print("  [WARNING] Invalid para indices from LLM, falling back to keyword")
                        start_para = None
                    print(f"[3/6] Extracting DOCX format elements (para {start_para}-{end_para}) ...")
                    format_elements = parser.extract_format_section_elements(
                        start_para_idx=start_para,
                        end_para_idx=end_para,
                    )
                else:
                    # Fallback: keyword-based (old behaviour)
                    locate_key = section_title or format_info.get("keyword", "")
                    print(f"[3/6] Extracting DOCX format elements (keyword: {locate_key or 'auto'}) ...")
                    format_elements = parser.extract_format_section_elements(
                        start_keyword=locate_key or None
                    )

                if format_elements:
                    para_count  = sum(1 for e in format_elements if e["type"] == "para")
                    table_count = sum(1 for e in format_elements if e["type"] == "table")
                    print(f"  Extracted {len(format_elements)} elements ({para_count} paragraphs, {table_count} tables)")
                    docx_format_paragraphs = [e for e in format_elements if e["type"] == "para"]
                else:
                    print("  No format elements found, falling back to paragraph extraction")
                    format_elements = None
                    locate_key = section_title or format_info.get("keyword", "")
                    if locate_key:
                        docx_format_paragraphs = parser.extract_format_section_paragraphs(
                            start_keyword=locate_key
                        )
                        if docx_format_paragraphs:
                            non_empty = sum(1 for p in docx_format_paragraphs if p["text"].strip())
                            print(f"  Fallback: {len(docx_format_paragraphs)} paragraphs ({non_empty} non-empty)")
        else:
            print("[3/6] No format section, skipping")

        # --- Multi-package handling: user selection & routing ---
        packages_info = lot_list
        # `packages` may still be None here when the document is single-package
        # (lot_list has 0 or 1 entries and neither Step 1.5 branch ran).
        # Always short-circuit on `packages` before calling len() on it.

        # Confirm selection
        if packages and packages_info:
            selected_names = []
            for pid in packages:
                pkg = next((p for p in packages_info if str(p["id"]) == str(pid)), None)
                selected_names.append(f"[{pid}] {pkg['name']}" if pkg else f"[{pid}]")
            print(f"\n  将处理 {len(packages)} 个包：")
            for n in selected_names:
                print(f"    {n}")

        # Resolve output directory
        if not output_file and not output_dir:
            base = os.path.splitext(os.path.basename(input_file))[0]
            output_dir = os.path.join("output", base)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        # Save parsed.json for quality check
        if save_intermediate and output_dir:
            tables_text = "\n\n".join(
                "\n".join("\t".join(str(c) for c in row) for row in t)
                for t in tables if t
            )
            with open(os.path.join(output_dir, "parsed.json"), "w", encoding="utf-8") as f:
                json.dump({"full_text": full_text, "tables_text": tables_text}, f,
                          ensure_ascii=False, indent=2)

        # scoring_shared from Step 0 pre-analysis.
        # NOTE: In the placeholder-lot path (LLM returned count only, no lot details),
        # lot_info may not contain a reliable "scoring_shared" value — it defaults to False,
        # which means each package is analysed separately. This is safe but may be redundant
        # if the document actually shares scoring criteria across lots.
        scoring_shared = lot_info.get("scoring_shared", False)

        # --- Step 4, 5, 6: LLM analysis & Generation ---
        if packages_info and packages and len(packages) > 1 and scoring_shared:
            # All selected packages share the same evaluation criteria.
            print(f"\n[4/6] 评分标准共用（scoring_shared=true），生成全标段通用分析与框架...")
            analysis = self.analyzer.analyze(
                full_text, tables,
                format_page_images=format_images,
                docx_format_paragraphs=docx_format_paragraphs,
                output_dir=output_dir,
                lot_context=lot_info,
                target_package=None  # Analyze generically
            )
            pkg_ids_str = "、".join(str(p) for p in packages)
            project_name = analysis.get("project_info", {}).get("name", "")
            project_name_labeled = f"{project_name}（第{pkg_ids_str}包通用）" if project_name else f"第{pkg_ids_str}包通用框架"
            safe_label = f"pkg{'_'.join(str(p) for p in packages)}_共用框架"
            out = os.path.join(output_dir or "output", f"{safe_label}.docx")
            
            final_path = self._process_package(
                analysis, full_text, None,
                out, save_intermediate, format_elements=format_elements,
                project_name_override=project_name_labeled,
            )

        elif packages_info and packages:
            if len(packages) == 1:
                # Single package selected: targeted analysis for best accuracy
                pkg_id = packages[0]
                pkg = next((p for p in packages_info if str(p["id"]) == str(pkg_id)), None)
                if pkg:
                    print(f"\n[4/6] 单包针对性分析与生成（包 {pkg_id}）...")
                    pkg_output_dir = os.path.join(output_dir, f"pkg_{pkg_id}") if output_dir else None
                    if pkg_output_dir:
                        os.makedirs(pkg_output_dir, exist_ok=True)
                    analysis = self.analyzer.analyze(
                        full_text, tables,
                        format_page_images=format_images,
                        docx_format_paragraphs=docx_format_paragraphs,
                        output_dir=pkg_output_dir or output_dir,
                        lot_context=lot_info,
                        target_package=pkg,
                    )
                    final_path = self._process_package(
                        analysis, full_text, pkg,
                        pkg_output_dir or output_dir or "output",
                        save_intermediate, format_elements=format_elements,
                    )
                else:
                    print(f"\n  [WARNING] 包编号 {pkg_id} 未在识别结果中找到")
                    final_path = output_dir or "output"

            else:
                # Multiple packages: ONE master analysis, then generate per package.
                # Saves (N-1)*3 LLM calls vs per-package analysis.
                # _filter_analysis_for_package() inside _process_package handles per-package filtering.
                saved = (len(packages) - 1) * 3
                print(f"\n[4/6] 多包模式：全量分析1次 + 逐包生成（共 {len(packages)} 包，节省约 {saved} 次LLM调用）...")
                master_analysis = self.analyzer.analyze(
                    full_text, tables,
                    format_page_images=format_images,
                    docx_format_paragraphs=docx_format_paragraphs,
                    output_dir=output_dir,
                    lot_context=lot_info,
                    target_package=None,
                )
                results = []
                for i, pkg_id in enumerate(packages, 1):
                    pkg = next((p for p in packages_info if str(p["id"]) == str(pkg_id)), None)
                    if not pkg:
                        print(f"\n  [WARNING] 包编号 {pkg_id} 未在识别结果中找到，跳过")
                        continue
                    print(f"\n--- 生成 [{pkg_id}] {pkg.get('name', '')} ({i}/{len(packages)}) ---")
                    pkg_output_dir = os.path.join(output_dir, f"pkg_{pkg_id}") if output_dir else None
                    if pkg_output_dir:
                        os.makedirs(pkg_output_dir, exist_ok=True)
                    path = self._process_package(
                        master_analysis, full_text, pkg,
                        pkg_output_dir or output_dir or "output",
                        save_intermediate, format_elements=format_elements,
                    )
                    results.append(path)
                final_path = output_dir or "output"

        else:
            # Single-package document
            print(f"\n[4/6] 单包文档分析与生成...")
            analysis = self.analyzer.analyze(
                full_text, tables,
                format_page_images=format_images,
                docx_format_paragraphs=docx_format_paragraphs,
                output_dir=output_dir,
                lot_context=lot_info,
                target_package=None
            )
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
        project_name_override: Optional[str] = None,
    ) -> str:
        """Process a single package and return the output path."""
        label = f"Package {package_info['id']}" if package_info else "document"
        if not package_info:
            print(f"[5/6] Generating framework for {label} ...")
        filtered_analysis = self._filter_analysis_for_package(analysis, package_info)
        if package_info:
            print(
                "  Package filter:"
                f" packages {self._collection_size(analysis.get('packages'))}"
                f" -> {self._collection_size(filtered_analysis.get('packages'))},"
                f" scoring_factors {self._collection_size(analysis.get('scoring_factors'))}"
                f" -> {self._collection_size(filtered_analysis.get('scoring_factors'))},"
                f" mapping {self._collection_size(analysis.get('scoring_requirements_mapping'))}"
                f" -> {self._collection_size(filtered_analysis.get('scoring_requirements_mapping'))}"
            )
        try:
            framework = self.generator.generate(filtered_analysis, full_text)
        except (ValueError, Exception) as e:
            print(f"\n{'!' * 60}")
            print(f"  [错误] 框架生成失败: {e}")
            print(f"{'!' * 60}")
            # Save whatever analysis we have so user can inspect
            if save_intermediate:
                json_dir = os.path.dirname(output_path) if not os.path.isdir(output_path) else output_path
                err_path = os.path.join(json_dir, f"{label}_analysis_before_error.json")
                try:
                    with open(err_path, "w", encoding="utf-8") as f:
                        json.dump(filtered_analysis, f, ensure_ascii=False, indent=2)
                    print(f"  分析结果已保存: {err_path}")
                except Exception:
                    pass
            raise

        # Inject DOCX format content directly (bypasses LLM for format sections)
        if format_elements:
            injected = self._inject_docx_format_content(framework, format_elements)
            print(f"  DOCX injection: {injected} node(s) matched")

        # Determine output file
        if os.path.isdir(output_path):
            name = filtered_analysis.get("project_info", {}).get("name", "framework")
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
                json.dump(filtered_analysis, f, ensure_ascii=False, indent=2)
            fw_data = [self._node_to_dict(n) for n in framework]
            with open(os.path.join(json_dir, f"{base}_framework.json"), "w", encoding="utf-8") as f:
                json.dump({"framework": fw_data}, f, ensure_ascii=False, indent=2)
            # Standard-name copies for quality check
            with open(os.path.join(json_dir, "analysis.json"), "w", encoding="utf-8") as f:
                json.dump(filtered_analysis, f, ensure_ascii=False, indent=2)
            with open(os.path.join(json_dir, "framework.json"), "w", encoding="utf-8") as f:
                json.dump({"framework": fw_data}, f, ensure_ascii=False, indent=2)

        print(f"[6/6] Generating Word document ...")
        if project_name_override:
            project_name = project_name_override
        else:
            project_name = filtered_analysis.get("project_info", {}).get("name", "")
            if package_info:
                project_name += f" - 第{package_info['id']}包"
        self.doc_generator.generate(framework, out, project_name)
        print(f"  Saved: {out}")
        return out

    def _filter_analysis_for_package(
        self,
        analysis: Dict[str, Any],
        package_info: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Return a package-scoped analysis copy for multi-package generation."""
        if not package_info:
            return analysis

        filtered = deepcopy(analysis)
        all_packages = analysis.get("packages", [])

        if isinstance(filtered.get("packages"), list):
            filtered["packages"] = [
                pkg for pkg in filtered["packages"]
                if str(pkg.get("id", "")).strip() == str(package_info.get("id", "")).strip()
            ]

        for field in ("scoring_factors", "scoring_requirements_mapping"):
            if field in filtered:
                filtered[field] = self._filter_package_value(
                    filtered[field], package_info, all_packages
                )

        return filtered

    def _filter_package_value(
        self,
        value: Any,
        package_info: Dict[str, Any],
        all_packages: List[Dict[str, Any]],
    ) -> Any:
        if isinstance(value, list):
            return [
                item for item in value
                if self._item_matches_package(item, package_info, all_packages)
            ]

        if isinstance(value, dict):
            current_keys = set()
            other_keys = set()
            for key in value.keys():
                key_text = str(key)
                if self._matches_package_token(key_text, package_info):
                    current_keys.add(key)
                    continue
                if any(
                    self._matches_package_token(key_text, pkg)
                    for pkg in all_packages
                    if str(pkg.get("id", "")) != str(package_info.get("id", ""))
                ):
                    other_keys.add(key)

            # When dict keys are package-specific, keep only current package keys plus
            # untagged/global keys. If the structure is not package-aware, leave it as-is.
            if current_keys or other_keys:
                return {
                    key: val for key, val in value.items()
                    if key in current_keys or key not in other_keys
                }

        return value

    def _item_matches_package(
        self,
        item: Any,
        package_info: Dict[str, Any],
        all_packages: List[Dict[str, Any]],
    ) -> bool:
        if not isinstance(item, dict):
            return True

        direct_match = self._match_package_metadata(item, package_info, all_packages)
        if direct_match is not None:
            return direct_match

        text = json.dumps(item, ensure_ascii=False)
        current_hit = self._text_mentions_package(text, package_info)
        other_hit = any(
            self._text_mentions_package(text, pkg)
            for pkg in all_packages
            if str(pkg.get("id", "")) != str(package_info.get("id", ""))
        )

        if current_hit and not other_hit:
            return True
        if other_hit and not current_hit:
            return False

        # No reliable package marker: keep the item to avoid dropping shared data.
        return True

    def _match_package_metadata(
        self,
        item: Dict[str, Any],
        package_info: Dict[str, Any],
        all_packages: List[Dict[str, Any]],
    ) -> Optional[bool]:
        metadata_keys = (
            "package_id", "package_ids", "package", "packages",
            "package_name", "package_names", "packageName",
            "pkg_id", "pkg_ids", "applicable_package", "applicable_packages",
        )

        for key in metadata_keys:
            if key not in item:
                continue
            values = item[key]
            if not isinstance(values, list):
                values = [values]

            has_current = False
            has_other = False
            for value in values:
                if self._matches_package_token(value, package_info):
                    has_current = True
                elif any(
                    self._matches_package_token(value, pkg)
                    for pkg in all_packages
                    if str(pkg.get("id", "")) != str(package_info.get("id", ""))
                ):
                    has_other = True

            if has_current:
                return True
            if has_other:
                return False

        return None

    @staticmethod
    def _normalize_package_name(value: Any) -> str:
        return re.sub(r"\s+", "", str(value or "").strip().lower())

    def _matches_package_token(self, value: Any, package_info: Dict[str, Any]) -> bool:
        normalized = self._normalize_package_name(value)
        package_id = str(package_info.get("id", "")).strip().lower()
        package_name = self._normalize_package_name(package_info.get("name"))

        if package_id and normalized == package_id:
            return True
        if package_name and normalized == package_name:
            return True
        return self._text_mentions_package(str(value or ""), package_info)

    def _text_mentions_package(self, text: str, package_info: Dict[str, Any]) -> bool:
        normalized = str(text or "").lower()
        compact = re.sub(r"\s+", "", normalized)
        package_id = str(package_info.get("id", "")).strip().lower()
        package_name = self._normalize_package_name(package_info.get("name"))

        patterns = []
        if package_id:
            patterns.extend([
                f"package {package_id}",
                f"package-{package_id}",
                f"package{package_id}",
                f"pkg{package_id}",
                f"\u5305{package_id}",
                f"\u5305 {package_id}",
                f"\u7b2c{package_id}\u5305",
                f"\u91c7\u8d2d\u5305{package_id}",
                f"\u91c7\u8d2d\u5305 {package_id}",
                f"\u6807\u5305{package_id}",
                f"\u6807\u5305 {package_id}",
                f"{package_id}\u5305",
            ])
        if package_name:
            patterns.append(package_name)

        for pattern in patterns:
            pattern_lower = pattern.lower()
            pattern_compact = re.sub(r"\s+", "", pattern_lower)
            if pattern_lower and pattern_lower in normalized:
                return True
            if pattern_compact and pattern_compact in compact:
                return True
        return False

    @staticmethod
    def _collection_size(value: Any) -> int:
        if isinstance(value, (list, dict)):
            return len(value)
        return 0

    @staticmethod
    def _node_to_dict(node) -> dict:
        d = {"level": node.level, "title": node.title, "content": getattr(node, "content", ""),
             "children": [BidFrameworkAgentV7._node_to_dict(c) for c in node.children]}
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
                # Containment match (min 2 chars to avoid false positives)
                elif len(min(text_core, title_core_no_format, key=len)) >= 2 and (
                    title_core_no_format in text_core or text_core in title_core_no_format
                ):
                    score = 10 + bold_bonus
                    if score > best_score:
                        best_score = score
                        best_idx = i

        return best_idx

    def _ask_user_packages(self, packages_info: List[str]) -> List[str]:
        """Prompt user to select packages (Chinese)."""
        print("\n  请选择要生成的包/标段：")
        for p in packages_info:
            budget = f"  预算: {p['budget']}" if p.get("budget") else ""
            print(f"    [{p['id']}] {p['name']}{budget}")
        print("  输入包编号（逗号分隔，如 1,3,5），直接回车生成全部：")

        # Flush any buffered keystrokes (e.g. Enter pressed during LLM wait)
        try:
            import msvcrt
            while msvcrt.kbhit():
                msvcrt.getwch()
        except Exception:
            pass

        user_input = input("  > ").strip()
        if not user_input:
            return [str(p["id"]) for p in packages_info]
        selected = [x.strip() for x in user_input.split(",") if x.strip()]
        if not selected:
            return [str(p["id"]) for p in packages_info]
        return selected
