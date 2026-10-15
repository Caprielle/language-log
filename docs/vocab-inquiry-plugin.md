# Vocab Inquiry 私有插件

版本：`0.1.0`。插件已保存到当前账号并安装启用，创建时明确指定 `PRIVATE`，共享对象为空。个人目录能找到插件，公开目录查询未找到该插件。

[打开账号中的 Vocab Inquiry](https://chatgpt.com/plugins/Plugin_2c30cef861e08191ac192ff3672f79f3?open_in_app)

该入口需要登录创建插件的账号。插件 ID：`Plugin_2c30cef861e08191ac192ff3672f79f3`。

## 使用

| 平台 | 操作 |
| --- | --- |
| ChatGPT 手机端、电脑端和网页版 | 新建聊天，输入 `@` 并选择插件 `Vocab Inquiry`，发送查词问题 |
| Codex | 新建聊天，从插件中选择 `Vocab Inquiry` 的查词 Skill，发送查词问题 |

可发送“开启当前对话的词汇查询模式”。开启后，本聊天后续的明确词汇问题沿用规则；发送“停止查词模式”可停止。其他问题正常回答，新聊天需重新开启。

专业术语展示英语、日语、中文及一条简单中文解释；普通词提供中文解释、源语言用法、源语言例句及中文翻译。原规则见 [源 Skill](../.agents/skills/vocab-inquiry/SKILL.md)。

## 打包与更新

唯一维护来源是 `.agents/skills/vocab-inquiry/`；`plugins/vocab-inquiry/skills/vocab-inquiry/` 是生成副本。插件的名称、版本和通用起始提示维护在 `plugins/vocab-inquiry/plugin.json`。

更新源文件和插件版本后，用 Python 3.12+ 执行：

```powershell
python scripts/build_vocab_inquiry_plugin.py
```

本机已验证的 Python 路径为 `C:\Users\jsy13\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`，未将其添加到系统 PATH。

ZIP 生成到 `_local/vocab-inquiry/vocab-inquiry-版本号.zip`，只包含 `plugin.json`、`skills/vocab-inquiry/SKILL.md` 和 `skills/vocab-inquiry/agents/openai.yaml`。脚本拒绝额外文件，不覆盖已有同版本 ZIP。

更新账号插件时，沿用上述插件 ID，将新版本保存为 `PRIVATE`，共享对象保持为空，然后核对安装版本。打包不自动上传；私有插件已安装到账号，当前没有创建本地 marketplace。

## 验收记录

| 项目 | 状态 |
| --- | --- |
| 官方 Skill 格式检查、ZIP 内容与完整性、源文件一致性、重复打包与额外文件拦截 | 通过 7 项，失败 0 项 |
| 云端读取查词规则 | 已与源文件逐字节核对一致 |
| 账号和 Codex 安装状态 | 已安装、已启用，版本 `0.1.0` |
| 安装目录的 manifest 和查词规则 | 已与本地插件包逐字节核对一致 |
| 私有创建及目录检查 | 创建请求为 `PRIVATE`、共享对象为空；个人目录找到，公开目录未找到 |
| 共享权限单独复核接口 | 当前个人账号调用返回“WORKSPACE scope requires an active workspace”；未改变共享对象 |
| ChatGPT 手机端、电脑端实际调用 | 2026-10-14 用户确认均能选中插件且回答格式正确；通过 2 项，失败 0 项 |
| Codex 插件加载 | 当前聊天的可用 Skill 列表已包含插件版 `vocab-inquiry:vocab-inquiry` |
| Codex 新聊天实际回答 | 待验证，不将插件加载和规则读取视为模型回答验证 |

用户已按“三维建模里的 vertex 是什么意思？”完成 ChatGPT 手机端和电脑端的基础调用验收。完整行为中的 `slightly`、不同语境下的 `normal`、连续查词、停止模式和新聊天，以及电脑关闭后的手机调用尚未逐项确认。

官方文档：[插件支持的平台](https://learn.chatgpt.com/docs/plugins)、[插件结构与安装](https://developers.openai.com/plugins/build/plugins)、[私有插件创建](https://learn.chatgpt.com/docs/build-plugins)。
