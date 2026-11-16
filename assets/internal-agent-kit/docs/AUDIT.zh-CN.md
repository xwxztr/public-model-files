# 四个开源 Agent 的内网适用性核查

核查日期：2026-11-17（Asia/Shanghai）。本报告是针对固定版本的联网入口、凭据、依赖和部署边界的**定向源码核查**，不是完整代码审计、渗透测试、等保测评或零风险证明。

## 结论

四者均可把某种模型请求指向自定义服务，但默认发行物均不应被认定为“所有功能完全无外网依赖”。应分别讨论三个阶段：外部准备机下载安装/构建、内网离线安装启动、实际调用内网模型。只要模型不在同一进程中推理，Agent 仍需与模型 API 通信。

| 项目与固定版本 | 完全断网启动/工作条件 | 额外联网能力与风险 | 本包判断 |
|---|---|---|---|
| [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) 0.2.2-rc.3 | 预装 npm 依赖及前端，显式配置自定义 OpenAI Chat 模型 | 反馈会话遥测、桌面产品分析、账号模型、插件/工具安装、Web 工具、原生运行时和更新组件；插件配置可执行代码 | 可做内网候选，但组件较多且为预发布软件；重点依赖沙箱边界 |
| [Pi](https://github.com/earendil-works/pi) 1.5.2 | 预装 Node 与依赖，自定义模型配置；启动采用 offline 参数 | 安装遥测、在线模型目录、工具二进制下载、扩展/技能/npm/git 包；默认工具具有命令执行能力 | 本包优先推荐，关闭扩展和 bash 后验证路径较小 |
| [OpenCode](https://github.com/anomalyco/opencode) 1.19.5 | 预装 Windows CLI，自定义提供商，关闭模型目录获取/升级等 | 模型目录刷新、LSP下载、分享、GitHub集成、插件与MCP、命令/网页工具 | 内网候选；不能仅修改 baseURL 就认为所有请求都走它 |
| [Codex CLI](https://github.com/openai/codex) 0.169.0 | 本地CLI + 自定义 Responses 服务，不使用公网登录 | 更新检查、分析、反馈、OTel、插件、MCP、网页搜索等；不同产品面默认值可不同 | 只有公司 Responses API 验收后适用，普通 Chat Completions 网关不够 |

这里的“可做候选”是有条件的部署判断，不代表已经证明原版在裸机上的所有执行路径都不会联网。断网能打开帮助页也不代表能完成 Agent 任务。

## 源码身份和依据

| 项目 | 固定提交 | 主要许可证 |
|---|---|---|
| DeepSeek Harness | `38a6a5c965aa99ab525161efb7cc5cf1fe62fced` | MIT |
| Pi | `b4afdddf44e059c67ccf5097e5317d913521b470` | MIT |
| OpenCode | `810c0eba1a7348036f8bdf61e6632d0c36c6876c` | MIT |
| Codex CLI | `d32063f96c2dff1dc96af839b3952abb6acfeda4` | Apache-2.0 |

版本、标签、运行时下载地址和二进制哈希也记录在 [SOURCES.json](../SOURCES.json)。Pi 的旧地址 `badlogic/pi-mono` 已迁移，不应把第三方同名 fork 当成官方包。本报告仅涉及开源 CLI/本地 Web 运行方式，不把 Codex 桌面客户端、ChatGPT 云服务或 DeepSeek 公网聊天产品视作同一交付对象。

### DeepSeek Harness

[固定提交的 base 配置](https://github.com/deepseek-ai/deepseek-harness/blob/38a6a5c965aa99ab525161efb7cc5cf1fe62fced/packages/bundle/base/cordis.patch.yml) 配置了 `session-telemetry-otel`，默认模式为 `FEEDBACK_ONLY`，目标为 DeepSeek 遥测收集服务。它不意味着普通每次对话都自动上报，但反馈路径仍然可能释放会话前缀，严格内网环境应禁用。`DSH_TELEMETRY_DISABLED` 的启动覆盖逻辑见 [profile-context.ts](https://github.com/deepseek-ai/deepseek-harness/blob/38a6a5c965aa99ab525161efb7cc5cf1fe62fced/packages/boot/app-boot/src/profile-context.ts)。

[Web bundle](https://github.com/deepseek-ai/deepseek-harness/blob/38a6a5c965aa99ab525161efb7cc5cf1fe62fced/packages/bundle/web-app/cordis.patch.yml) 同时包含桌面产品分析组件，并根据 profile 决定是否启用。这说明反馈遥测和产品分析要分别检查，不能用一个名字推断全部都关闭。插件管理器的注册表解析见 [registry.ts](https://github.com/deepseek-ai/deepseek-harness/blob/38a6a5c965aa99ab525161efb7cc5cf1fe62fced/packages/boot/plugin-manager/src/registry.ts)，桌面自动更新实现见 [update-coordinator.ts](https://github.com/deepseek-ai/deepseek-harness/blob/38a6a5c965aa99ab525161efb7cc5cf1fe62fced/apps/desktop/src/update-coordinator.ts)。这些是存在的能力，不代表本包 CLI/Web 启动时一定触发桌面更新。

自定义 API 的正式配置结构见 [provider 指南](https://github.com/deepseek-ai/deepseek-harness/blob/38a6a5c965aa99ab525161efb7cc5cf1fe62fced/docs/user/guide/providers.md)。本包使用 `llm-pi-ai` 的自定义 `corp` 提供商和明确模型列表，避免公网账号及默认云模型。关闭远程模型、遥测与Web/命令工具；保留本地授权等必要服务以避免破坏 UI 依赖。

### Pi

[启动入口](https://github.com/earendil-works/pi/blob/b4afdddf44e059c67ccf5097e5317d913521b470/packages/coding-agent/src/main.ts) 处理 `--offline` / `PI_OFFLINE`；[CLI 参数定义](https://github.com/earendil-works/pi/blob/b4afdddf44e059c67ccf5097e5317d913521b470/packages/coding-agent/src/cli/args.ts) 说明这用于关闭**启动网络操作**，并提供关闭扩展、MCP、技能等参数。因此它不是所有子进程的网络策略。

[默认设置](https://github.com/earendil-works/pi/blob/b4afdddf44e059c67ccf5097e5317d913521b470/packages/coding-agent/src/core/settings-defaults.ts) 中安装遥测默认为开；[交互模式](https://github.com/earendil-works/pi/blob/b4afdddf44e059c67ccf5097e5317d913521b470/packages/coding-agent/src/modes/interactive/interactive-mode.ts) 包含 `pi.dev/api/report-install` 路径和 offline 判断。安装遥测不应被描述成全部会话内容遥测，但也属于不允许的公网外联。

[模型目录提供方](https://github.com/earendil-works/pi/blob/b4afdddf44e059c67ccf5097e5317d913521b470/packages/coding-agent/src/core/remote-catalog-provider.ts) 访问 pi.dev 的目录；[工具管理器](https://github.com/earendil-works/pi/blob/b4afdddf44e059c67ccf5097e5317d913521b470/packages/coding-agent/src/utils/tools-manager.ts) 有 GitHub 二进制下载逻辑。自定义模型能力见 [models.md](https://github.com/earendil-works/pi/blob/b4afdddf44e059c67ccf5097e5317d913521b470/packages/coding-agent/docs/models.md)。本包通过显式模型定义、offline、遥测关闭和仅 read/edit/write 工具收缩功能，真正的禁网由 Sandbox 完成。

### OpenCode

[模型目录实现](https://github.com/anomalyco/opencode/blob/810c0eba1a7348036f8bdf61e6632d0c36c6876c/packages/core/src/models-dev.ts) 在该版本默认使用 `https://models.opencode.ai`，并在开关允许时后台刷新。历史文档中的 models.dev 名称不能代替此版本实际端点。开关定义见 [flag.ts](https://github.com/anomalyco/opencode/blob/810c0eba1a7348036f8bdf61e6632d0c36c6876c/packages/core/src/flag/flag.ts)。

[LSP 实现](https://github.com/anomalyco/opencode/blob/810c0eba1a7348036f8bdf61e6632d0c36c6876c/packages/opencode/src/lsp/server.ts) 包含从 GitHub 等站点获取语言服务器的逻辑；[GitHub 集成](https://github.com/anomalyco/opencode/blob/810c0eba1a7348036f8bdf61e6632d0c36c6876c/packages/opencode/src/cli/cmd/github.handler.ts) 还可调用 OpenCode 的公开 API。分享、插件、权限、提供方等配置结构见 [v1 配置](https://github.com/anomalyco/opencode/blob/810c0eba1a7348036f8bdf61e6632d0c36c6876c/packages/core/src/v1/config/config.ts)。

本包设置禁自动更新、禁目录获取、纯模式及禁项目配置，并关闭分享/LSP/格式化器/MCP、仅启用 corp 提供商。没有采用旧教程中当前源码不存在的开关作为安全保证。项目内指令仍可影响模型行为，因此输入和提示注入风险没有消失。

### Codex CLI

[provider 协议代码](https://github.com/openai/codex/blob/d32063f96c2dff1dc96af839b3952abb6acfeda4/codex-rs/model-provider-info/src/lib.rs) 的 `WireApi` 仅接受 `responses`，`chat` 配置被明确拒绝。这是本包默认不允许 Codex 对接仅 Chat Completions 网关的依据。

[配置 schema](https://github.com/openai/codex/blob/d32063f96c2dff1dc96af839b3952abb6acfeda4/codex-rs/core/config.schema.json) 包含自定义 provider、更新检查、analytics、feedback 和 OTel 配置。关闭 analytics 并不自动覆盖自定义 OTLP exporter，本包另将日志/指标 exporter 均设为 none，关闭反馈和更新检查。配置加载测试确认该版本已经不接受旧的 `approval_policy="untrusted"`，本包使用有效的 `on-request`，并依靠只读设置、关闭 shell 及外层沙箱约束操作。

## 依赖修复及扫描边界

初次使用 DeepSeek Harness 0.2.2-rc.1 的依赖树时，npm audit 报告了大量传播条目。随后升级到 0.2.2-rc.3，并通过构建根目录 overrides 固定 `@modelcontextprotocol/client=2.3.0`、`fflate=0.8.3`、`undici=8.12.4`。Zod 也由新版本依赖树更新到修复版本。

相关公开告警包括 [MCP 跨源重定向](https://github.com/advisories/GHSA-6prh-2h8m-c8cw)、[fflate ZIP64 拒绝服务](https://github.com/advisories/GHSA-px8p-9vwx-vf98)、[Undici TLS选项问题](https://github.com/advisories/GHSA-2m5v-pch6-74hx)、[Zod 内存耗尽](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5)。这里仅用于解释固定依赖的原因，不以包名告警数量代替可利用性分析。

最终构建时的 npm audit 告警数为 **0**，原始 JSON 随包保留在 [npm-audit.json](../npm-audit.json)。此结果只覆盖被扫描的 npm 依赖树及当时数据库，**不覆盖** Codex/OpenCode 预编译二进制全部内嵌依赖、Node/Python/LibreOffice等原生运行时、操作系统、未知漏洞或恶意包。构建机上没有可用的 Defender 服务，本次未取得病毒扫描通过证据，必须由公司工具完成。

交付保留 npm 锁文件和 [依赖清单](../DEPENDENCIES.json)。上游依赖包中的代码和许可证随运行包保留。对原生运行时和预编译二进制尚未完成完整 SBOM/许可证闭包校验或从源码重建核对；高要求环境应将这些列为准入门槛。

## 为什么这次交付不是“删掉几个URL的安全版”

修改 API 地址和关闭功能只是降低误用概率；插件和子进程仍可自行构造网络请求。本包的主要控制是虚拟化隔离 + 禁用网卡 + 宿主受限中继，不能用在宿主运行同一程序来复现相同保证。详细假设和局限见 [SECURITY.md](../SECURITY.md)。

为避免产生错误安全感，没有将包命名为无风险版或内网认证版，也没有伪造公司 API、Windows Sandbox 或真实任务验收记录。发布候选包是便于公司审核，不等于允许直接投入生产。
