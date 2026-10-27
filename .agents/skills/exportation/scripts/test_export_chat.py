"""Offline behavior checks; fixtures are synthetic, never real chats."""

import copy
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import export_chat as exporter


@contextmanager
def temporary_directory():
    root = Path(r"D:\z.repos\language-log\_local\exportation\checks").resolve()
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="case-", dir=root) as temporary:
        resolved = Path(temporary).resolve()
        if not resolved.is_relative_to(root):
            raise RuntimeError("Test cleanup path escaped the local test directory")
        yield str(resolved)


def fixture():
    return {
        "schema_version": 1, "source": "chatgpt-conversation", "conversation_id": "test-chat",
        "title": "Synthetic test only", "reader": "synthetic-test-reader",
        "read_reference": "synthetic-fixture-only", "has_more_before": False,
        "has_more_after": False, "truncated": False, "export_request_id": "request",
        "messages": [
            {"id": "u1", "parent_id": None, "role": "user", "content_type": "text",
             "content": "vertex 是什么意思？", "status": "complete"},
            {"id": "a1", "parent_id": "u1", "role": "assistant", "content_type": "text",
             "content": "vertex（頂点，顶点）：确定位置的点。", "status": "complete"},
            {"id": "request", "parent_id": "a1", "role": "user", "content_type": "text",
             "content": "导出当前聊天", "status": "complete"},
        ],
    }


class ExportChecks(unittest.TestCase):
    def setUp(self):
        self.snapshot = fixture()
        self.timestamp = "2026-10-18T12:34:56+08:00"

    def render(self, snapshot=None):
        snapshot = self.snapshot if snapshot is None else snapshot
        raw = json.dumps(snapshot, ensure_ascii=False).encode("utf-8")
        return exporter.render(snapshot, raw, self.timestamp)

    def test_exact_unicode_whitespace_code_and_embedded_role_labels(self):
        content = '  e\u0301 顶点 😀\r\n## 助手：\n```python\nprint("x")\n```\n````\n$\\vec{v}$\t\n'
        self.snapshot["messages"][0]["content"] = content
        data, _, _ = self.render()
        self.assertEqual(exporter.decode_export(data.decode("utf-8"))[0], ("user", content))

    def test_export_request_is_excluded_and_counts_are_exact(self):
        data, name, meta = self.render()
        self.assertEqual(name, "2026-10-18-123456-test-chat.md")
        self.assertEqual((meta["user_message_count"], meta["assistant_message_count"]), (1, 1))
        self.assertEqual(len(exporter.decode_export(data.decode("utf-8"))), 2)
        self.assertEqual((meta["capture_start"], meta["capture_end"]), ("u1", "a1"))

    def test_consecutive_roles_are_preserved(self):
        self.snapshot["messages"][1]["role"] = "user"
        _, _, meta = self.render()
        self.assertEqual(meta["user_message_count"], 2)

    def test_empty_original_text_is_not_replaced(self):
        self.snapshot["messages"][1]["content"] = ""
        data, _, _ = self.render()
        self.assertEqual(exporter.decode_export(data.decode("utf-8"))[1], ("assistant", ""))

    def test_unknown_id_is_recorded_without_guessing(self):
        self.snapshot["conversation_id"] = "unknown"
        _, name, meta = self.render()
        self.assertTrue(name.endswith("-unknown.md"))
        self.assertEqual(meta["conversation_id"], "unknown")

    def test_source_does_not_claim_authenticity_from_structural_checks(self):
        _, _, meta = self.render()
        self.assertEqual(meta["verification"], "snapshot-structure-and-local-byte-roundtrip")
        self.assertNotIn("complete", meta)

    def test_pagination_truncation_and_non_boolean_flags_are_rejected(self):
        for field in ("has_more_before", "has_more_after", "truncated"):
            for value in (True, None, 0, "false"):
                with self.subTest(field=field, value=value):
                    candidate = copy.deepcopy(self.snapshot)
                    candidate[field] = value
                    with self.assertRaises(exporter.ExportError):
                        self.render(candidate)

    def test_wrong_platform_is_rejected(self):
        self.snapshot["source"] = "codex-conversation"
        with self.assertRaises(exporter.ExportError):
            self.render()

    def test_missing_provenance_is_rejected(self):
        self.snapshot["read_reference"] = ""
        with self.assertRaises(exporter.ExportError):
            self.render()

    def test_mixed_branch_or_missing_parent_is_rejected(self):
        self.snapshot["messages"][1]["parent_id"] = "another-branch"
        with self.assertRaises(exporter.ExportError):
            self.render()

    def test_duplicate_message_id_is_rejected(self):
        self.snapshot["messages"][1]["id"] = "u1"
        with self.assertRaises(exporter.ExportError):
            self.render()

    def test_missing_first_message_is_rejected(self):
        self.snapshot["messages"][0]["parent_id"] = "missing-earlier-message"
        with self.assertRaises(exporter.ExportError):
            self.render()

    def test_non_text_or_missing_content_is_rejected(self):
        for field, value in (("content_type", "image"), ("content", None)):
            with self.subTest(field=field):
                candidate = copy.deepcopy(self.snapshot)
                candidate["messages"][0][field] = value
                with self.assertRaises(exporter.ExportError):
                    self.render(candidate)

    def test_hidden_or_unknown_roles_are_rejected(self):
        for role in ("system", "tool", "developer", "analysis", None, []):
            with self.subTest(role=role):
                candidate = copy.deepcopy(self.snapshot)
                candidate["messages"][1]["role"] = role
                with self.assertRaises(exporter.ExportError):
                    self.render(candidate)

    def test_unfinished_reply_is_rejected(self):
        self.snapshot["messages"][1]["status"] = "in_progress"
        with self.assertRaises(exporter.ExportError):
            self.render()

    def test_wrong_cutoff_is_rejected(self):
        self.snapshot["export_request_id"] = "different-request"
        with self.assertRaises(exporter.ExportError):
            self.render()

    def test_unknown_schema_or_message_fields_are_rejected(self):
        for location in (self.snapshot, self.snapshot["messages"][0]):
            location["unrecognized"] = "data"
            with self.assertRaises(exporter.ExportError):
                self.render()
            del location["unrecognized"]

    def test_filename_traversal_is_rejected(self):
        self.snapshot["conversation_id"] = "../../other"
        with self.assertRaises(exporter.ExportError):
            self.render()

    def test_host_timezone_is_never_used_implicitly(self):
        for timestamp in ("2026-10-18T12:34:56", "2026-10-18T12:34:56Z",
                          "2026-10-18T12:34:56.123+08:00"):
            with self.subTest(timestamp=timestamp), self.assertRaises(exporter.ExportError):
                exporter.export_time(timestamp)

    def test_corrupt_markdown_is_rejected(self):
        data, _, _ = self.render()
        text = data.decode("utf-8")
        with self.assertRaises(exporter.ExportError):
            exporter.decode_export(text.replace("vertex 是什么意思？", "changed"))
        with self.assertRaises(exporter.ExportError):
            exporter.decode_export(text[:-4])

    def test_exclusive_create_does_not_overwrite(self):
        data, name, _ = self.render()
        with temporary_directory() as temporary:
            directory = Path(temporary)
            target = exporter.write_new(directory, name, data)
            with self.assertRaises(FileExistsError):
                exporter.write_new(directory, name, b"replacement")
            self.assertEqual(target.read_bytes(), data)

    def test_write_failure_reports_the_created_file(self):
        with temporary_directory() as temporary:
            target = Path(temporary) / "incomplete.md"
            with patch.object(exporter.os, "fsync", side_effect=OSError("synthetic write failure")):
                with self.assertRaisesRegex(exporter.ExportError, "A file was created"):
                    exporter.write_new(target.parent, target.name, b"data")
            self.assertTrue(target.exists())

    def test_readback_failure_reports_the_created_file(self):
        with temporary_directory() as temporary:
            with patch.object(Path, "read_bytes", return_value=b"wrong"):
                with self.assertRaisesRegex(exporter.ExportError, "read-back verification failed"):
                    exporter.write_new(Path(temporary), "mismatch.md", b"data")

    def test_duplicate_json_keys_are_rejected(self):
        with temporary_directory() as temporary:
            source = Path(temporary) / "duplicate.json"
            source.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
            with self.assertRaises(exporter.ExportError):
                exporter.load_snapshot(source)

    def test_inspect_is_read_only_and_states_its_limit(self):
        with temporary_directory() as temporary:
            source = Path(temporary) / "synthetic.json"
            raw = json.dumps(self.snapshot, ensure_ascii=False).encode("utf-8")
            source.write_bytes(raw)
            result = subprocess.run([sys.executable, "-B", str(Path(exporter.__file__)),
                                     "inspect", str(source)], capture_output=True, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["reader_authenticity"], "not_checked")
            self.assertEqual(source.read_bytes(), raw)
            self.assertEqual(list(Path(temporary).iterdir()), [source])

    def test_invalid_save_creates_no_output(self):
        with temporary_directory() as temporary:
            root = Path(temporary)
            source = root / "broken.json"
            source.write_text("{}", encoding="utf-8")
            with patch.object(exporter, "DESTINATION", root / "not-created"):
                with self.assertRaises(exporter.ExportError):
                    exporter.save_snapshot(source, self.timestamp)
            self.assertFalse((root / "not-created").exists())

    def test_save_roundtrip_uses_the_fixed_destination(self):
        with temporary_directory() as temporary:
            root = Path(temporary)
            source = root / "synthetic.json"
            source.write_text(json.dumps(self.snapshot, ensure_ascii=False), encoding="utf-8")
            # Tests redirect the module constant, never the production CLI.
            with patch.object(exporter, "DESTINATION", root / "inbox"):
                report = exporter.save_snapshot(source, self.timestamp)
            text = Path(report["path"]).read_bytes().decode("utf-8")
            self.assertEqual(exporter.decode_export(text),
                             [(m["role"], m["content"]) for m in self.snapshot["messages"][:-1]])

    def test_source_hash_cannot_describe_different_bytes(self):
        with self.assertRaises(exporter.ExportError):
            exporter.render(self.snapshot, b"{}", self.timestamp)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ExportChecks)
    log = io.StringIO()
    result = unittest.TextTestRunner(stream=log).run(suite)
    print(json.dumps({"passed": result.testsRun - len(result.failures) - len(result.errors),
                      "failed": len(result.failures) + len(result.errors)}))
    if not result.wasSuccessful():
        print(log.getvalue(), file=sys.stderr)
    raise SystemExit(0 if result.wasSuccessful() else 1)
