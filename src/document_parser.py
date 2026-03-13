# -*- coding: utf-8 -*-
"""
Document Parser
Parse procurement documents (PDF/DOCX/DOC) and extract text, paragraphs, and tables.
Supports PDF page screenshots for vision-based format detection.
"""

import os
import base64
from typing import Tuple, List, Optional


class DocumentParser:
    """Parse procurement documents (PDF / DOCX / DOC)."""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.ext = os.path.splitext(file_path)[1].lower()

    def parse(self) -> Tuple[str, List[dict], List[List[List[str]]]]:
        """
        Parse document.

        Returns:
            (full_text, paragraphs, tables)
            - full_text: concatenated document text
            - paragraphs: list of {"text": ..., "style": ...}
            - tables: list of tables, each table = list of rows, each row = list of cell strings
        """
        if self.ext == ".pdf":
            return self._parse_pdf()
        elif self.ext == ".docx":
            return self._parse_docx()
        elif self.ext == ".doc":
            return self._parse_doc()
        else:
            raise ValueError(f"Unsupported format: {self.ext}")

    # ------------------------------------------------------------------ #
    #  PDF page screenshots for vision-based format recognition
    # ------------------------------------------------------------------ #

    def screenshot_pages(self, page_numbers: List[int], dpi: int = 150) -> List[dict]:
        """
        Screenshot specified PDF pages as base64 PNG images.

        Args:
            page_numbers: 0-based page indices
            dpi: resolution (150 = good quality/token balance)

        Returns:
            [{"page": N, "data": base64_str, "media_type": "image/png"}, ...]
        """
        if self.ext != ".pdf":
            raise ValueError("screenshot_pages only supports PDF files")

        import fitz  # PyMuPDF

        doc = fitz.open(self.file_path)
        images = []
        for page_num in page_numbers:
            if page_num < 0 or page_num >= len(doc):
                continue
            page = doc[page_num]
            mat = fitz.Matrix(dpi / 72, dpi / 72)
            pix = page.get_pixmap(matrix=mat)
            png_data = pix.tobytes("png")
            images.append({
                "page": page_num,
                "data": base64.b64encode(png_data).decode("utf-8"),
                "media_type": "image/png",
            })
        doc.close()
        return images

    def find_format_template_pages(self) -> List[int]:
        """
        Find page numbers containing format templates
        (e.g. chapter titled "投标文件格式" / "响应文件格式").
        Returns 0-based page indices.
        """
        if self.ext != ".pdf":
            return []

        import fitz

        doc = fitz.open(self.file_path)
        pages: List[int] = []
        in_section = False

        section_keywords = ["投标文件格式", "响应文件格式", "电子投标文件格式", "附件格式"]
        chapter_keywords = ["第七章", "第六章", "第八章", "附件"]

        for i in range(len(doc)):
            text = doc[i].get_text()
            if any(kw in text for kw in section_keywords):
                if any(kw in text for kw in chapter_keywords):
                    in_section = True
            if in_section:
                pages.append(i)

        doc.close()
        return pages

    # ------------------------------------------------------------------ #
    #  Format-specific parsers
    # ------------------------------------------------------------------ #

    def _parse_pdf(self) -> Tuple[str, List[dict], List]:
        import fitz

        doc = fitz.open(self.file_path)
        full_text = "\n".join(page.get_text() for page in doc)
        doc.close()

        if len(full_text.strip()) < 200:
            raise ValueError("PDF text too short — might be a scanned image")

        paragraphs = [{"text": full_text, "style": "Normal"}]
        return full_text, paragraphs, []

    def _parse_docx(self) -> Tuple[str, List[dict], List[List[List[str]]]]:
        from docx import Document

        doc = Document(self.file_path)

        paragraphs = []
        for p in doc.paragraphs:
            text = p.text.strip()
            if text:
                paragraphs.append({
                    "text": text,
                    "style": p.style.name if p.style else "Normal",
                })

        full_text = "\n".join(p["text"] for p in paragraphs)

        tables = []
        for table in doc.tables:
            rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
            tables.append(rows)

        return full_text, paragraphs, tables

    def _parse_doc(self) -> Tuple[str, List[dict], List]:
        """Parse legacy .doc (requires Windows + MS Word COM)."""
        try:
            import win32com.client
            import pythoncom
        except ImportError:
            raise ImportError(
                "pywin32 is required for .doc parsing on Windows. "
                "Install with: pip install pywin32"
            )

        pythoncom.CoInitialize()
        try:
            word = win32com.client.Dispatch("Word.Application")
            word.Visible = False
            doc = word.Documents.Open(os.path.abspath(self.file_path))
            full_text = doc.Content.Text
            doc.Close(False)
            word.Quit()
        finally:
            pythoncom.CoUninitialize()

        paragraphs = [{"text": full_text, "style": "Normal"}]
        return full_text, paragraphs, []
