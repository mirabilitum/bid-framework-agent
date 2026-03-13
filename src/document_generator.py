# -*- coding: utf-8 -*-
"""
Document Generator
Convert a framework JSON / FrameworkNode tree into a formatted Word (.docx) document.

Supported content markers:
  [CENTER]text   → centred paragraph
  [RIGHT]text    → right-aligned paragraph
  [TABLE_START]  → start of table block (first line = headers, separated by |)
  [TABLE_END]    → end of table block
  【xxx】         → bold section header
  Leading spaces → visual indent (2/4/6 spaces for level 1/2/3)
"""

import json
import re
from typing import List, Dict, Any, Optional, Tuple


class DocumentGenerator:
    """Generate Word documents from framework structures."""

    FONT_NAME = "宋体"
    TITLE_SIZE = 14   # 四号 = 14pt
    BODY_SIZE = 14

    _SECTION_HEADER_RE = re.compile(r"^【.+?】.*$")

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #

    def generate(self, framework_nodes, output_path: str, project_name: str = ""):
        """
        Generate Word doc from FrameworkNode list or raw dict.

        Args:
            framework_nodes: list of FrameworkNode, or a dict with "framework" key
            output_path: .docx output path
            project_name: shown on the cover page
        """
        if isinstance(framework_nodes, dict):
            return self.generate_from_json(framework_nodes, output_path, project_name)

        # Convert FrameworkNode list → dict format
        data = {"has_chapter_covers": False, "framework": [self._node_to_dict(n) for n in framework_nodes]}
        # Detect chapter covers
        if any(n.cover_page for n in framework_nodes):
            data["has_chapter_covers"] = True
        self.generate_from_json(data, output_path, project_name)

    def generate_from_json(self, framework_data: Dict[str, Any], output_path: str, project_name: str = ""):
        """Generate Word from a framework dict (JSON-compatible)."""
        from docx import Document

        doc = Document()
        self._set_default_font(doc)

        has_covers = framework_data.get("has_chapter_covers", False)
        for node in framework_data.get("framework", []):
            if has_covers:
                cover = node.get("cover_page")
                if cover:
                    self._add_chapter_cover(doc, cover)
                index = node.get("index_page")
                if index:
                    self._add_index_page(doc, index)
            self._add_node(doc, node)

        doc.save(output_path)
        print(f"  [OK] Word document saved: {output_path}")

    def generate_from_file(self, json_path: str, output_path: str, project_name: str = ""):
        """Load framework JSON file and generate Word document."""
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.generate_from_json(data, output_path, project_name)

    # ------------------------------------------------------------------ #
    #  Internal helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _node_to_dict(node) -> dict:
        d: Dict[str, Any] = {
            "level": node.level,
            "title": node.title,
            "content": node.content,
            "children": [DocumentGenerator._node_to_dict(c) for c in node.children],
        }
        if node.cover_page:
            d["cover_page"] = node.cover_page
        if node.index_page:
            d["index_page"] = node.index_page
        return d

    def _set_default_font(self, doc):
        from docx.shared import Pt

        style = doc.styles["Normal"]
        font = style.font
        font.name = self.FONT_NAME
        font.size = Pt(self.BODY_SIZE)
        style.element.rPr.rFonts.set(
            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}eastAsia",
            self.FONT_NAME,
        )

    def _make_run(self, para, text: str, bold: bool = False, size: Optional[int] = None):
        from docx.shared import Pt

        run = para.add_run(text)
        run.font.name = self.FONT_NAME
        run.font.size = Pt(size or self.BODY_SIZE)
        run.bold = bold
        run.element.rPr.rFonts.set(
            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}eastAsia",
            self.FONT_NAME,
        )
        return run

    def _set_cell_font(self, cell, text: str, bold: bool = False):
        cell.text = ""
        p = cell.paragraphs[0]
        self._make_run(p, text, bold=bold)

    # ---- tables ----

    def _add_table(self, doc, header_line: str, data_lines: List[str]):
        from docx.enum.table import WD_TABLE_ALIGNMENT

        headers = [h.strip() for h in header_line.split("|") if h.strip()]
        if not headers:
            return
        num_cols = len(headers)

        rows_data = []
        for dl in data_lines:
            cells = [c.strip() for c in dl.split("|")]
            while len(cells) < num_cols:
                cells.append("")
            rows_data.append(cells[:num_cols])

        table = doc.add_table(rows=1 + len(rows_data), cols=num_cols)
        table.style = "Table Grid"
        table.alignment = WD_TABLE_ALIGNMENT.CENTER

        for i, h in enumerate(headers):
            self._set_cell_font(table.rows[0].cells[i], h, bold=True)
        for r_idx, row in enumerate(rows_data):
            for c_idx, val in enumerate(row):
                self._set_cell_font(table.rows[r_idx + 1].cells[c_idx], val)

        doc.add_paragraph()

    # ---- content parsing ----

    def _parse_content_blocks(self, content: str) -> List[Tuple]:
        """
        Parse content string into typed blocks:
          ("text", line, align)
          ("table", (header, [data_lines]))
          ("header", line)            — 【xxx】 bold header
        """
        blocks: List[Tuple] = []
        lines = content.split("\n")
        i = 0

        while i < len(lines):
            line = lines[i]

            if line.strip() == "[TABLE_START]":
                table_lines = []
                i += 1
                while i < len(lines) and lines[i].strip() != "[TABLE_END]":
                    table_lines.append(lines[i])
                    i += 1
                if table_lines:
                    blocks.append(("table", (table_lines[0], table_lines[1:])))
                i += 1
                continue

            if self._SECTION_HEADER_RE.match(line.strip()):
                blocks.append(("header", line))
                i += 1
                continue

            align = "left"
            text = line
            if line.startswith("[CENTER]"):
                align, text = "center", line[8:]
            elif line.startswith("[RIGHT]"):
                align, text = "right", line[7:]

            blocks.append(("text", text, align))
            i += 1

        return blocks

    # ---- cover / index pages ----

    def _add_chapter_cover(self, doc, cover: Dict[str, Any]):
        from docx.enum.text import WD_PARAGRAPH_ALIGNMENT

        for _ in range(6):
            doc.add_paragraph()

        p = doc.add_paragraph()
        p.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
        self._make_run(p, cover.get("title", ""), bold=True, size=18)

        subtitle = cover.get("subtitle", "")
        if subtitle:
            p2 = doc.add_paragraph()
            p2.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
            self._make_run(p2, subtitle, bold=True, size=16)

        doc.add_paragraph()
        for field_text in cover.get("fields", []):
            p3 = doc.add_paragraph()
            p3.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
            self._make_run(p3, field_text)
        doc.add_page_break()

    def _add_index_page(self, doc, index: Dict[str, Any]):
        from docx.enum.text import WD_PARAGRAPH_ALIGNMENT

        p = doc.add_paragraph()
        p.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
        self._make_run(p, index.get("title", "索引"), bold=True)
        doc.add_paragraph()

        for item in index.get("items", []):
            p2 = doc.add_paragraph()
            self._make_run(p2, item)

        notes = index.get("notes", "")
        if notes:
            doc.add_paragraph()
            p3 = doc.add_paragraph()
            self._make_run(p3, notes)
        doc.add_page_break()

    # ---- recursive node renderer ----

    def _add_node(self, doc, node: Dict[str, Any]):
        from docx.enum.text import WD_PARAGRAPH_ALIGNMENT

        title = node.get("title", "")
        content = node.get("content", "")
        children = node.get("children", [])

        # Title
        title_align = None
        if title.startswith("[CENTER]"):
            title, title_align = title[8:], "center"

        p_title = doc.add_paragraph()
        if title_align == "center":
            p_title.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
        self._make_run(p_title, title, bold=True)

        # Content blocks
        if content:
            for block in self._parse_content_blocks(content):
                btype = block[0]
                if btype == "table":
                    header_line, data_lines = block[1]
                    self._add_table(doc, header_line, data_lines)
                elif btype == "header":
                    p = doc.add_paragraph()
                    self._make_run(p, block[1], bold=True)
                else:
                    text, align = block[1], block[2] if len(block) > 2 else "left"
                    p = doc.add_paragraph()
                    if align == "center":
                        p.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
                    elif align == "right":
                        p.alignment = WD_PARAGRAPH_ALIGNMENT.RIGHT
                    self._make_run(p, text)

        for child in children:
            self._add_node(doc, child)
