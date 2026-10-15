#!/usr/bin/env python3
"""Validate and save a draft to language-log/records with a daily sequence."""

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

from validate_note import NoteError, validate_note


RECORDS_DIR = Path(r"D:\z.repos\language-log\records")


def checked_date(value):
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValueError("日期须为有效的 YYYY-MM-DD") from None
    if parsed.isoformat() != value:
        raise ValueError("日期须为有效的 YYYY-MM-DD")
    return value


def next_filename(records_dir, day):
    """Inspect names only; gaps are not reused and other days do not count."""
    day = checked_date(day)
    pattern = re.compile(re.escape(day) + r"-([0-9]{2,})\.md")
    maximum = 0
    for entry in records_dir.iterdir():
        match = pattern.fullmatch(entry.name)
        if match and entry.is_file():
            maximum = max(maximum, int(match.group(1)))
    return records_dir / f"{day}-{maximum + 1:02d}.md"


def save_note(draft, records_dir, day):
    day = checked_date(day)
    data = draft.read_bytes()
    counts = validate_note(data.decode("utf-8"))
    records_dir.mkdir(parents=True, exist_ok=True)
    target = next_filename(records_dir, day)
    # Exclusive creation is the final protection against a concurrent save.
    with target.open("xb") as stream:
        if stream.write(data) != len(data):
            raise OSError(f"文件未完整写入：{target}")
    if target.read_bytes() != data:
        raise OSError(f"落盘内容与草稿不一致：{target}")
    return {**counts, "path": str(target.resolve())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("draft", type=Path, help="A locally prepared UTF-8 Markdown draft")
    parser.add_argument("--date", required=True, help="Current client date in Asia/Shanghai: YYYY-MM-DD")
    args = parser.parse_args()
    try:
        result = save_note(args.draft, RECORDS_DIR, args.date)
    except (OSError, UnicodeError, NoteError, ValueError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
