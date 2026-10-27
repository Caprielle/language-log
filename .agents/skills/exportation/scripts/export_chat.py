"""Losslessly render a validated reader snapshot; no ChatGPT reader is bundled."""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path


DESTINATION = Path(r"D:\z.repos\language-log\_local\inbox\chatgpt")
TOP_KEYS = {
    "schema_version", "source", "conversation_id", "title", "reader",
    "read_reference", "has_more_before", "has_more_after", "truncated",
    "export_request_id", "messages",
}
MESSAGE_KEYS = {"id", "parent_id", "role", "content_type", "content", "status"}
LABELS = {"user": "用户", "assistant": "助手"}


class ExportError(ValueError):
    """A validation failure, with no implied successful export."""


def require(condition, message):
    if not condition:
        raise ExportError(message)


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicate JSON key")
        result[key] = value
    return result


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def validate_snapshot(snapshot):
    require(isinstance(snapshot, dict) and set(snapshot) == TOP_KEYS,
            "Snapshot fields do not match protocol v1")
    require(type(snapshot["schema_version"]) is int and snapshot["schema_version"] == 1,
            "Unsupported snapshot version")
    require(snapshot["source"] == "chatgpt-conversation", "Not a ChatGPT snapshot")
    identifier = snapshot["conversation_id"]
    require(isinstance(identifier, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,100}", identifier),
            "Conversation ID cannot be used safely in a filename")
    require(isinstance(snapshot["title"], str), "Title must be original text or empty")
    for field in ("reader", "read_reference", "export_request_id"):
        require(nonempty(snapshot[field]), "Missing reader provenance or request ID")
    for field in ("has_more_before", "has_more_after", "truncated"):
        require(snapshot[field] is False, "Source is incomplete or pagination is unconfirmed")
    messages = snapshot["messages"]
    require(isinstance(messages, list) and len(messages) >= 2, "No prior conversation to export")
    previous = None
    seen = set()
    for item in messages:
        require(isinstance(item, dict) and set(item) == MESSAGE_KEYS,
                "Message fields do not match protocol v1")
        require(nonempty(item["id"]) and item["id"] not in seen, "Missing or duplicate message ID")
        require(item["parent_id"] == previous, "Missing, reordered, or mixed-branch messages")
        require(isinstance(item["role"], str) and item["role"] in LABELS,
                "Unsupported visible message role")
        require(item["content_type"] == "text" and isinstance(item["content"], str),
                "Non-text or missing message content")
        require(item["status"] == "complete", "An unfinished message cannot be exported")
        item["content"].encode("utf-8", errors="strict")
        seen.add(item["id"])
        previous = item["id"]
    require(messages[0]["role"] == "user", "Conversation must begin with the first user message")
    require(messages[-1]["role"] == "user"
            and messages[-1]["id"] == snapshot["export_request_id"],
            "The final message is not the fixed export request")
    return messages[:-1]


def load_snapshot(path):
    raw = Path(path).read_bytes()
    snapshot = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
    validate_snapshot(snapshot)
    return snapshot, raw


def export_time(value):
    require(isinstance(value, str), "Provide the client Beijing timestamp")
    parsed = datetime.fromisoformat(value)
    require(parsed.utcoffset() == timedelta(hours=8) and parsed.microsecond == 0,
            "Timestamp must include +08:00 and whole seconds")
    return parsed


def fence_for(content):
    # A longer delimiter than every backtick run cannot be closed by the payload.
    longest = max((len(match[0]) for match in re.finditer(r"`+", content)), default=0)
    return "`" * max(3, longest + 1)


def render(snapshot, raw, timestamp):
    require(json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object) == snapshot,
            "Snapshot data does not match the original reader bytes")
    messages = validate_snapshot(snapshot)
    moment = export_time(timestamp)
    metadata = {
        "skill": "exportation", "source": "chatgpt-conversation",
        "conversation_id": snapshot["conversation_id"], "title": snapshot["title"],
        "exported_at": moment.isoformat(timespec="seconds"),
        "scope": "当前分支，从首条用户消息至导出指令之前",
        "capture_start": messages[0]["id"], "capture_end": messages[-1]["id"],
        "export_request_id": snapshot["export_request_id"],
        "user_message_count": sum(item["role"] == "user" for item in messages),
        "assistant_message_count": sum(item["role"] == "assistant" for item in messages),
        "reader": snapshot["reader"], "read_reference": snapshot["read_reference"],
        "source_snapshot_sha256": sha256(raw),
        "verification": "snapshot-structure-and-local-byte-roundtrip",
        "messages": [
            {"id": item["id"], "role": item["role"], "characters": len(item["content"]),
             "sha256": sha256(item["content"].encode("utf-8")), "fence": fence_for(item["content"])}
            for item in messages
        ],
    }
    # JSON is valid YAML 1.2; one encoder handles all quoting and newlines.
    header = json.dumps(metadata, ensure_ascii=False, indent=2)
    blocks = []
    for index, (item, info) in enumerate(zip(messages, metadata["messages"]), 1):
        blocks.append(f"## {index}. {LABELS[item['role']]}：\n\n"
                      f"{info['fence']}text\n{item['content']}\n{info['fence']}\n\n")
    text = "---\n" + header + "\n---\n\n# 原始问答\n\n" + "".join(blocks)
    require(decode_export(text) == [(item["role"], item["content"]) for item in messages],
            "Markdown round-trip check failed")
    filename = moment.strftime("%Y-%m-%d-%H%M%S-") + snapshot["conversation_id"] + ".md"
    return text.encode("utf-8"), filename, metadata


def decode_export(text):
    require(text.startswith("---\n"), "Missing export header")
    header, separator, body = text[4:].partition("\n---\n\n# 原始问答\n\n")
    require(bool(separator), "Missing message section")
    metadata = json.loads(header, object_pairs_hook=unique_object)
    result = []
    for index, info in enumerate(metadata["messages"], 1):
        prefix = f"## {index}. {LABELS[info['role']]}：\n\n{info['fence']}text\n"
        require(body.startswith(prefix), "Message boundary mismatch")
        body = body[len(prefix):]
        length = info["characters"]
        content, body = body[:length], body[length:]
        suffix = f"\n{info['fence']}\n\n"
        require(body.startswith(suffix), "Truncated message body")
        body = body[len(suffix):]
        require(sha256(content.encode("utf-8")) == info["sha256"], "Message text mismatch")
        result.append((info["role"], content))
    require(body == "", "Unexpected data after final message")
    return result


def write_new(directory, filename, data):
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / filename
    try:
        # The exclusive open rejects existing files and links, including races.
        with target.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        raise
    except OSError as error:
        if target.exists():
            raise ExportError("A file was created but writing failed: " + str(target)) from error
        raise
    try:
        require(target.read_bytes() == data, "Saved bytes do not match the export")
    except (OSError, ExportError) as error:
        raise ExportError("A file was created but read-back verification failed: " + str(target)) from error
    return target


def save_snapshot(path, timestamp):
    require(os.name == "nt", "The approved Inbox is on the connected Windows computer")
    require(DESTINATION.is_absolute() and DESTINATION.drive.upper() == "D:",
            "The fixed local Inbox is unavailable")
    for directory in (DESTINATION, *DESTINATION.parents):
        require(not directory.is_symlink() and not directory.is_junction(),
                "The fixed Inbox must not redirect through a link or junction")
    snapshot, raw = load_snapshot(path)
    data, filename, metadata = render(snapshot, raw, timestamp)
    target = write_new(DESTINATION, filename, data)
    return {"path": str(target), "user_message_count": metadata["user_message_count"],
            "assistant_message_count": metadata["assistant_message_count"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect_parser = subparsers.add_parser("inspect", help="Check the internal snapshot structure only")
    inspect_parser.add_argument("snapshot", type=Path)
    save_parser = subparsers.add_parser("save", help="Save a verified reader snapshot to the fixed local Inbox")
    save_parser.add_argument("snapshot", type=Path)
    save_parser.add_argument("--exported-at", required=True)
    args = parser.parse_args()
    try:
        if args.command == "inspect":
            snapshot, raw = load_snapshot(args.snapshot)
            messages = validate_snapshot(snapshot)
            result = {"snapshot_structure": "valid", "reader_authenticity": "not_checked",
                      "source_history_completeness": "not_proven_by_this_script",
                      "message_count": len(messages), "source_snapshot_sha256": sha256(raw)}
        else:
            result = save_snapshot(args.snapshot, args.exported_at)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError, UnicodeError) as error:
        print("Export failed: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
