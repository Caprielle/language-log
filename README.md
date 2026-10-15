# language-log

这个仓库用于记录我在技术美术（Technical Artist，TA）学习过程中的语言学习内容，以及分享在学习过程中使用或者创建的 Skills。

## 记录内容

- 词汇笔记和阶段总结
- TA 相关的专业术语、常用表达与使用示例
- 辅助学习的 Skills 及其使用方法

## 目录说明

| 目录 | 用途 |
| --- | --- |
| `records/` | 学习记录与练习 |
| `glossary/` | 专业术语与常用表达整理（待定） |
| `.agents/` | 使用的 Skills |
| `plugins/` | 可安装的插件包 |
| `scripts/` | 从维护中的 Skill 生成插件包 |

## 使用方式

按学习主题整理记录，保留材料来源和示例；使用 Skill 辅助学习时，记录其用途与使用方法，方便后续复习和复用。

`Vocab Inquiry` 已创建为账号内的私有插件并安装启用。ChatGPT 在新聊天中输入 `@` 选择插件；Codex 从插件中选择同名查词 Skill。插件沿用原有查词规则，详细用法、安装状态和跨端验收见 [插件说明](docs/vocab-inquiry-plugin.md)。

调用 `$vocab-take-in` 收录当前对话中查询过的生词，文档固定保存到 `records/`。文件按北京时间命名为 `YYYY-MM-DD-01.md`、`YYYY-MM-DD-02.md`，编号取当天已有最大编号加一，新一天从 `01` 开始。

也可明确要求收录粘贴的原始查词问答，或指定 `.md`、`.txt` 文件。材料须保留用户提问、助手回答及顺序；每次只处理指定范围，建议每批导入一次。外部导入使用独立成功标记，不影响当前聊天的收录进度；只有聊天标题、ID 或摘要时停止收录。

调用 `$github-sync` 检查本仓库的后续更新。它先展示中文更新表格、GitHub 上传目标及英文提交说明，你确认后才提交和上传；首次上传仍由你完成。更新说明涵盖全部待上传文件和提交历史，只在聊天中展示。

同步需要 Python 3.12+、Git 和 [Gitleaks 8.30.1](https://github.com/gitleaks/gitleaks/releases/tag/v8.30.1)。本机扫描工具放在被忽略的 `_local/tools/gitleaks-8.30.1/`，不会随仓库上传。凭据检查与个人信息审阅未完成、发现疑似敏感内容或远端版本有分歧时停止同步。

在仓库根目录运行本地测试（Windows，使用本机 Codex 的 Python）：

```powershell
& (Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe') '.agents\skills\github-sync\scripts\test_github_sync.py' --scanner '_local\tools\gitleaks-8.30.1\gitleaks.exe'
```

测试只使用被忽略目录中的临时仓库和本地远端，不连接 GitHub，结果报告通过和失败数量。

内容随个人学习进度持续补充。
