# 安装和使用手册

## 1. 先确认环境

支持 Windows 10/11 x64 的 Sandbox 适用版本及硬件虚拟化；Home/ARM64不支持本包。Windows 和安全软件必须处于公司认可的支持/补丁状态。Sandbox 要求及配置依据见 [微软概览](https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/) 和 [配置文件文档](https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/windows-sandbox-configure-using-wsb-file)。

请公司 IT 预先启用 **Windows Sandbox（Windows 沙盒）** 可选功能。启用功能可能需要管理员、重启及公司 Windows 安装介质；本包不自动更改系统功能、不自动下载系统组件。如果缺少功能，只通过公司批准的离线组件源安装，不能为安装而临时开放外网。支持功能不代表公司政策允许使用，需遵循公司的终端管理规定。

本机没有安装该功能，发布包未实测 Windows 10 或 Sandbox 内的所有界面。须先完成[验收清单](ACCEPTANCE.zh-CN.md)。若环境不能使用 Sandbox，停止使用本部署方式，让公司 IT 提供隔离 VM；不可直接在宿主启动 Agent 当作替代。

## 2. 在可联网的外部准备机下载

1. 打开本仓库对应 Release，下载完整 `Internal-Agent-Windows-x64-*.zip`、`SHA256SUMS.txt` 和独立手册；不要只下载 GitHub 自动生成的 Source code。
2. 通过公司允许的导入渠道审查文件，核对 ZIP 的 SHA-256，并做公司指定的病毒/EDR、许可证和供应链检查。SHA256SUMS 同站下载只能证明一致性，不能证明来源未被篡改；审批系统应记录批准的哈希。
3. 代码导入完成后，在公司内网机器离线使用；运行时无需 GitHub、npm、pip、微软账户或公网模型账户。

```powershell
Get-FileHash .\Internal-Agent-Windows-x64-0.1.0.zip -Algorithm SHA256
Expand-Archive .\Internal-Agent-Windows-x64-0.1.0.zip C:\CorpAgent
```

以下假设解压后的根目录为 `C:\CorpAgent`，内含 `windows`、`payload`、`docs`、`host-config.example.json`。如果解压产生额外一层目录，相应调整路径。不要放在 OneDrive、网盘同步目录、受其他用户可写的目录或包含特殊重解析点的路径中。

## 3. 本地填写公司 API 配置

复制示例为 `C:\CorpAgent\host-config.json`，只在公司机器修改：

```json
{
  "base_url": "https://llm.corp.example/v1",
  "pinned_ip": "10.0.0.10",
  "model": "company-approved-model",
  "api_key_env": "CORP_LLM_API_KEY",
  "ca_file": null,
  "allow_responses": false,
  "max_request_bytes": 4194304,
  "max_response_bytes": 33554432,
  "timeout_seconds": 180,
  "max_requests_per_session": 500
}
```

`base_url` 使用证书上的公司域名，`pinned_ip` 必须由 IT 确认，是它的固定 RFC1918 IPv4。中继不做 DNS 查询；地址改变时由 IT 修改此 IP。端口可写在 URL 中。示例域名、IP、模型名都是占位符。

若证书由公司 CA 签发，可使用系统已受信的公司证书，或者将经批准的根/中间 CA PEM 文件保存在宿主私有目录，再把 `ca_file` 改为它的绝对路径，例如 `C:\\CorpCerts\\llm-ca.pem`。证书的 SAN 必须匹配 `base_url` 主机名。**不支持跳过证书校验，也不支持明文 HTTP。** CA 文件不应放入沙箱工具包或 GitHub。

真实 API 密钥不写 JSON，不写启动命令，不写模型配置，不提交 GitHub。启动中继时会隐藏输入密钥，Ctrl+C停止后进程内密钥释放。若公司通过安全机制注入 `CORP_LLM_API_KEY` 环境变量也可使用，中继读取后从自己的环境移除；不要用会留在历史记录中的命令输入真实密钥。

当前只支持 Bearer 鉴权和纯文本接口，API路径固定为 `/v1/chat/completions`，可选 `/v1/responses`。网关有其他路径前缀、额外必需请求头、mTLS或其他鉴权时，本版不能直接使用，需要公司审查后的适配。

## 4. 准备只读输入副本

建立专用目录，例如 `C:\AgentInput\demo`，放入**允许交给公司模型处理**的合成测试文件。不要直接选完整个人目录、代码盘根目录或包含 `.env`、私钥、浏览器数据、真实凭据的项目。移除符号链接、junction 和其他重解析点。

输入目录映射只读。启动后文件复制到沙箱内部 `C:\Work`，编辑发生在那里。不要在运行期间让宿主其他程序修改输入目录。

## 5. 创建会话并启动

普通 PowerShell 窗口执行以下步骤；`ExecutionPolicy Bypass` 仅用于当前进程加载经审查的本地脚本，不修改系统持久策略。若公司禁止该参数，使用公司签名脚本和批准的执行策略。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\CorpAgent\windows\Initialize.ps1 `
  -InputFolder C:\AgentInput\demo `
  -ConfigFile C:\CorpAgent\host-config.json `
  -Agent pi
```

初始化只创建会话，不自动连接模型或启动沙箱。它会显示会话路径，例如 `C:\CorpAgent\local\<随机ID>`。在第二个普通 PowerShell 窗口运行显示的命令：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\CorpAgent\windows\Start-Host.ps1 `
  -Session C:\CorpAgent\local\<随机ID>
```

按隐藏提示输入公司 API 密钥，看到 `Host relay ready` 后，双击该会话目录里的 **Agent.wsb**。不要从开始菜单直接启动默认 Sandbox：微软默认配置有网络，本包生成的文件才显式禁网。

生成的 WSB 关闭网络、剪贴板、音视频、打印机和 GPU 共享，仅映射：工具包只读、输入只读、会话启动信息只读、专用交换目录读写、独立输出目录读写。宿主完整工具包根目录、公司 API 配置和真实密钥均不映射。

首次做安全测试时不要放公司文件。确认隔离有效后再用获批数据。

## 6. 四个工具如何使用

**Pi（推荐先试）**：输入阅读/编辑任务，例如“读取 demo.txt，把错别字修正到 result.txt”。本包允许 read/edit/write，关闭 bash、扩展、MCP、技能、主题、提示模板及启动网络操作。不保存 Pi 会话。自定义模型走本地桥，由宿主中继调用公司 API。`--offline` 只关闭上游启动联网，并不是其全部工具的网络隔离承诺。

**OpenCode**：初始化 `-Agent opencode`。只启用 corp 模型、关闭分享和更新、LSP、格式化器、MCP与项目配置，编辑询问，命令与网页工具拒绝。启动后直接输入任务。公司模型应支持 OpenAI function tools；仅能纯聊天的接口无法胜任完整 Agent 工作。

**DeepSeek Harness**：初始化 `-Agent deepseek`，启动后在**沙箱内部**打开终端显示的 `http://127.0.0.1:3080/?token=...` 等本地 URL。不要复制到宿主浏览器，不要公开该本地访问令牌。预设模型为 corp。禁用反馈遥测、产品分析、账号模型、远程模型入口、网页工具、插件安装工具、命令工具及若干自动化工具。核心 `remote-access` 是本地 API 授权服务的依赖，保留该服务不代表给沙箱打开网络；服务器仅绑定沙箱回环地址。插件管理基础服务保留供界面依赖使用，外联仍由禁网边界阻止。不要登录 DeepSeek 公网账号或安装第三方插件。

**Codex**：公司须确认并测试支持 Responses API、SSE、函数工具及 Codex 请求语义，再将 `allow_responses` 设为 `true`，初始化 `-Agent codex`。供应商只标注“OpenAI兼容”不足以启用。默认只读沙箱、关闭 shell、网页搜索、更新检查、分析、反馈及 OTel。不使用 ChatGPT 登录。本版未对真实 Responses 服务完成模型交互验收；不要自行加 Chat→Responses 转换后宣称等价。

同一沙箱内工具退出后可再次运行：

```powershell
& C:\Kit\windows\Run-Agent.ps1 -Agent pi
```

上下文窗口和输出限制保守设为 32768/8192；应按公司模型能力调整生成配置并重新验收。网关不支持 `store=false` 或某些 OpenAI 参数时会报错，本包不会通过删除保密控制来静默降级。

## 7. 保存、停止和清理

沙箱关闭后，`C:\Work` 和会话状态会丢失。先在沙箱内人工导出**选定结果**：

```powershell
Copy-Item C:\Work\result.txt C:\Output\result.txt
```

宿主结果位于会话的 `output` 目录。按公司流程检查差异、扫描文件、审查脚本与宏后再使用；不要把整个目录当作可信程序自动运行。输出会持久保留。

关闭 Sandbox，并在宿主中继窗口 Ctrl+C。中继正常完成请求后会删除对应交换文件，但崩溃/超时竞态可能留下明文请求或响应；检查本会话 `exchange`。按公司留存制度归档或删除本会话目录，删除前确认已保存需要的输出。磁盘应加密，不承诺普通删除可安全擦除 SSD。

## 8. 故障处理

| 现象 | 检查办法 |
|---|---|
| 找不到 Windows Sandbox | 由 IT 从公司离线系统源安装对应功能；不要直接跑宿主 Agent |
| 配置拒绝启动 | 检查 HTTPS、固定私网 IPv4、模型ID、CA路径和无链接目录；占位模型会被拒绝 |
| 502 | 先由 IT 验证固定 IP/端口、TLS SAN/信任链、密钥、目标路径；中继故意不回显敏感错误详情 |
| 403 | 检查模型是否完全相同，是否调用了非允许接口、远程工具、图片/文件内容或服务端会话 |
| 504/界面等待 | 确认中继窗口仍运行；响应整体缓冲，模型超时/请求上限需要合理调整 |
| Codex 启动被拒绝 | 尚未启用并验收 Responses API，改用 Pi/OpenCode |
| 程序尝试下载/升级失败 | 禁网生效的表现之一；不要开放公网，走外部准备机重新构建离线包 |
| shell/git/编译器不可用 | 本包默认关闭命令工具，也未带完整编译工具链；只有确有需求、经公司审核后另行离线导入 |
| DeepSeek 预发布程序启动失败 | 保存非敏感错误供内部分析；不上传会话/反馈；先使用已验证的 Pi 或 OpenCode |

## 9. 升级与外部重建

内网只替换审核后的整个包，禁止内部执行 npm/pip自更新。外部重建须固定新的版本和提交、刷新锁文件与SBOM、重新做漏洞和恶意软件扫描、运行安全测试与隔离验收，重新记录批准的哈希。安装生命周期脚本默认禁用；确需启用任何脚本时应逐一审核，并仅在外部构建机执行。

源代码、锁文件和构建脚本的复现范围见 [构建说明](BUILD.zh-CN.md)。上游预编译二进制和 npm 包不等于由本项目完成可复现编译；严格公司可要求自己从已批准源代码构建。
