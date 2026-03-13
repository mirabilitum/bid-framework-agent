# -*- coding: utf-8 -*-
"""
Bid Framework Generator Agent
Main orchestrator: parse → analyze → generate → output Word document.
"""

import os
import json
from typing import Optional, List, Dict, Any

from .document_parser import DocumentParser
from .llm_provider import create_llm_provider, BaseLLMProvider
from .llm_analyzer import LLMAnalyzer
from .llm_generator import LLMFrameworkGenerator
from .document_generator import DocumentGenerator


class BidFrameworkAgent:
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
        print("[1/4] Parsing document ...")
        parser = DocumentParser(input_file)
        full_text, paragraphs, tables = parser.parse()
        print(f"  Text: {len(full_text)} chars | Paragraphs: {len(paragraphs)} | Tables: {len(tables)}")

        # Step 1.5: PDF format-template screenshots for vision
        format_images = None
        if parser.ext == ".pdf":
            print("[1.5] Capturing format-template page screenshots ...")
            fmt_pages = parser.find_format_template_pages()
            if fmt_pages:
                format_images = parser.screenshot_pages(fmt_pages, dpi=100)
                print(f"  Captured {len(format_images)} page(s)")
            else:
                print("  No format-template pages found, skipping")

        # --- Step 2: LLM analysis ---
        print("[2/4] Analyzing document with LLM ...")
        analysis = self.analyzer.analyze(full_text, tables, format_page_images=format_images)

        # --- Step 3: Multi-package handling ---
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

        # --- Step 4: Generate framework(s) ---
        if packages_info and packages:
            results = []
            for pkg_id in packages:
                pkg = next((p for p in packages_info if str(p["id"]) == str(pkg_id)), None)
                if pkg:
                    path = self._process_package(analysis, full_text, pkg, output_dir or "output", save_intermediate)
                    results.append(path)
            final_path = output_dir or "output"
        else:
            final_path = self._process_package(
                analysis, full_text, None,
                output_file or os.path.join(output_dir or "output", "framework.docx"),
                save_intermediate,
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
    ) -> str:
        """Process a single package and return the output path."""
        label = f"Package {package_info['id']}" if package_info else "document"
        print(f"\n[3/4] Generating framework for {label} ...")
        framework = self.generator.generate(analysis, full_text)

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
            # framework is a list of FrameworkNode, serialise via generator helper
            fw_data = self.generator.nodes_to_dict(framework)
            with open(os.path.join(json_dir, f"{base}_framework.json"), "w", encoding="utf-8") as f:
                json.dump(fw_data, f, ensure_ascii=False, indent=2)

        print(f"[4/4] Generating Word document ...")
        project_name = analysis.get("project_info", {}).get("name", "")
        if package_info:
            project_name += f" - Package {package_info['id']}"
        self.doc_generator.generate(framework, out, project_name)
        print(f"  Saved: {out}")
        return out

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
