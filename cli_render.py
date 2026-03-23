#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Render a framework JSON file into a Word document.

Usage:
    python cli_render.py <framework.json> <output.docx> [project_name]
"""
import sys
import os
import logging

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(level=logging.INFO, format="  %(message)s")

sys.path.insert(0, os.path.dirname(__file__))
from src.document_generator import DocumentGenerator


def main():
    if len(sys.argv) < 3:
        print("Usage: cli_render.py <framework.json> <output.docx> [project_name]")
        sys.exit(1)

    json_path = sys.argv[1]
    output_path = sys.argv[2]
    project_name = sys.argv[3] if len(sys.argv) > 3 else ""

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    gen = DocumentGenerator()
    gen.generate_from_file(json_path, output_path, project_name)
    print(f"Done: {output_path}")


if __name__ == "__main__":
    main()
