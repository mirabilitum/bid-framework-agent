#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Extract paragraph formatting from a DOCX format template section.

Returns a flat list of paragraphs with formatting attributes.
The LLM decides how to group them into templates.

Usage:
    python cli_extract_format.py <docx_file> <section_keyword> <output_dir>

    section_keyword: text to locate the format section start
                     (e.g. "投标文件格式", "响应文件格式", "第七章")

Examples:
    python cli_extract_format.py doc.docx "投标文件格式" ./output
    python cli_extract_format.py doc.docx "第七章" ./output
"""
import sys
import os
import json

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(__file__))
from src.document_parser import DocumentParser


def main():
    if len(sys.argv) < 4:
        print("Usage: cli_extract_format.py <docx_file> <section_keyword> <output_dir>")
        print('  section_keyword: e.g. "投标文件格式", "响应文件格式", "第七章"')
        sys.exit(1)

    docx_file = sys.argv[1]
    section_keyword = sys.argv[2]
    output_dir = sys.argv[3]
    os.makedirs(output_dir, exist_ok=True)

    parser = DocumentParser(docx_file)
    paragraphs = parser.extract_format_section_paragraphs(start_keyword=section_keyword)

    if not paragraphs:
        print(f"No paragraphs found with keyword: {section_keyword}")
        sys.exit(0)

    # Save
    out_path = os.path.join(output_dir, "docx_format_paragraphs.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(paragraphs, f, ensure_ascii=False, indent=2)

    # Stats
    non_empty = sum(1 for p in paragraphs if p["text"].strip())
    centered = sum(1 for p in paragraphs if p["align"] == "center")
    right = sum(1 for p in paragraphs if p["align"] == "right")
    print(f"Extracted {len(paragraphs)} paragraphs ({non_empty} non-empty, {centered} centered, {right} right-aligned)")
    print(f"Output: {out_path}")


if __name__ == "__main__":
    main()
