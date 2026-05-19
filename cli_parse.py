#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Parse a procurement document and output extracted data as JSON.

Usage:
    python cli_parse.py <input_file> [output_dir]

Outputs:
    <output_dir>/parsed.json   — text, tables, format paragraphs, page_count
"""
import sys
import os
import json

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(__file__))
from src.document_parser import DocumentParser


def main():
    if len(sys.argv) < 2:
        print("Usage: cli_parse.py <input_file> [output_dir]")
        sys.exit(1)

    input_file = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "output"
    os.makedirs(output_dir, exist_ok=True)

    parser = DocumentParser(input_file)
    full_text, paragraphs, tables = parser.parse()

    result = {
        "file": os.path.basename(input_file),
        "ext": parser.ext,
        "full_text": full_text,
        "tables": tables,
    }

    # PDF: report total page count (for LLM-driven screenshot selection)
    if parser.ext == ".pdf":
        result["page_count"] = parser.page_count

    # DOCX: report paragraph count (format extraction deferred to LLM-driven step)
    if parser.ext == ".docx":
        from docx import Document
        doc = Document(input_file)
        result["paragraph_count"] = len(doc.paragraphs)

    # Format tables as readable text (for LLM consumption)
    tables_text_parts = []
    for i, table in enumerate(tables[:10]):
        tables_text_parts.append(f"\n表格 {i + 1}:")
        for row in table:
            tables_text_parts.append(" | ".join(str(c) for c in row))
        tables_text_parts.append("")
    if len(tables) > 10:
        tables_text_parts.append(f"\n... 还有 {len(tables) - 10} 个表格未显示")
    result["tables_text"] = "\n".join(tables_text_parts) if tables_text_parts else "无表格"

    # Save JSON
    json_path = os.path.join(output_dir, "parsed.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\nParsed: {len(full_text)} chars, {len(tables)} tables")
    if parser.ext == ".pdf":
        print(f"Total pages: {result['page_count']}")
    print(f"Output: {json_path}")


if __name__ == "__main__":
    main()
