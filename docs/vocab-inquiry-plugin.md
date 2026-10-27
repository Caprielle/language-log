# Vocab Inquiry 私有插件

账号及本机安装版本：`0.1.1`。2026-10-27 已上传到原插件、安装启用，并读回核对云端版本、规则和安装文件。原插件创建时明确指定 `PRIVATE`，共享对象为空；本次更新未修改共享设置，未另建插件或本地 marketplace。

[打开账号中的 Vocab Inquiry](https://chatgpt.com/plugins/Plugin_2c30cef861e08191ac192ff3672f79f3?open_in_app)

该入口需要登录创建插件的账号。插件 ID：`Plugin_2c30cef861e08191ac192ff3672f79f3`。

## 使用

| 平台 | 操作 |
| --- | --- |
| ChatGPT 手机端、电脑端和网页版 | 新建聊天，输入 `@` 并选择插件 `Vocab Inquiry`，发送查词问题 |
| Codex | 新建聊天，从插件中选择 `Vocab Inquiry` 的查词 Skill，发送查词问题 |

可发送“开启当前对话的词汇查询模式”。开启后，本聊天后续的明确词汇问题沿用规则；发送“停止查词模式”可停止。其他问题正常回答，新聊天需重新开启。

专业术语展示英语、日语、中文及一条简单中文解释；普通词提供中文解释、源语言用法、源语言例句及中文翻译。原规则见 [源 Skill](../.agents/skills/vocab-inquiry/SKILL.md)。

## 对话自动命名（0.1.1）

`0.1.1` 新增规则：首次实际调用查词或开启查词模式时，使用宿主提供的对话改名能力，将当前对话命名为 `YYYY-MM-DD-词汇查询`，日期取首次调用当天的北京时间（`Asia/Shanghai`）。每个对话只尝试一次，连续查词、重复开启或跨天继续时不重复命名；用户另行指定或手动修改的标题会保留。仅讨论或修改插件不触发改名。

这条规则本身不提供改名工具。缺少改名能力、无法确认当前对话或操作失败时，会用一句话说明自动命名未完成及原因，再正常回答查词问题；不会把回复中的标题当作已经改名。成功时不额外提示。

2026-10-27 已按用户要求直接调用本地 ZIP 内的 Skill，以“开启当前对话的词汇查询模式”进行测试。虽然本会话未提供独立的对话改名工具，但宿主原生 app-server 支持 `thread/name/set`；通过环境变量 `CODEX_THREAD_ID` 及 `thread/read` 核实当前聊天与工作目录后执行改名，再读回确认标题为 `2026-10-27-词汇查询`，通过 1 项、失败 0 项。测试记录位于被忽略的 `_local/vocab-inquiry/local-invocation-20261027.json`，包含所测 ZIP 的 SHA-256。

该项测试验证包内 Skill 的直接调用和宿主改名操作，没有验证插件自动选中或其他端的行为。随后用户明确要求“上传安装”，已通过原生 `plugin/share/save` 更新同一账号插件，再用 `plugin/install` 安装 `0.1.1`。云端规则文本已与源文件核对一致（仅统一换行比较），更新前后云端展示信息一致，安装的三个文件与本地插件逐字节一致。账号更新及安装检查通过 3 项、失败 0 项，记录位于 `_local/vocab-inquiry/account-update-20261027.json`。

## 打包与更新

唯一维护来源是 `.agents/skills/vocab-inquiry/`；`plugins/vocab-inquiry/skills/vocab-inquiry/` 是生成副本。插件的名称、版本和通用起始提示维护在 `plugins/vocab-inquiry/plugin.json`。

更新源文件和插件版本后，用 Python 3.12+ 执行：

```powershell
python scripts/build_vocab_inquiry_plugin.py
```

本机已验证的 Python 路径为 `C:\Users\jsy13\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`，未将其添加到系统 PATH。

ZIP 生成到 `_local/vocab-inquiry/vocab-inquiry-版本号.zip`，只包含 `plugin.json`、`skills/vocab-inquiry/SKILL.md` 和 `skills/vocab-inquiry/agents/openai.yaml`。脚本拒绝额外文件，不覆盖已有同版本 ZIP。

更新账号插件时，沿用上述插件 ID 和已有共享设置；本次验证使用的原生 `plugin/share/save` 只传 `pluginPath`、`remotePluginId`。`discoverability` 和 `shareTargets` 仅供首次创建，更新请求传入会被服务端拒绝。保存后通过 `plugin/read`、`plugin/skill/read` 核对云端版本及规则，再调用 `plugin/install` 并检查本机版本、启用状态和安装文件。打包不自动上传，当前没有创建本地 marketplace。

更新前先核对当前云端版本和规则与已安装旧版一致，确认包内 manifest 仅增加版本号；云端展示字段可能经过平台处理，因此比较更新前后的云端展示信息，不要求它与包内字段逐项相等。本次仅上传插件目录内已审阅的三个文件，不上传仓库其他内容。

## 验收记录

| 项目 | 状态 |
| --- | --- |
| `0.1.1` 本地格式、包内容与一致性检查 | 2026-10-27 通过 5 项，失败 0 项 |
| `0.1.1` 包内 Skill 直接调用与当前聊天改名 | 2026-10-27 通过 1 项，失败 0 项；宿主读回标题为 `2026-10-27-词汇查询` |
| `0.1.1` 账号更新与本机安装 | 2026-10-27 通过 3 项，失败 0 项；云端及安装版本均为 `0.1.1`，已启用 |
| `0.1.1` 新聊天自动选中与跨端行为 | 未验证；直接调用包内 Skill、上传及安装不视为自动触发验收 |
| 官方 Skill 格式检查、ZIP 内容与完整性、源文件一致性、重复打包与额外文件拦截 | 通过 7 项，失败 0 项 |
| 云端读取查词规则 | `0.1.1` 已与源文件核对文本一致，仅统一换行比较 |
| 账号和 Codex 安装状态 | 已安装、已启用，版本 `0.1.1` |
| 安装目录的 manifest 和查词规则 | 已与本地插件包逐字节核对一致 |
| 私有创建及目录检查 | 创建请求为 `PRIVATE`、共享对象为空；个人目录找到，公开目录未找到 |
| 共享权限单独复核接口 | 当前个人账号调用返回“WORKSPACE scope requires an active workspace”；未改变共享对象 |
| ChatGPT 手机端、电脑端实际调用 | 2026-10-14 用户确认均能选中插件且回答格式正确；通过 2 项，失败 0 项 |
| Codex 插件加载 | 当前聊天的可用 Skill 列表已包含插件版 `vocab-inquiry:vocab-inquiry` |
| Codex 新聊天实际回答 | 待验证，不将插件加载和规则读取视为模型回答验证 |

用户已按“三维建模里的 vertex 是什么意思？”完成 ChatGPT 手机端和电脑端的基础调用验收。完整行为中的 `slightly`、不同语境下的 `normal`、连续查词、停止模式和新聊天，以及电脑关闭后的手机调用尚未逐项确认。

官方文档：[插件支持的平台](https://learn.chatgpt.com/docs/plugins)、[插件结构与安装](https://developers.openai.com/plugins/build/plugins)、[私有插件创建](https://learn.chatgpt.com/docs/build-plugins)。
