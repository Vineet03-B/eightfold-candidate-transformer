#!/usr/bin/env python3
"""
Multi-Source Candidate Data Transformer — CLI
Usage:
  python cli.py --csv sample_inputs/recruiter.csv \
                --ats sample_inputs/ats.json \
                --github https://github.com/torvalds \
                --resume sample_inputs/resume.txt \
                --notes sample_inputs/notes.txt \
                --config sample_inputs/config.json \
                --output output_profile.json
"""

import argparse
import json
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from transformer import run_pipeline


def read_file(path: str) -> str:
    if not path:
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        print(f"[WARN] File not found: {path}", file=sys.stderr)
        return ""


def main():
    parser = argparse.ArgumentParser(description="Multi-Source Candidate Data Transformer")
    parser.add_argument("--csv",    help="Recruiter CSV export file path")
    parser.add_argument("--ats",    help="ATS JSON blob file path")
    parser.add_argument("--github", help="GitHub profile URL or username")
    parser.add_argument("--linkedin", help="LinkedIn data JSON file path")
    parser.add_argument("--resume", help="Resume plain text file path")
    parser.add_argument("--notes",  help="Recruiter notes .txt file path")
    parser.add_argument("--config", help="Runtime output config JSON file path")
    parser.add_argument("--output", help="Output file path (default: stdout)")
    parser.add_argument("--pretty", action="store_true", default=True,
                        help="Pretty-print JSON output")
    args = parser.parse_args()

    sources = {}
    if args.csv:
        sources["csv_text"] = read_file(args.csv)
    if args.ats:
        sources["ats_json_text"] = read_file(args.ats)
    if args.github:
        sources["github_url"] = args.github
    if args.linkedin:
        raw = read_file(args.linkedin)
        try:
            sources["linkedin_data"] = json.loads(raw)
        except Exception:
            print("[WARN] Could not parse LinkedIn JSON", file=sys.stderr)
    if args.resume:
        sources["resume_text"] = read_file(args.resume)
    if args.notes:
        sources["recruiter_notes"] = read_file(args.notes)

    if not sources:
        print("[ERROR] Provide at least one source input.", file=sys.stderr)
        parser.print_help()
        sys.exit(1)

    config = None
    if args.config:
        raw_cfg = read_file(args.config)
        try:
            config = json.loads(raw_cfg)
        except Exception:
            print("[WARN] Could not parse config JSON; using default schema.", file=sys.stderr)

    result = run_pipeline(sources, config)

    indent = 2 if args.pretty else None
    output_str = json.dumps(result, indent=indent, ensure_ascii=False)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_str)
        print(f"[OK] Profile written to {args.output}", file=sys.stderr)
    else:
        print(output_str)


if __name__ == "__main__":
    main()
