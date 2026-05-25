# -*- coding: utf-8 -*-
"""
Framework Checker
Validates a generated framework.json against its analysis.json.

Pure Python checks — no LLM needed. Produces a structured problem report.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Problem:
    """A single validation problem."""
    severity: str   # "error" | "warning" | "info"
    check: str      # check function name
    node_path: str   # human-readable path to the problematic node
    message: str     # description


@dataclass
class CheckReport:
    """Aggregated check results."""
    problems: List[Problem] = field(default_factory=list)

    @property
    def errors(self) -> int:
        return sum(1 for p in self.problems if p.severity == "error")

    @property
    def warnings(self) -> int:
        return sum(1 for p in self.problems if p.severity == "warning")

    @property
    def info_count(self) -> int:
        return sum(1 for p in self.problems if p.severity == "info")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "problems": [
                {"severity": p.severity, "check": p.check,
                 "node_path": p.node_path, "message": p.message}
                for p in self.problems
            ],
            "summary": {
                "errors": self.errors,
                "warnings": self.warnings,
                "info": self.info_count,
            },
        }


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------

def _collect_titles(nodes: List[Dict], prefix: str = "") -> List[str]:
    """Recursively collect all node titles with path context."""
    titles = []
    for node in nodes:
        title = node.get("title", "").replace("[CENTER]", "").replace("[RIGHT]", "").strip()
        path = f"{prefix} > {title}" if prefix else title
        titles.append(path)
        titles.extend(_collect_titles(node.get("children", []), path))
    return titles


def _walk_nodes(nodes: List[Dict], prefix: str = ""):
    """Yield (node, path) for every node in the tree."""
    for node in nodes:
        title = node.get("title", "").replace("[CENTER]", "").replace("[RIGHT]", "").strip()
        path = f"{prefix} > {title}" if prefix else title
        yield node, path
        yield from _walk_nodes(node.get("children", []), path)


def check_format_templates_present(
    framework: List[Dict], analysis: Dict[str, Any]
) -> List[Problem]:
    """Check that every format_template has a corresponding node in the framework."""
    problems = []
    templates = analysis.get("response_format", {}).get("format_templates", [])
    if not templates:
        return problems

    # Collect all titles (normalized)
    all_titles = _collect_titles(framework)
    all_titles_norm = set()
    for t in all_titles:
        # Take the last segment of the path
        last = t.split(" > ")[-1] if " > " in t else t
        norm = re.sub(r'[．.、，·\s]', '', last)
        all_titles_norm.add(norm)

    # Skip cover-type templates — they render as standalone pages, not framework nodes
    skip_types = {"cover_format", "cover"}

    for tpl in templates:
        if tpl.get("content_type") in skip_types:
            continue
        tpl_title = tpl.get("title", "")
        if "封面" in tpl_title:
            continue
        tpl_norm = re.sub(r'[．.、，·\s]', '', tpl_title)
        if not any(tpl_norm in t or t in tpl_norm for t in all_titles_norm if len(t) >= 2):
            problems.append(Problem(
                severity="error",
                check="format_templates_present",
                node_path="",
                message=f"格式模板「{tpl_title}」在框架中没有对应节点",
            ))

    return problems


def check_scoring_factors_expanded(
    framework: List[Dict], analysis: Dict[str, Any]
) -> List[Problem]:
    """Check that all non-price, expandable scoring factors appear in the framework."""
    problems = []
    mapping = analysis.get("scoring_requirements_mapping", [])
    if not mapping:
        # Fall back to scoring_factors
        factors = analysis.get("scoring_factors", [])
        mapping = [{"scoring_factor": f["name"], "category": f["category"],
                     "expand_as_children": True} for f in factors if f["category"] != "price"]

    # Collect all titles for matching
    all_titles_text = " ".join(_collect_titles(framework))

    for item in mapping:
        if item.get("category") == "price":
            continue
        name = item.get("scoring_factor", "")
        if not name:
            continue
        # Check if name appears anywhere in the framework titles
        if name not in all_titles_text:
            problems.append(Problem(
                severity="error",
                check="scoring_factors_expanded",
                node_path="",
                message=f"评分因素「{name}」未在框架中展开",
            ))

    return problems


def check_title_content_duplication(framework: List[Dict]) -> List[Problem]:
    """Check that title and content do not duplicate each other."""
    problems = []
    for node, path in _walk_nodes(framework):
        title = node.get("title", "").replace("[CENTER]", "").replace("[RIGHT]", "").strip()
        content = node.get("content", "")
        if not title or not content:
            continue
        # Check if content starts with the same text as title
        first_line = content.split("\n")[0].replace("[CENTER]", "").replace("[RIGHT]", "").strip()
        title_clean = re.sub(r'[．.、，·\s]', '', title)
        first_clean = re.sub(r'[．.、，·\s]', '', first_line)
        if title_clean and first_clean and len(title_clean) >= 2:
            if title_clean in first_clean or first_clean in title_clean:
                problems.append(Problem(
                    severity="warning",
                    check="title_content_duplication",
                    node_path=path,
                    message=f"标题与内容首行重复：title=\"{title}\" content_first_line=\"{first_line}\"",
                ))

    return problems


def check_level_hierarchy(framework: List[Dict]) -> List[Problem]:
    """Check that level values are continuous (no jumps like 1→3)."""
    problems = []

    def _check(nodes: List[Dict], parent_level: int, prefix: str):
        for node in nodes:
            level = node.get("level", 99)
            title = node.get("title", "").replace("[CENTER]", "").replace("[RIGHT]", "").strip()
            path = f"{prefix} > {title}" if prefix else title

            if level > parent_level + 1:
                problems.append(Problem(
                    severity="warning",
                    check="level_hierarchy",
                    node_path=path,
                    message=f"层级跳跃：父节点 level={parent_level}，当前节点 level={level}（应为 {parent_level + 1}）",
                ))

            _check(node.get("children", []), level, path)

    _check(framework, 0, "")
    return problems


def check_table_markers(framework: List[Dict]) -> List[Problem]:
    """Check that [TABLE_START] and [TABLE_END] markers are properly paired."""
    problems = []
    for node, path in _walk_nodes(framework):
        content = node.get("content", "")
        if not content:
            continue
        starts = content.count("[TABLE_START]")
        ends = content.count("[TABLE_END]")
        if starts != ends:
            problems.append(Problem(
                severity="error",
                check="table_markers",
                node_path=path,
                message=f"表格标记不配对：[TABLE_START]={starts}个，[TABLE_END]={ends}个",
            ))

    return problems


def check_empty_nodes(framework: List[Dict]) -> List[Problem]:
    """Check for leaf nodes with no content, no children, and no elements."""
    problems = []
    for node, path in _walk_nodes(framework):
        children = node.get("children", [])
        content = node.get("content", "")
        elements = node.get("elements")
        paragraphs = node.get("paragraphs")

        if not children and not content and not elements and not paragraphs:
            # is_free_form leaf with no content is expected (user fills it)
            if node.get("is_free_form"):
                continue
            problems.append(Problem(
                severity="info",
                check="empty_nodes",
                node_path=path,
                message="叶子节点无内容（content为空，无children/elements）",
            ))

    return problems


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class FrameworkChecker:
    """Run all checks on a framework + analysis pair."""

    _CHECKS = [
        check_format_templates_present,
        check_scoring_factors_expanded,
        check_title_content_duplication,
        check_level_hierarchy,
        check_table_markers,
        check_empty_nodes,
    ]

    def check(self, framework_data: Dict[str, Any],
              analysis_data: Dict[str, Any]) -> CheckReport:
        """Run all checks and return a report."""
        framework = framework_data.get("framework", [])
        report = CheckReport()

        for check_fn in self._CHECKS:
            try:
                # Some checks need analysis, some only need framework
                import inspect
                params = inspect.signature(check_fn).parameters
                if "analysis" in params:
                    problems = check_fn(framework, analysis_data)
                else:
                    problems = check_fn(framework)
            except Exception as e:
                logger.warning("Check %s failed: %s", check_fn.__name__, e)
                problems = [Problem(
                    severity="warning",
                    check=check_fn.__name__,
                    node_path="",
                    message=f"检查执行失败: {e}",
                )]
            report.problems.extend(problems)

        logger.info(
            "Check complete: %d errors, %d warnings, %d info",
            report.errors, report.warnings, report.info_count,
        )
        return report
