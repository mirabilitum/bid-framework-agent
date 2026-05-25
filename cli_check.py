#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validate a framework.json against its analysis.json.

Usage:
    python cli_check.py <framework.json> <analysis.json> [-o check_report.json]
"""
import sys
import os
import json
import logging
import argparse

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(level=logging.INFO, format="  %(message)s")

sys.path.insert(0, os.path.dirname(__file__))
from src.framework_checker import FrameworkChecker


def main():
    parser = argparse.ArgumentParser(description="Validate framework.json against analysis.json")
    parser.add_argument("framework", help="Path to framework.json")
    parser.add_argument("analysis", help="Path to analysis.json")
    parser.add_argument("-o", "--output", help="Save full report to JSON file")
    args = parser.parse_args()

    try:
        with open(args.framework, "r", encoding="utf-8") as f:
            framework_data = json.load(f)
    except FileNotFoundError:
        print(f"Error: framework file not found: {args.framework}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: invalid JSON in {args.framework}: {e}")
        sys.exit(1)

    try:
        with open(args.analysis, "r", encoding="utf-8") as f:
            analysis_data = json.load(f)
    except FileNotFoundError:
        print(f"Error: analysis file not found: {args.analysis}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: invalid JSON in {args.analysis}: {e}")
        sys.exit(1)

    checker = FrameworkChecker()
    report = checker.check(framework_data, analysis_data)

    # Print summary
    report_dict = report.to_dict()
    summary = report_dict["summary"]
    print(f"\n  Check result: {summary['errors']} errors, {summary['warnings']} warnings, {summary['info']} info")

    for p in report_dict["problems"]:
        icon = {"error": "X", "warning": "!", "info": "i"}[p["severity"]]
        path = f" @ {p['node_path']}" if p["node_path"] else ""
        print(f"  [{icon}] [{p['check']}]{path}: {p['message']}")

    # Save report
    if args.output:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report_dict, f, ensure_ascii=False, indent=2)
        print(f"\n  Report saved: {args.output}")

    sys.exit(1 if summary["errors"] > 0 else 0)


if __name__ == "__main__":
    main()
