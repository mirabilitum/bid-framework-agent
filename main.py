#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bid Framework Generator Agent — CLI entry point.

Usage:
    python main.py --input 招标文件.pdf --provider claude
    python main.py --input 招标文件.pdf --provider kimi --api-key sk-xxx
    python main.py --input 招标文件.pdf --provider mock
"""

import sys
import os
import argparse

# Ensure UTF-8 output on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

# Load .env file if present (simple key=value, no dependencies)
_env_file = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_env_file):
    with open(_env_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

from src.agent import BidFrameworkAgent
from src.llm_provider import list_providers


def main():
    providers = list_providers()

    parser = argparse.ArgumentParser(
        description="Bid Framework Generator Agent — convert procurement documents to bid response outlines (Word).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  python main.py -i 招标文件.pdf -p claude
  python main.py -i 招标文件.pdf -p openai --model gpt-4o
  python main.py -i 招标文件.pdf -p kimi --api-key sk-xxx
  python main.py -i 招标文件.pdf -p deepseek
  python main.py -i 招标文件.pdf -p ollama --model llama3
  python main.py -i 招标文件.pdf -p mock          # test without API key

Supported providers:
  claude (anthropic)       Anthropic Claude   — env: ANTHROPIC_API_KEY
  openai (gpt)             OpenAI GPT         — env: OPENAI_API_KEY
  kimi (moonshot)          Moonshot Kimi      — env: OPENAI_COMPATIBLE_API_KEY
  deepseek                 DeepSeek           — env: OPENAI_COMPATIBLE_API_KEY
  gemini                   Google Gemini      — env: OPENAI_COMPATIBLE_API_KEY
  ollama (local)           Local Ollama       — no key needed
  qwen                     Alibaba Qwen       — env: QWEN_API_KEY
  openai-compatible        Any OpenAI-compat  — env: OPENAI_COMPATIBLE_API_BASE + API_KEY
  mock                     Test mode          — no key needed
""",
    )
    parser.add_argument("--input", "-i", help="Input procurement document (PDF/DOCX/DOC)")
    parser.add_argument("--output", "-o", help="Output Word file path (single package)")
    parser.add_argument("--output-dir", "-d", help="Output directory (multi-package)")
    parser.add_argument("--provider", "-p", default="claude", help=f"LLM provider (default: claude)")
    parser.add_argument("--api-key", help="API key (or set via environment variable)")
    parser.add_argument("--model", help="Override default model (e.g. gpt-4o, moonshot-v1-128k)")
    parser.add_argument("--base-url", help="API base URL (for openai-compatible provider)")
    parser.add_argument("--packages", help="Package IDs to process, comma-separated (e.g. 1,2)")
    parser.add_argument("--save-json", action="store_true", help="Save intermediate analysis/framework JSON")
    parser.add_argument("--list-providers", action="store_true", help="List all available providers and exit")

    args = parser.parse_args()

    if args.list_providers:
        print("Available providers:")
        for p in providers:
            print(f"  {p}")
        return

    if not args.input:
        parser.error("--input/-i is required")

    packages = None
    if args.packages:
        packages = [int(x.strip()) for x in args.packages.split(",")]

    provider_kwargs = {}
    if args.model:
        provider_kwargs["model"] = args.model
    if args.base_url:
        provider_kwargs["base_url"] = args.base_url

    agent = BidFrameworkAgent(
        llm_provider=args.provider,
        api_key=args.api_key,
        **provider_kwargs,
    )

    agent.run(
        input_file=args.input,
        output_file=args.output,
        output_dir=args.output_dir,
        packages=packages,
        save_intermediate=args.save_json,
    )


if __name__ == "__main__":
    main()
