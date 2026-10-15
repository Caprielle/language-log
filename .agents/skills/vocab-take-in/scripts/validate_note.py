#!/usr/bin/env python3
"""Read-only validation of vocab-take-in tables. YAML is checked separately."""

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path


PRO_HEADING = "## 一、专业词汇"
OTHER_HEADING = "## 二、其他词汇"
PRO_COLUMNS = ["英语", "日语", "中文", "简单中文解释"]
OTHER_COLUMNS = ["外文", "中文"]
FOOTER = "† 表示该内容不在对话中，由助手补充。"


class NoteError(ValueError):
    pass


def parse_row(line, number):
    """Split a GFM row, respecting an odd run of backslashes before a pipe."""
    cells, buffer, backslashes = [], [], 0
    for char in line.strip():
        if char == "|" and backslashes % 2 == 0:
            cells.append("".join(buffer).strip())
            buffer = []
        else:
            buffer.append(char)
        backslashes = backslashes + 1 if char == "\\" else 0
    cells.append("".join(buffer).strip())
    if len(cells) < 3 or cells[0] or cells[-1]:
        raise NoteError(f"第 {number} 行：表格须以未转义的竖线开始和结束")
    return cells[1:-1]


def canonical_term(value):
    value = value.removesuffix("†").strip().replace(r"\|", "|")
    value = unicodedata.normalize("NFC", value)
    return "" if value == "待定" else value


def validate_note(text):
    if re.search(r"\{\{[^\n]*?\}\}", text):
        raise NoteError("文档含未填充的模板变量")
    raw = text.splitlines()
    if not raw or raw[0] != "---":
        raise NoteError("文档须以 YAML 属性区开始；YAML 内容另行解析核验")
    try:
        end = raw.index("---", 1)
    except ValueError:
        raise NoteError("YAML 属性区缺少结束标记") from None
    if not any(line.strip() for line in raw[1:end]):
        raise NoteError("YAML 属性区不能为空")
    lines = [(i + 1, line.strip()) for i, line in enumerate(raw)
             if i > end and line.strip()]
    if not lines or not lines[0][1].startswith("# ") or not lines[0][1][2:].strip():
        raise NoteError("缺少文档主标题")
    cursor, seen, counts = 1, {}, []

    def expect(expected):
        nonlocal cursor
        if cursor >= len(lines) or lines[cursor][1] != expected:
            raise NoteError(f"固定格式缺少或错置：{expected}")
        cursor += 1

    def check_terms(cells, number, professional):
        positions = (0, 1) if professional else (0,)
        keys = set()
        for index in positions:
            value = cells[index]
            if any(mark in value for mark in ("`", "**", "[[", "](")):
                raise NoteError(f"第 {number} 行：词形须用纯文本")
            key = canonical_term(value)
            if key:
                keys.add(key)
        if not keys:
            raise NoteError(f"第 {number} 行：至少需要一个已知外文词形")
        for key in keys:
            if key in seen:
                raise NoteError(f"重复词形 {key!r}：第 {seen[key]}、{number} 行；请依据语境复核草稿")
        for key in keys:
            seen[key] = number

    for heading, columns, terminal, professional in (
        (PRO_HEADING, PRO_COLUMNS, OTHER_HEADING, True),
        (OTHER_HEADING, OTHER_COLUMNS, FOOTER, False),
    ):
        expect(heading)
        if cursor + 1 >= len(lines):
            raise NoteError(f"{heading} 缺少表头或分隔行")
        number, header = lines[cursor]
        if parse_row(header, number) != columns:
            raise NoteError(f"第 {number} 行：表头须为 {columns}")
        cursor += 1
        number, separator = lines[cursor]
        if parse_row(separator, number) != ["---"] * len(columns):
            raise NoteError(f"第 {number} 行：表格分隔行须保持模板格式")
        cursor += 1
        count = 0
        while cursor < len(lines) and lines[cursor][1] != terminal:
            number, row = lines[cursor]
            cells = parse_row(row, number)
            if len(cells) != len(columns):
                raise NoteError(f"第 {number} 行：须有 {len(columns)} 列；内容中的竖线须转义")
            if any(not cell for cell in cells):
                raise NoteError(f"第 {number} 行：存在空单元格，无法确定的项应填待定")
            for cell in cells:
                if "†" in cell and (not professional or cell.count("†") != 1 or not cell.endswith("†")):
                    raise NoteError(f"第 {number} 行：补充标记只允许放在专业表单元格末尾")
            check_terms(cells, number, professional)
            count += 1
            cursor += 1
        counts.append(count)
    expect(FOOTER)
    if cursor != len(lines):
        raise NoteError("固定两表之外出现额外正文")
    if not sum(counts):
        raise NoteError("没有生词，不应生成空文档")
    return {"status": "passed", "professional": counts[0],
            "other": counts[1], "duplicates": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("note", type=Path, help="A UTF-8 Markdown draft; never modified")
    args = parser.parse_args()
    try:
        result = validate_note(args.note.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, NoteError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
