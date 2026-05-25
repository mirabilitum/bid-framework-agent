# -*- coding: utf-8 -*-
"""
LLM Framework Generator (v7 split-prompt version)
Generates bid response framework using 3 sequential LLM calls:
  Step 1: Skeleton (directory structure, content empty)
  Step 2: Scoring expansion (scoring factors → framework nodes)
  Step 3: Content filling (template text, tables, alignment)
"""

import os
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

try:
    from .llm_provider import BaseLLMProvider
    from .json_repair import extract_and_parse_json
    from .llm_utils import call_llm_with_continuation
except ImportError:
    from llm_provider import BaseLLMProvider
    from json_repair import extract_and_parse_json
    from llm_utils import call_llm_with_continuation


@dataclass
class FrameworkNode:
    """Framework tree node"""
    level: int
    title: str
    content: str = ""
    children: List['FrameworkNode'] = field(default_factory=list)
    cover_page: dict = field(default_factory=dict)
    index_page: dict = field(default_factory=dict)


class LLMFrameworkGenerator:
    """Generates framework using LLM (3-step split prompts)"""

    JSON_RETRY_SUFFIX = "\n\n【重要】请只输出合法的 JSON 对象，不要输出任何代码、解释或其他内容。"

    PROMPT_FILES = [
        "generate_1_skeleton.txt",
        "generate_2_scoring.txt",
        "generate_3_content.txt",
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

    def generate(self, analysis_result: Dict[str, Any],
                 document_text: str = "",
                 on_progress=None) -> List[FrameworkNode]:
        """
        Generate framework in 3 LLM steps.

        Args:
            analysis_result: Full analysis result (from LLMAnalyzer)
            document_text: Original document text (unused in split mode)
            on_progress: callback(text, current, total)

        Returns:
            List of FrameworkNode
        """
        analysis_json = json.dumps(analysis_result, ensure_ascii=False, indent=2)
        mapping = analysis_result.get("scoring_requirements_mapping", [])
        mapping_json = json.dumps(mapping, ensure_ascii=False, indent=2)
        fmt_templates = analysis_result.get("response_format", {}).get("format_templates", [])
        fmt_json = json.dumps(fmt_templates, ensure_ascii=False, indent=2)

        # --- Step 1: Skeleton ---
        if on_progress:
            on_progress("生成Step1: 构建目录骨架...", 4, 6)
        print("  [1/3] Building skeleton...")

        prompt1 = self._prompts["generate_1_skeleton.txt"]
        prompt1 = prompt1.replace("{analysis_json}", analysis_json)

        skeleton = self._call_and_parse_json(
            step_no=1,
            step_name="skeleton",
            prompt=prompt1,
            label="skeleton",
            max_tokens=8192,
        )

        node_count = self._count_json_nodes(skeleton.get("framework", []))
        print(f"    - skeleton nodes: {node_count}")

        # --- Step 2: Scoring expansion ---
        if on_progress:
            on_progress("生成Step2: 展开评分因素...", 5, 6)
        print("  [2/3] Expanding scoring factors...")

        skeleton_json = json.dumps(skeleton, ensure_ascii=False, indent=2)
        prompt2 = self._prompts["generate_2_scoring.txt"]
        prompt2 = prompt2.replace("{skeleton_json}", skeleton_json)
        prompt2 = prompt2.replace("{scoring_requirements_mapping}", mapping_json)

        scoring_fw = self._call_and_parse_json(
            step_no=2,
            step_name="scoring expansion",
            prompt=prompt2,
            label="scoring",
            max_tokens=16384,
            max_continuations=5,
        )

        node_count2 = self._count_json_nodes(scoring_fw.get("framework", []))
        print(f"    - after scoring expansion: {node_count2} nodes")

        # --- Step 3: Content filling ---
        if on_progress:
            on_progress("生成Step3: 填充内容...", 6, 6)
        print("  [3/3] Filling content...")

        scoring_json = json.dumps(scoring_fw, ensure_ascii=False, indent=2)
        prompt3 = self._prompts["generate_3_content.txt"]
        prompt3 = prompt3.replace("{framework_json}", scoring_json)
        prompt3 = prompt3.replace("{format_templates}", fmt_json)

        final_fw = self._call_and_parse_json(
            step_no=3,
            step_name="content filling",
            prompt=prompt3,
            label="framework",
            max_tokens=16384,
            max_continuations=5,
        )

        # Convert to FrameworkNode objects
        framework = self._convert_to_nodes(final_fw.get("framework", []))

        print(f"  [OK] Framework generation complete")
        total = sum(self._count_all_nodes(n) for n in framework)
        print(f"    - Top-level: {len(framework)}, Total: {total} nodes")

        return framework

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _call_llm(self, prompt: str, max_tokens: int = 8192,
                   max_continuations: int = 3) -> str:
        return call_llm_with_continuation(
            self.llm_provider, prompt,
            max_tokens=max_tokens, max_continuations=max_continuations,
        )

    def _call_and_parse_json(
        self,
        step_no: int,
        step_name: str,
        prompt: str,
        label: str,
        max_tokens: int,
        max_continuations: int = 3,
    ) -> Dict[str, Any]:
        last_error = None
        last_response = ""

        for attempt in range(3):
            prompt_to_use = prompt
            if attempt > 0:
                prompt_to_use += self.JSON_RETRY_SUFFIX

            response = self._call_llm(
                prompt_to_use,
                max_tokens=max_tokens,
                max_continuations=max_continuations,
            )
            try:
                return extract_and_parse_json(response, label=label)
            except Exception as exc:
                last_error = exc
                last_response = response
                if attempt < 2:
                    print(f"  [WARNING] Step {step_no} JSON解析失败，正在重试({attempt + 1}/2)...")

        raise ValueError(
            f"Step {step_no} ({step_name}): LLM returned unparseable JSON. "
            f"Error: {last_error}. Response (first 200 chars): {last_response[:200]!r}"
        ) from last_error

    def _convert_to_nodes(self, framework_list: List[Dict]) -> List[FrameworkNode]:
        nodes = []
        for i, item in enumerate(framework_list):
            if not isinstance(item, dict):
                continue
            title = item.get("title")
            level = item.get("level")
            if title is None or level is None:
                print(f"  [WARNING] Skipping item missing title/level at index {i}")
                continue
            node = FrameworkNode(
                level=level,
                title=str(title),
                content=str(item.get("content", "")),
                children=self._convert_to_nodes(item.get("children", [])),
                cover_page=item.get("cover_page", {}),
                index_page=item.get("index_page", {}),
            )
            nodes.append(node)
        return nodes

    def _count_all_nodes(self, node: FrameworkNode) -> int:
        return 1 + sum(self._count_all_nodes(c) for c in node.children)

    def _count_json_nodes(self, nodes: list) -> int:
        count = 0
        for n in nodes:
            if isinstance(n, dict):
                count += 1 + self._count_json_nodes(n.get("children", []))
        return count
