# 外部准备机重建说明

本章仅在**可联网的外部准备机**执行。公司内网使用已审查的完整运行ZIP，不运行这些安装步骤。

## 固定材料

- 四个项目的源码标签/提交及运行时URL见 `SOURCES.json`。
- npm根清单是 `vendor-package.json`，固定依赖树是 `vendor-lock.json`。
- Pi/DeepSeek来自官方npm包；OpenCode/Codex使用官方Windows x64发行物；Node/Python使用官方便携版。
- 包内新增源代码在 `src/`、`windows/`；未把上游全部源码修改后重新编译，也未删除所有上游联网函数。

## 重建步骤

1. 在空的隔离构建目录解压源码包，使用经批准的Node/npm、Python与PowerShell。审查新增源代码、依赖锁、包下载来源与许可证。
2. 建立 `vendor`，把 `vendor-package.json` 复制成其 `package.json`，把 `vendor-lock.json` 复制成 `package-lock.json`。
3. 在vendor目录执行 `npm ci --ignore-scripts --no-audit --no-fund`。固定官方npm注册表或公司批准的外部镜像；不得私自使用不可信镜像。`--ignore-scripts` 用于避免在构建阶段自动执行依赖生命周期脚本。
4. 下载 `SOURCES.json` 的四个运行时归档，核对记录哈希和发布方签名/证明。哈希可能只能验证本次选定材料的一致性；本次没有完成所有发行者签名独立验证。
5. 解压Python嵌入版全部文件到 `payload/runtime/python/`；Node的 `node.exe` 与LICENSE到 `payload/runtime/node/`；OpenCode的exe到 `payload/runtime/opencode/opencode.exe`；Codex exe改名为 `payload/runtime/codex/codex.exe`。
6. 保留上游许可、NOTICE和依赖原始许可文件，重新生成依赖清单及材料来源记录。`DEPENDENCIES.json` 是npm包清单，不是全部原生二进制的完整SBOM。
7. 在vendor目录运行 `npm audit --json --omit=dev` 并保留输出；此步骤只把公开npm依赖信息提交给注册表。新增告警须评估修复，不要把扫描失败当作零告警。
8. 运行下面的检查并记录结果。所有功能测试只使用本地假模型和空白临时用户目录，不带真实API密钥。

```powershell
python -m unittest discover -s tests -v
python tests/smoke_agents.py --agent pi
python tests/smoke_agents.py --agent opencode
python tests/smoke_agents.py --agent deepseek
python tests/smoke_agents.py --agent codex
```

测试要求回环端口8765可用，DeepSeek的默认本地UI端口也须可用；按顺序执行，避免冲突。DeepSeek测试只验证页面启动和令牌认证，不等于真实任务验收；Codex测试只验证配置加载，未调用模型。

9. 更新 `docs/VALIDATION.zh-CN.md`，记录跳过/失败和未验证部分，避免复制旧测试结论。
10. 执行 `python tools/build_bundle.py`。它不联网，只复制已准备依赖、生成逐文件哈希并构建两个ZIP和独立手册。若发现已暂存的vendor锁与新锁不同，会拒绝构建；确认目标路径后手工移走旧 `payload/vendor`，再重新构建。不要递归删除未经核对的计算路径。
11. 运行 `windows/Verify-Payload.ps1`；在独立目录完整解压最终ZIP，再次核验ZIP和payload，并跑公司扫描工具。
12. 在支持的目标Windows/Sandbox中完成现场清单。先验收再在公司引入真实数据。

相同上游版本也可能因平台可选依赖、不同npm版本或文件元数据产生不同ZIP字节。本包提供锁文件和来源，但不声称可复现上游源码到二进制或逐字节重建发行ZIP。

## 发布纪律

只发布源代码白名单、占位配置、公开材料、无敏感数据的验证记录和已批准的离线包。`local/`、真实配置、密钥、CA、输入/输出、提示词与业务日志一律不进入构建ZIP或Git。发布新包使用新tag，保留旧包哈希供回滚；不要静默替换同名安全包。
