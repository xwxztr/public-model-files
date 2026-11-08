# Archify Offline 3.2.0

基于 Archify 3.2.0 的离线衍生版本。请先下载同目录的 ZIP 和 SHA-256 校验文件，再通过公司允许的方式传入内网。原项目许可证和第三方声明保留在压缩包内。

## 校验

PowerShell 中进入压缩包所在目录，运行：

```powershell
Get-FileHash .\archify-offline-3.2.0.zip -Algorithm SHA256
```

应与 `archify-offline-3.2.0.sha256` 中的值一致。校验和可检测下载损坏，但如果包和校验文件同时遭篡改，不能独立证明来源；请通过可信渠道核实。

## 安装到 Pi

1. 将 ZIP 解压到临时目录，里面包含 `archify-offline` 文件夹。
2. 将整个文件夹复制到 Pi 的用户级 Skill 目录 `<agent-dir>/skills/archify-offline`。如果设置了 `PI_CODING_AGENT_DIR`，它的值就是 `<agent-dir>`；否则 Pi 默认目录是 `~/.pi/agent`。
3. 重启 Pi，或运行 `/reload`，并在任务中明确要求使用 `archify-offline` Skill。
4. 需要 Node.js 18 或更新版本；自动浏览器检查需要本地已安装的 Chrome 或 Edge。不要在内网运行在线安装命令。

例如用户级 Pi 数据目录为 `D:\Develop\PI` 时，最终文件应位于：

```text
D:\Develop\PI\skills\archify-offline\SKILL.md
```

Codex 用户可将同一个文件夹放到其用户级 `skills` 目录并重启会话。

## 离线边界

- 此版本禁用在线更新检查和远程品牌图标抓取；已提供的本地图标仍可用。
- Node 绘图入口加入网络限制；验证浏览器屏蔽 HTTP、HTTPS、WebSocket，页面包含限制外部资源的 CSP。
- 只做过功能与有限的网络限制测试，无法保证不存在所有安全漏洞或所有外联路径。使用前应按公司政策进行代码审查和隔离测试，并通过操作系统/网络策略封锁外网。
- Skill 无法决定使用它的模型是否在内网。分析敏感数据时请确认模型、Agent、依赖和运行环境均已按公司要求部署在内网。
- 生成的 HTML 可能包含项目路径、文件名或代码摘要；共享时请检查内容。不要点击 HTML 中指向外部网站的链接。
- 修改上游代码或升级版本后，请重新审查与测试；不要直接覆盖后假设这些离线限制仍然有效。
