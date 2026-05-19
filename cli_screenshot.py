#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Screenshot specific pages from a PDF file.

Usage:
    python cli_screenshot.py <pdf_file> <page_numbers> [output_dir] [--dpi N]

    page_numbers: comma-separated, 1-based (e.g. "37,38,39,40")

Examples:
    python cli_screenshot.py doc.pdf 37,38,39 ./output
    python cli_screenshot.py doc.pdf 37-45 ./output --dpi 150
"""
import sys
import os

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")


def parse_page_spec(spec: str) -> list[int]:
    """Parse page specification like '37,38,39' or '37-45' into 1-based page list."""
    pages = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            pages.extend(range(int(start), int(end) + 1))
        else:
            pages.append(int(part))
    return pages


def main():
    if len(sys.argv) < 3:
        print("Usage: cli_screenshot.py <pdf_file> <page_numbers> [output_dir] [--dpi N]")
        print("  page_numbers: 1-based, comma-separated or range (e.g. '37,38,39' or '37-45')")
        sys.exit(1)

    pdf_file = sys.argv[1]
    page_spec = sys.argv[2]

    # Parse optional args
    output_dir = "output"
    dpi = 100
    i = 3
    while i < len(sys.argv):
        if sys.argv[i] == "--dpi" and i + 1 < len(sys.argv):
            dpi = int(sys.argv[i + 1])
            i += 2
        else:
            output_dir = sys.argv[i]
            i += 1

    os.makedirs(output_dir, exist_ok=True)

    # Parse page numbers (1-based input → 0-based for fitz)
    pages_1based = parse_page_spec(page_spec)

    import fitz
    doc = fitz.open(pdf_file)
    total = len(doc)

    # Validate all requested page numbers before processing
    invalid = [p for p in pages_1based if p < 1 or p > total]
    if invalid:
        print(f"Error: page(s) out of range {invalid} — PDF has {total} page(s) (1-{total})")
        doc.close()
        sys.exit(1)

    output_paths = []
    for page_num in pages_1based:
        page_idx = page_num - 1  # convert to 0-based
        if page_idx < 0 or page_idx >= total:
            print(f"  [SKIP] Page {page_num} out of range (total: {total})")
            continue
        page = doc[page_idx]
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        png_path = os.path.join(output_dir, f"format_page_{page_num}.png")
        pix.save(png_path)
        output_paths.append(os.path.abspath(png_path))
        print(f"  Page {page_num} -> {png_path}")

    doc.close()
    print(f"\nScreenshots: {len(output_paths)} pages saved to {output_dir}")


if __name__ == "__main__":
    main()
