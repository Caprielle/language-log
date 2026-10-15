"""Prepare an approval-bound GitHub update; apply only after explicit confirmation."""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile


SCANNER_VERSION = "8.30.1"
MAX_REVIEW_BYTES = 100 * 1024 * 1024
COMMIT_TITLE = re.compile(r"[a-z][a-z0-9-]*(?:\([a-z0-9._/-]+\))?!?: [\x20-\x7e]+")


class SyncError(Exception):
    def __init__(self, code, detail, findings=None):
        self.code, self.detail, self.findings = code, detail, findings or []
        super().__init__(code)


def fail(code, detail, findings=None):
    raise SyncError(code, detail, findings)


def digest(value):
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def check_title(message):
    if not message or len(message) > 100 or message != message.strip() or not COMMIT_TITLE.fullmatch(message):
        fail("INVALID_MESSAGE", "提交标题必须是简洁英文 Conventional Commit。")


def github_url(value):
    match = re.fullmatch(
        r"(?:git@github\.com:|ssh://git@github\.com/|https://github\.com/)"
        r"([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?", value
    )
    if not match or any(part in (".", "..") for part in match.groups()):
        fail("INVALID_TARGET", "上传地址必须是无内嵌凭据的明确 github.com 仓库地址。")
    return "https://github.com/" + "/".join(match.groups())


def safe_path(root, relative):
    parts = PurePosixPath(relative).parts
    if not parts or PurePosixPath(relative).is_absolute() or any(p in ("..", ".git") for p in parts):
        fail("UNSAFE_PATH", "文件路径不在可检查范围内。")
    path = root.joinpath(*parts)
    if not path.resolve().is_relative_to(root.resolve()):
        fail("UNSAFE_PATH", "发现指向仓库外部的路径。")
    for item in [path, *path.parents]:
        if item == root:
            break
        if item.exists() or item.is_symlink():
            attributes = getattr(item.lstat(), "st_file_attributes", 0)
            if item.is_symlink() or attributes & 0x400:
                fail("UNSUPPORTED_LINK", "发现链接，无法完整检查待上传内容。", [{"path": relative}])
    return path


def check_text(data, path, scope):
    if b"\0" in data:
        fail("UNSUPPORTED_CONTENT", "包含二进制文件，必须完成相应内容检查后才能上传。", [{"path": path, "scope": scope}])
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        fail("UNSUPPORTED_CONTENT", "文件不是可完整检查的 UTF-8 文本。", [{"path": path, "scope": scope}])


def suspicious_name(path):
    name = PurePosixPath(path).name.lower()
    return name in {"id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", ".git-credentials"} or PurePosixPath(name).suffix in {".pem", ".key", ".p12", ".pfx", ".ppk"}


class SyncRepo:
    def __init__(self, root, scanner, config):
        self.root = Path(root).resolve()
        self.scanner, self.config = Path(scanner).resolve(), Path(config).resolve()
        self.git_bin = shutil.which("git")
        if not self.git_bin:
            fail("MISSING_GIT", "找不到 Git，停止同步。")
        for key in os.environ:
            if key in {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES"} or key.startswith("GIT_CONFIG_"):
                fail("GIT_ENV_OVERRIDE", "发现覆盖仓库或 Git 配置的环境变量，需先明确执行环境。")
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GITLEAKS_")}
        self.env.update({"GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"})
        top = self.git(["rev-parse", "--show-toplevel"]).decode().strip()
        if Path(top).resolve() != self.root:
            fail("WRONG_REPOSITORY", "只允许操作本 Skill 所在的仓库。")
        self.local = safe_path(self.root, "_local/github-sync")
        ignored = self.git(["check-ignore", "-q", "--no-index", "--", "_local/github-sync/probe"], allowed=(0, 1), result=True)
        if ignored.returncode != 0:
            fail("LOCAL_NOT_IGNORED", "_local/github-sync 必须被 Git 忽略，防止检查材料进入提交。")
        self.local.mkdir(parents=True, exist_ok=True)

    def git(self, args, allowed=(0,), env=None, result=False):
        proc = subprocess.run([self.git_bin, "-C", str(self.root), *args], env=env or self.env, capture_output=True, timeout=60)
        if proc.returncode not in allowed:
            fail("GIT_FAILED", "Git 操作失败，停止；未输出可能包含敏感内容的原始日志。")
        return proc if result else proc.stdout

    def network(self, args):
        return self.git(args)

    def target(self):
        head = self.git(["rev-parse", "--verify", "HEAD"], allowed=(0, 128), result=True)
        if head.returncode:
            fail("FIRST_UPLOAD_REQUIRED", "请先自行完成首次提交、关联 GitHub 和首次上传。")
        if self.git(["rev-parse", "--is-shallow-repository"]).strip() != b"false":
            fail("SHALLOW_HISTORY", "浅克隆无法完整检查本次待上传历史。")
        for marker in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply", "sequencer"):
            path = self.git(["rev-parse", "--git-path", marker]).decode().strip()
            marker_path = Path(path) if Path(path).is_absolute() else self.root / path
            if marker_path.exists():
                fail("IN_PROGRESS_OPERATION", "存在未完成的 Git 操作，先停止同步。")
        branch = self.git(["symbolic-ref", "--quiet", "--short", "HEAD"], allowed=(0, 1), result=True)
        if branch.returncode:
            fail("DETACHED_HEAD", "当前没有明确的本地分支。")
        branch = branch.stdout.decode().strip()
        values = []
        for suffix in ("remote", "merge"):
            item = self.git(["config", "--get-all", f"branch.{branch}.{suffix}"], allowed=(0, 1)).decode().splitlines()
            if len(item) != 1:
                fail("MISSING_UPSTREAM", "当前分支没有唯一明确的追踪仓库和分支。")
            values.append(item[0])
        remote, ref = values
        if remote.startswith("-") or remote == "." or not ref.startswith("refs/heads/"):
            fail("INVALID_TARGET", "当前追踪目标不是明确的 GitHub 分支。")
        self.git(["check-ref-format", ref])
        fetch_urls = self.git(["remote", "get-url", "--all", remote]).decode().splitlines()
        push_urls = self.git(["remote", "get-url", "--push", "--all", remote]).decode().splitlines()
        if len(fetch_urls) != 1 or len(push_urls) != 1:
            fail("AMBIGUOUS_TARGET", "远端包含多个地址，无法确定唯一上传目标。")
        web = github_url(fetch_urls[0])
        if github_url(push_urls[0]) != web:
            fail("TARGET_MISMATCH", "获取地址与上传地址指向不同仓库。")
        return {"root": str(self.root), "branch": branch, "remote": remote, "ref": ref, "web": web, "transport": digest([fetch_urls, push_urls])}

    def scanner_ready(self):
        if not self.scanner.is_file() or not self.config.is_file():
            fail("MISSING_SCANNER", "找不到已验证的 Gitleaks 或扫描配置，停止同步。")
        proc = subprocess.run([str(self.scanner), "version"], capture_output=True, env=self.env, timeout=15)
        if proc.returncode or proc.stdout.decode().strip() != SCANNER_VERSION:
            fail("SCANNER_VERSION", "Gitleaks 版本不符合已验证的要求，停止同步。")

    def worktree_files(self):
        result = self.git(["ls-files", "-z", "--cached", "--others", "--exclude-standard"])
        return sorted(set(p.decode("utf-8") for p in result.split(b"\0") if p))

    def export_tree(self, tree, directory, scope, budget):
        entries = self.git(["ls-tree", "-rz", "--full-tree", tree]).split(b"\0")
        paths = []
        for entry in filter(None, entries):
            spec, encoded_path = entry.split(b"\t", 1)
            mode, kind, blob = spec.decode().split()
            path = encoded_path.decode("utf-8")
            if mode not in ("100644", "100755") or kind != "blob":
                fail("UNSUPPORTED_ENTRY", "包含链接或子模块，无法完整检查。", [{"path": path, "scope": scope}])
            if suspicious_name(path):
                fail("SENSITIVE_FILENAME", "发现疑似私钥文件，停止同步。", [{"path": path, "scope": scope}])
            size = int(self.git(["cat-file", "-s", blob]))
            budget[0] += size
            if budget[0] > MAX_REVIEW_BYTES:
                fail("REVIEW_LIMIT", "待检查内容超过本工具的完整检查范围，停止同步。")
            data = self.git(["cat-file", "blob", blob])
            check_text(data, path, scope)
            output = safe_path(directory, path)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(data)
            paths.append(path)
        return paths

    def scan_directory(self, source, temp):
        report = temp / "report.json"
        empty_ignore = temp / "empty-ignore"
        empty_ignore.mkdir(exist_ok=True)
        proc = subprocess.run([
            str(self.scanner), "dir", str(source), "--config", str(self.config),
            "--redact=100", "--no-banner", "--no-color", "--log-level", "error",
            "--ignore-gitleaks-allow", "--gitleaks-ignore-path", str(empty_ignore),
            "--max-target-megabytes", "0", "--max-decode-depth", "5", "--exit-code", "23",
            "--report-format", "json", "--report-path", str(report), "--timeout", "60"
        ], capture_output=True, cwd=temp, env=self.env, timeout=75)
        if proc.returncode not in (0, 23) or not report.is_file():
            fail("SCANNER_FAILED", "凭据检查未完整完成，停止同步。")
        findings = json.loads(report.read_text(encoding="utf-8"))
        if not isinstance(findings, list):
            fail("SCANNER_FAILED", "扫描报告不完整，停止同步。")
        if findings or proc.returncode == 23:
            locations = []
            for item in findings:
                file = Path(item["File"])
                relative = file.relative_to(source).as_posix() if file.is_absolute() else file.as_posix()
                locations.append({"path": relative, "line": item.get("StartLine"), "category": item.get("RuleID")})
            fail("CREDENTIAL_FOUND", "发现疑似凭据；只报告位置，停止同步。", locations)

    def collect(self, message=None):
        target = self.target()
        self.scanner_ready()
        self.network(["fetch", "--no-tags", "--no-recurse-submodules", "--", target["remote"], target["ref"]])
        base = self.git(["rev-parse", "--verify", "FETCH_HEAD"]).decode().strip()
        head = self.git(["rev-parse", "HEAD"]).decode().strip()
        ancestor = self.git(["merge-base", "--is-ancestor", base, head], allowed=(0, 1), result=True)
        if ancestor.returncode:
            fail("REMOTE_DIVERGED", "远端包含本地没有的更新，停止；不自动合并或覆盖。")
        pending = self.git(["rev-list", "--reverse", f"{base}..{head}"]).decode().splitlines()
        identities = {role: self.git(["var", f"GIT_{role.upper()}_IDENT"]).decode().strip().rsplit(" ", 2)[0] for role in ("author", "committer")}
        with tempfile.TemporaryDirectory(prefix="scan-", dir=self.local) as temp_name:
            temp = Path(temp_name).resolve()
            if not temp.is_relative_to(self.local.resolve()):
                fail("UNSAFE_TEMP", "临时检查目录不在指定范围内。")
            source = temp / "source"
            source.mkdir()
            (source / "planned-identity.txt").write_text(json.dumps(identities, ensure_ascii=False), encoding="utf-8")
            budget = [0]
            for path in self.worktree_files():
                actual = safe_path(self.root, path)
                if not actual.exists():
                    continue
                if not actual.is_file():
                    fail("UNSUPPORTED_ENTRY", "候选内容不是可完整检查的普通文件。", [{"path": path}])
                if suspicious_name(path):
                    fail("SENSITIVE_FILENAME", "发现疑似私钥文件，停止同步。", [{"path": path}])
                budget[0] += actual.stat().st_size
                if budget[0] > MAX_REVIEW_BYTES:
                    fail("REVIEW_LIMIT", "待检查内容超过完整检查范围，停止同步。")
                data = actual.read_bytes()
                check_text(data, path, "worktree")
                output = safe_path(source / "worktree", path)
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(data)
            # Check raw files before invoking configured Git clean filters.
            self.scan_directory(source, temp)
            index_env = {**self.env, "GIT_INDEX_FILE": str(temp / "index")}
            self.git(["read-tree", head], env=index_env)
            self.git(["add", "--all", "--", "."], env=index_env)
            tree = self.git(["write-tree"], env=index_env).decode().strip()
            versions = [{"scope": "prepared", "tree": tree, "paths": self.export_tree(tree, source / "prepared", "prepared", budget)}]
            for commit in pending:
                commit_tree = self.git(["rev-parse", f"{commit}^{{tree}}"]).decode().strip()
                paths = self.export_tree(commit_tree, source / "history" / commit, commit, budget)
                metadata = self.git(["show", "--no-patch", "--format=fuller", commit])
                check_text(metadata, "commit-metadata", commit)
                metadata_path = source / "metadata" / (commit + ".txt")
                metadata_path.parent.mkdir(parents=True, exist_ok=True)
                metadata_path.write_bytes(metadata)
                versions.append({"scope": commit, "tree": commit_tree, "paths": paths})
            self.scan_directory(source, temp)
            if target != self.target() or self.git(["rev-parse", "HEAD"]).decode().strip() != head:
                fail("CHANGED_DURING_PREPARE", "检查期间分支或目标改变，需要重新准备。")
        raw = self.git(["diff", "--no-ext-diff", "--no-textconv", "--no-renames", "--name-status", "-z", base, tree]).split(b"\0")
        pairs = list(filter(None, raw))
        changes = [{"status": pairs[i].decode(), "path": pairs[i + 1].decode("utf-8")} for i in range(0, len(pairs), 2)]
        changed = self.git(["rev-parse", f"{head}^{{tree}}"]).decode().strip() != tree
        if changed and message is not None:
            check_title(message)
        state = {**target, "base": base, "head": head, "tree": tree, "pending_commits": pending, "needs_commit": changed,
                 "scanner_sha256": hashlib.sha256(self.scanner.read_bytes()).hexdigest(), "config_sha256": hashlib.sha256(self.config.read_bytes()).hexdigest(),
                 "author_sha256": digest(identities["author"]), "committer_sha256": digest(identities["committer"]), "message": message if changed else None}
        return {"state": state, "changes": changes, "review_versions": versions}

    def prepare(self, message=None):
        record = self.collect(message)
        record["snapshot_id"] = digest(record)
        record["status"] = "ready" if record["state"]["needs_commit"] or record["state"]["pending_commits"] else "no_update"
        if record["state"]["needs_commit"] and message is None:
            record["status"] = "needs_message"
        path = self.local / ("preview-" + record["snapshot_id"] + ".json")
        if not path.exists():
            with path.open("x", encoding="utf-8") as file:
                json.dump(record, file, ensure_ascii=False, indent=2)
        return {**record, "snapshot": str(path)}

    def load_snapshot(self, path, approval):
        path = Path(path).resolve()
        if not path.is_relative_to(self.local.resolve()) or not re.fullmatch(r"[0-9a-f]{64}", approval):
            fail("INVALID_APPROVAL", "确认快照或编号无效，停止同步。")
        record = json.loads(path.read_text(encoding="utf-8"))
        payload = {key: record[key] for key in ("state", "changes", "review_versions")}
        if digest(payload) != approval or record.get("snapshot_id") != approval or record["state"]["root"] != str(self.root):
            fail("INVALID_APPROVAL", "快照不符合用户确认的编号，停止同步。")
        return record

    def recheck(self, path, approval):
        record = self.load_snapshot(path, approval)
        current = self.collect(record["state"]["message"])
        if digest(current) != approval:
            fail("APPROVAL_STALE", "确认后内容、分支、工具或上传目标变化，需要重新预览并确认。")
        return record

    def apply(self, path, approval, message, confirmed, privacy_reviewed):
        if not confirmed or not privacy_reviewed:
            fail("CONFIRMATION_REQUIRED", "必须完成具体预览的用户确认和敏感个人信息审阅。")
        approved = self.recheck(path, approval)
        before = approved["state"]
        if not before["needs_commit"] and not before["pending_commits"]:
            fail("NO_UPDATE", "没有需要提交或上传的更新。")
        if before["needs_commit"]:
            if message is not None and message != before["message"]:
                fail("INVALID_MESSAGE", "提交标题与用户确认的预览不同，停止同步。")
            message = before["message"]
            check_title(message)
            self.git(["add", "--all", "--", "."])
            staged_tree = self.git(["write-tree"]).decode().strip()
            if staged_tree != before["tree"]:
                fail("APPROVAL_STALE", "暂存内容与用户确认版本不同，停止；保留当前暂存内容。")
            self.git(["commit", "--message", message])
        actual = self.collect()
        after = actual["state"]
        identity = ("root", "branch", "remote", "ref", "web", "transport", "base", "scanner_sha256", "config_sha256", "author_sha256", "committer_sha256")
        if any(before[key] != after[key] for key in identity) or after["tree"] != before["tree"] or after["needs_commit"]:
            fail("COMMIT_CHANGED", "实际提交、目标或工作区与确认内容不同，停止；保留本地提交。")
        if before["needs_commit"]:
            parents = self.git(["rev-list", "--parents", "-n", "1", after["head"]]).decode().split()
            title = self.git(["show", "--no-patch", "--format=%B", after["head"]]).decode().strip()
            author = self.git(["show", "--no-patch", "--format=%an <%ae>", after["head"]]).decode().strip()
            committer = self.git(["show", "--no-patch", "--format=%cn <%ce>", after["head"]]).decode().strip()
            if parents[1:] != [before["head"]] or title != message or digest(author) != before["author_sha256"] or digest(committer) != before["committer_sha256"]:
                fail("COMMIT_CHANGED", "实际父提交或提交说明不符合确认内容，停止；保留本地提交。")
        elif after["head"] != before["head"]:
            fail("COMMIT_CHANGED", "本地提交在确认后改变，停止同步。")
        remote = self.network(["ls-remote", "--exit-code", "--heads", "--", after["remote"], after["ref"]]).decode().split()
        if len(remote) != 2 or remote != [before["base"], before["ref"]]:
            fail("REMOTE_CHANGED", "上传前远端版本变化，需要重新预览并确认。")
        self.network(["push", "--porcelain", "--no-follow-tags", "--no-mirror", "--", after["remote"], after["head"] + ":" + after["ref"]])
        remote = self.network(["ls-remote", "--exit-code", "--heads", "--", after["remote"], after["ref"]]).decode().split()
        if remote != [after["head"], after["ref"]]:
            fail("UPLOAD_UNCONFIRMED", "未能核对本次上传结果；保留本地提交，不自动重试。")
        return {"status": "uploaded", "commit": after["head"], "branch": after["ref"], "changes": approved["changes"],
                "commit_url": after["web"] + "/commit/" + after["head"],
                "compare_url": after["web"] + "/compare/" + before["base"] + "..." + after["head"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "recheck", "apply"))
    parser.add_argument("--scanner", type=Path)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--approval")
    parser.add_argument("--message")
    parser.add_argument("--confirmed", action="store_true")
    parser.add_argument("--privacy-reviewed", action="store_true")
    args = parser.parse_args()
    skill = Path(__file__).resolve().parents[1]
    root = skill.parents[2]
    if root.name != "language-log" or skill.parent.name != "skills" or skill.parent.parent.name != ".agents":
        fail("WRONG_INSTALLATION", "本 Skill 必须位于 language-log/.agents/skills/github-sync/。")
    scanner = args.scanner or root / "_local/tools/gitleaks-8.30.1/gitleaks.exe"
    repo = SyncRepo(root, scanner, skill / "references/gitleaks.toml")
    if args.action != "prepare" and (args.snapshot is None or args.approval is None):
        fail("INVALID_APPROVAL", "缺少用户确认的快照和编号。")
    if args.action == "prepare":
        output = repo.prepare(args.message)
    elif args.action == "recheck":
        repo.recheck(args.snapshot, args.approval)
        output = {"status": "unchanged", "snapshot_id": args.approval}
    else:
        output = repo.apply(args.snapshot, args.approval, args.message, args.confirmed, args.privacy_reviewed)
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except SyncError as error:
        print(json.dumps({"status": "stopped", "error": error.code, "detail": error.detail, "findings": error.findings}, ensure_ascii=False))
        raise SystemExit(2)
    except Exception as error:
        print(json.dumps({"status": "stopped", "error": "CHECK_FAILED", "exception_type": type(error).__name__, "detail": "检查或操作失败，停止；不输出可能包含敏感内容的原始异常。"}, ensure_ascii=False))
        raise SystemExit(2)
