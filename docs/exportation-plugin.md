# exportation

版本：`0.1.1`。源 Skill、转换脚本及本地插件 ZIP 已生成。当前没有接入经过验证的 ChatGPT 完整原文读取工具或适配程序，没有创建账号插件或完成安装；不能宣称已经支持在 Chat 或 Work 中一键导出。

| 项目 | 状态 |
| --- | --- |
| 本地源 Skill | `.agents/skills/exportation/`，唯一维护来源 |
| 本地插件目录 | `plugins/exportation/`，Skill 副本由打包脚本生成 |
| 插件 ZIP | `_local/exportation/exportation-0.1.1.zip` |
| 完整原文读取工具及适配程序 | 未接入；缺少时 Skill 停止，不生成摘要或部分记录 |
| 账号私有创建和安装 | 未执行；Plugin Creator 已安装启用，但当前会话没有其 `create_plugin` 工具，账号保存待执行 |
| Chat、Work 实际调用及完整导出 | 未验证，不能用本地检查代替 |

## 目标用法

安装并完成能力验证后，在需要导出的原 ChatGPT 对话中选择 `@exportation`，发送“导出当前聊天”。从第一条用户消息导出到本次指令之前，仅保留当前显示分支的完整文字问答。

目标目录固定为 `D:\z.repos\language-log\_local\inbox\chatgpt`。文件名为北京时间 `YYYY-MM-DD-HHmmss-聊天ID.md`，真实 ID 无法取得时使用 `unknown`；同名文件立即报错，不覆盖。原文用带角色和序号的独立文本块保存，代码、公式、链接、换行和 Unicode 字符均保留原始文本。

本插件包没有 MCP 服务、账号授权或电脑连接。Chat 中能选中插件，不代表具备完整历史读取、Python 执行或本地写入能力；Work 也必须核实这些条件。原文不完整、只有摘要或占位引用、分支不明、非文字内容无法还原或没有本机访问时停止，不改为其他导出方式。

## 本地程序

Python 3.12+，仅标准库。`references/snapshot-format.md` 定义内部读取快照协议，不是官方 ChatGPT API。只有经过验证的实际读取工具及适配程序才能产生输入；不要求用户预先下载官方导出包，也不允许模型手工构造问答来通过校验。

```powershell
python .agents/skills/exportation/scripts/export_chat.py inspect <reader-snapshot.json>
python .agents/skills/exportation/scripts/export_chat.py save <reader-snapshot.json> --exported-at YYYY-MM-DDTHH:MM:SS+08:00
```

`inspect` 只检查输入结构，不写入；`save` 校验输入、转换后反向解码比对、独占创建并读回核对文件。结构和校验值不能证明快照来自真实工具或账号历史没有遗漏。输入快照和聊天正文留在本机，不放入插件包。

导出完成后，只返回文件路径、用户消息数和助手消息数。用户明确要求收录时，再把 Markdown 交给 `vocab-take-in` 按外部材料独立导入，不改变它的格式和界线。

## 维护与验证

修改 `.agents/skills/exportation/`，同步提升 `plugins/exportation/plugin.json` 的版本后打包：

```powershell
python -B scripts/build_exportation_plugin.py
```

打包只复制 `SKILL.md`、`agents/openai.yaml`、`references/snapshot-format.md` 和 `scripts/export_chat.py`，加上根 `plugin.json` 共五个文件。测试脚本留在源 Skill，不随包分发。打包拒绝额外文件、链接及同版本 ZIP 覆盖，并核对生成副本和 ZIP 字节。它不上传、不设置账号可见性、不安装插件。

本机执行标准库行为检查：

```powershell
& (Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe') -B '.agents\skills\exportation\scripts\test_export_chat.py'
```

2026-10-18 本地行为和包检查：通过 43 项、失败 0 项；Skill 格式检查通过。检查使用明确标记的合成消息和本地临时目录，没有导出真实聊天、生成词汇笔记或改写旧记录。完整能力验收仍须在实际 Chat 和 Work 中分别完成。

官方资料：[插件结构](https://developers.openai.com/plugins/build/plugins)、[插件测试](https://developers.openai.com/plugins/deploy/connect-chatgpt)、[Chat 和 Work 调用](https://learn.chatgpt.com/docs/build-plugins)。
