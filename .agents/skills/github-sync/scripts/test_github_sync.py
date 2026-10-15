"""Exercise the workflow with temporary repositories and local-only remotes."""

import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from github_sync import SyncError, SyncRepo, github_url


def git(root, *args):
    proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, timeout=30)
    if proc.returncode:
        raise RuntimeError("fixture Git operation failed: " + proc.stderr.decode("utf-8", errors="replace"))
    return proc.stdout.decode("utf-8").strip()


def synthetic_token():
    return "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"


class LocalRemoteRepo(SyncRepo):
    def __init__(self, root, scanner, config, bare):
        self.bare = Path(bare)
        self.calls = []
        self.fail_push = False
        super().__init__(root, scanner, config)

    def network(self, args):
        self.calls.append(args[0])
        if self.fail_push and args[0] == "push":
            raise SyncError("GIT_FAILED", "fixture push rejection")
        args = list(args)
        args[args.index("--") + 1] = str(self.bare)
        return self.git(args)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="case-", dir=TEST_ROOT)
        self.parent = Path(self.temp.name).resolve()
        if not self.parent.is_relative_to(TEST_ROOT.resolve()):
            raise RuntimeError("unsafe fixture directory")
        self.root = self.parent / "language-log"
        self.bare = self.parent / "remote.git"
        self.root.mkdir()
        self.bare.mkdir()
        git(self.root, "init", "--initial-branch=main")
        git(self.bare, "init", "--bare", "--initial-branch=main")
        git(self.root, "config", "user.name", "Fixture User")
        git(self.root, "config", "user.email", "fixture@example.test")
        git(self.root, "config", "core.autocrlf", "false")
        self.write(".gitignore", "/_local/\n.env\n")
        self.write("notes.md", "Original language notes.\n")
        self.commit("docs: create fixture")
        git(self.root, "push", str(self.bare), "HEAD:refs/heads/main")
        git(self.root, "remote", "add", "origin", "git@github.com:fixture-user/language-log.git")
        git(self.root, "config", "branch.main.remote", "origin")
        git(self.root, "config", "branch.main.merge", "refs/heads/main")
        self.initial = git(self.root, "rev-parse", "HEAD")
        self.repo = LocalRemoteRepo(self.root, SCANNER, CONFIG, self.bare)

    def tearDown(self):
        if not self.parent.is_relative_to(TEST_ROOT.resolve()):
            raise RuntimeError("unsafe fixture cleanup")
        self.temp.cleanup()

    def write(self, relative, value):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")

    def commit(self, message):
        git(self.root, "add", "--all")
        git(self.root, "commit", "--message", message)

    def apply(self, preview, message="docs: update language notes", confirmed=True, privacy=True):
        return self.repo.apply(preview["snapshot"], preview["snapshot_id"], message, confirmed, privacy)

    def assert_stops(self, code, operation):
        with self.assertRaises(SyncError) as caught:
            operation()
        self.assertEqual(code, caught.exception.code)
        return caught.exception

    def test_clean_repository(self):
        preview = self.repo.prepare("docs: update language notes")
        self.assertEqual("no_update", preview["status"])
        self.assert_stops("NO_UPDATE", lambda: self.apply(preview))
        self.assertNotIn("push", self.repo.calls)

    def test_preview_preserves_real_index_and_head(self):
        self.write("notes.md", "Staged language change.\n")
        git(self.root, "add", "notes.md")
        self.write("notes.md", "Final language change.\n")
        self.write("新增笔记.md", "新词记录。\n")
        index = (self.root / ".git/index").read_bytes()
        self.repo.prepare("docs: update language notes")
        self.assertEqual(index, (self.root / ".git/index").read_bytes())
        self.assertEqual(self.initial, git(self.root, "rev-parse", "HEAD"))
        self.assertNotIn("push", self.repo.calls)

    def test_successful_update_includes_add_modify_delete(self):
        (self.root / "notes.md").unlink()
        self.write("新笔记.md", "追加した言葉。\n")
        self.write(".gitignore", "/_local/\n.env\n*.tmp\n")
        preview = self.repo.prepare("docs: update language notes")
        self.assertEqual({"A", "M", "D"}, {item["status"] for item in preview["changes"]})
        result = self.apply(preview)
        self.assertEqual("uploaded", result["status"])
        self.assertEqual(result["commit"], git(self.bare, "rev-parse", "refs/heads/main"))
        self.assertEqual("", git(self.root, "status", "--porcelain"))
        self.assertIn("https://github.com/fixture-user/language-log/commit/", result["commit_url"])

    def test_only_existing_unpushed_commit(self):
        self.write("notes.md", "Already committed update.\n")
        self.commit("docs: add existing language update")
        head = git(self.root, "rev-parse", "HEAD")
        preview = self.repo.prepare("docs: update language notes")
        self.assertFalse(preview["state"]["needs_commit"])
        self.assertEqual([head], preview["state"]["pending_commits"])
        self.apply(preview, None)
        self.assertEqual(head, git(self.root, "rev-parse", "HEAD"))

    def test_automatic_tag_push_is_disabled(self):
        git(self.root, "config", "push.followTags", "true")
        git(self.root, "tag", "--annotate", "fixture-tag", "--message", "fixture annotation")
        self.write("notes.md", "Branch-only update.\n")
        preview = self.repo.prepare("docs: update language notes")
        self.assertEqual("uploaded", self.apply(preview)["status"])
        self.assertEqual("", git(self.bare, "tag", "--list"))

    def test_reverted_pending_history_is_still_uploaded(self):
        self.write("notes.md", "Intermediate update.\n")
        self.commit("docs: add intermediate update")
        self.write("notes.md", "Original language notes.\n")
        self.commit("docs: revert intermediate update")
        preview = self.repo.prepare("docs: update language notes")
        self.assertEqual([], preview["changes"])
        self.assertEqual(2, len(preview["state"]["pending_commits"]))
        self.assertEqual(3, len(preview["review_versions"]))
        self.assertEqual("uploaded", self.apply(preview, None)["status"])

    def test_missing_confirmation_makes_no_commit(self):
        self.write("notes.md", "Unconfirmed update.\n")
        preview = self.repo.prepare("docs: update language notes")
        self.assert_stops("CONFIRMATION_REQUIRED", lambda: self.apply(preview, confirmed=False))
        self.assertEqual(self.initial, git(self.root, "rev-parse", "HEAD"))
        self.assertNotIn("push", self.repo.calls)

    def test_missing_privacy_review_makes_no_commit(self):
        self.write("notes.md", "Update awaiting review.\n")
        preview = self.repo.prepare("docs: update language notes")
        self.assert_stops("CONFIRMATION_REQUIRED", lambda: self.apply(preview, privacy=False))
        self.assertEqual(self.initial, git(self.root, "rev-parse", "HEAD"))

    def test_changes_invalidate_confirmation(self):
        self.write("notes.md", "Reviewed update.\n")
        preview = self.repo.prepare("docs: update language notes")
        self.write("notes.md", "A different update.\n")
        self.assert_stops("APPROVAL_STALE", lambda: self.apply(preview))
        self.assertEqual(self.initial, git(self.root, "rev-parse", "HEAD"))

    def test_snapshot_tampering_is_rejected(self):
        self.write("notes.md", "Reviewed update.\n")
        preview = self.repo.prepare("docs: update language notes")
        path = Path(preview["snapshot"])
        stored = json.loads(path.read_text(encoding="utf-8"))
        stored["state"]["web"] = "https://github.com/fixture-user/another"
        path.write_text(json.dumps(stored), encoding="utf-8")
        self.assert_stops("INVALID_APPROVAL", lambda: self.apply(preview))

    def test_unbound_title_cannot_create_commit(self):
        self.write("notes.md", "Update without a proposed title.\n")
        preview = self.repo.prepare()
        self.assertEqual("needs_message", preview["status"])
        self.assert_stops("INVALID_MESSAGE", lambda: self.apply(preview, None))
        self.assertEqual(self.initial, git(self.root, "rev-parse", "HEAD"))

    def test_changed_title_cannot_create_commit(self):
        self.write("notes.md", "Approved title fixture.\n")
        preview = self.repo.prepare("docs: update language notes")
        self.assert_stops("INVALID_MESSAGE", lambda: self.apply(preview, "docs: a different title"))
        self.assertEqual(self.initial, git(self.root, "rev-parse", "HEAD"))

    def test_current_credentials_block_and_values_are_not_returned(self):
        token = synthetic_token()
        self.write("notes.md", "access_token = " + token + "\n")
        error = self.assert_stops("CREDENTIAL_FOUND", self.repo.prepare)
        serialized = json.dumps(error.findings)
        self.assertNotIn(token, serialized)
        self.assertTrue(error.findings)
        self.assertNotIn("push", self.repo.calls)

    def test_deleted_historical_credential_is_checked(self):
        self.write("credential.txt", "access_token = " + synthetic_token() + "\n")
        self.commit("docs: add fixture credential")
        (self.root / "credential.txt").unlink()
        self.commit("docs: remove fixture credential")
        error = self.assert_stops("CREDENTIAL_FOUND", self.repo.prepare)
        self.assertTrue(any("history/" in item["path"] for item in error.findings))

    def test_ignored_untracked_file_is_not_uploaded(self):
        self.write(".env", "access_token = " + synthetic_token() + "\n")
        self.write("notes.md", "Public language update.\n")
        preview = self.repo.prepare("docs: update language notes")
        self.assertNotIn(".env", preview["review_versions"][0]["paths"])
        self.apply(preview)
        self.assertNotIn(".env", git(self.root, "ls-tree", "--name-only", "HEAD").splitlines())

    def test_ignored_but_previously_tracked_secret_is_checked(self):
        self.write(".env", "access_token = " + synthetic_token() + "\n")
        git(self.root, "add", "--force", ".env")
        git(self.root, "commit", "--message", "docs: add fixture tracked secret")
        self.assert_stops("CREDENTIAL_FOUND", self.repo.prepare)

    def test_private_key_filename_blocks(self):
        self.write("id_ed25519", "Fixture key file.\n")
        self.assert_stops("SENSITIVE_FILENAME", self.repo.prepare)

    def test_private_key_content_in_regular_note_blocks(self):
        key = "-----BEGIN " + "OPENSSH PRIVATE KEY-----\n" + "QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVo=\n" + "-----END " + "OPENSSH PRIVATE KEY-----\n"
        self.write("notes.md", key)
        self.assert_stops("CREDENTIAL_FOUND", self.repo.prepare)

    def test_binary_file_requires_review(self):
        (self.root / "picture.bin").write_bytes(b"\0\x01\xff")
        self.assert_stops("UNSUPPORTED_CONTENT", self.repo.prepare)

    def test_missing_scanner_does_not_allow_sync(self):
        self.repo.scanner = self.parent / "missing-tool"
        self.assert_stops("MISSING_SCANNER", self.repo.prepare)

    def test_remote_ahead_blocks_without_merge(self):
        tree = git(self.root, "rev-parse", "HEAD^{tree}")
        advanced = git(self.root, "commit-tree", tree, "-p", self.initial, "-m", "docs: remote fixture update")
        git(self.root, "push", str(self.bare), advanced + ":refs/heads/main")
        self.assert_stops("REMOTE_DIVERGED", self.repo.prepare)
        self.assertEqual(self.initial, git(self.root, "rev-parse", "HEAD"))

    def test_mismatched_push_target_blocks(self):
        git(self.root, "config", "remote.origin.pushurl", "git@github.com:fixture-user/other.git")
        self.assert_stops("TARGET_MISMATCH", self.repo.prepare)
        self.assertEqual([], self.repo.calls)

    def test_credentials_in_url_are_not_disclosed(self):
        value = "https://" + "fixture:fixture-password@github.com/fixture-user/language-log.git"
        error = self.assert_stops("INVALID_TARGET", lambda: github_url(value))
        self.assertNotIn("fixture-password", error.detail)

    def test_push_failure_retains_local_commit(self):
        self.write("notes.md", "Update retained on rejection.\n")
        preview = self.repo.prepare("docs: update language notes")
        self.repo.fail_push = True
        self.assert_stops("GIT_FAILED", lambda: self.apply(preview))
        self.assertNotEqual(self.initial, git(self.root, "rev-parse", "HEAD"))
        self.assertEqual(self.initial, git(self.bare, "rev-parse", "refs/heads/main"))

    def test_commit_hook_cannot_change_approved_message(self):
        hook = self.root / ".git/hooks/commit-msg"
        hook.write_text('#!/bin/sh\nprintf "docs: changed by fixture hook\\n" > "$1"\n', encoding="utf-8")
        hook.chmod(0o755)
        self.write("notes.md", "Approved title update.\n")
        preview = self.repo.prepare("docs: update language notes")
        self.assert_stops("COMMIT_CHANGED", lambda: self.apply(preview))
        self.assertEqual(self.initial, git(self.bare, "rev-parse", "refs/heads/main"))

    def test_changed_author_invalidates_confirmation(self):
        self.write("notes.md", "Reviewed author update.\n")
        preview = self.repo.prepare("docs: update language notes")
        git(self.root, "config", "user.email", "changed@example.test")
        self.assert_stops("APPROVAL_STALE", lambda: self.apply(preview))
        self.assertEqual(self.initial, git(self.root, "rev-parse", "HEAD"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scanner", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    args = parser.parse_args()
    SCANNER = args.scanner.resolve()
    CONFIG = Path(__file__).resolve().parents[1] / "references/gitleaks.toml"
    workspace = args.workspace.resolve()
    if git(workspace, "check-ignore", "_local/github-sync-tests/probe") != "_local/github-sync-tests/probe":
        raise RuntimeError("test workspace must ignore _local")
    TEST_ROOT = workspace / "_local/github-sync-tests"
    TEST_ROOT.mkdir(parents=True, exist_ok=True)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(WorkflowTests)
    result = unittest.TestResult()
    suite.run(result)
    failed = len(result.errors) + len(result.failures)
    report = {"passed": result.testsRun - failed, "failed": failed}
    print(json.dumps(report))
    if failed:
        (TEST_ROOT / "failures.json").write_text(json.dumps([{"test": str(test), "trace": trace} for test, trace in result.errors + result.failures], ensure_ascii=False, indent=2), encoding="utf-8")
    raise SystemExit(1 if failed else 0)
