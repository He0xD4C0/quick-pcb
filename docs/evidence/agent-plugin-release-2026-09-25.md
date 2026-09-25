# Quick PCB v0.3.0 Agent Plugin 发布证据（2026-09-25）

## 结论

- 仓库已生成 Agent Plugins 1.0 根清单、标准 `mcp.json`、Codex 兼容清单与轻量 BoardSpec skill；默认只启用 Core。
- 四个 stdio 入口分别暴露 Core 3、Layout 20、Schematic 34、兼容全量 53 个唯一工具。全部工具具有输入 schema、输出 schema、结构化内容和 MCP annotations。
- Core 可从任意当前目录运行；Layout 与 Schematic 在 Bridge 不可用时仍能完成 MCP 初始化，并把 `BRIDGE_UNAVAILABLE` 作为结构化工具错误返回。
- EasyEDA 实机验证覆盖服务身份、连接状态、Layout 读取与暂存取消，以及 Schematic 的 revision 防护、回读、拓扑、可读性、DRC 和显式保存。
- 本证据证明本地 Agent Plugin 和 stdio MCP 的指定流程可用，不代表公共云 MCP、所有 Agent 客户端、任意电路、PCB 生产或量产就绪。

## 运行环境与隔离

- 日期：2026-09-25。
- EasyEDA Pro：`3.2.186`，半离线模式。
- Bridge：`service=easyeda-bridge`，执行前确认 `edaConnected=true` 且仅有一个已连接窗口。
- 专用工程：`QuickPCB_Schematic_MCP_E2E_20260915_195355`。
- 所有 EDA 写入和保存仅针对上述专用工程。Layout 网表导入停留在预览窗口后选择取消；没有选择“应用修改”。

## MCP 协议与服务面

| 入口 | 服务名 | 工具数 | 默认状态 |
|---|---|---:|---|
| `boardspec-core-mcp` | `boardspec-core` | 3 | 启用 |
| `boardspec-layout-mcp` | `boardspec-layout` | 20 | 关闭 |
| `boardspec-schematic-mcp` | `boardspec-schematic` | 34 | 关闭 |
| `boardspec-mcp` | `boardspec` | 53 | 兼容入口 |

三个聚焦服务均报告 `version=0.3.0`、稳定 title/description 和按领域约束编写的初始化 instructions。Core 的 `validate`、`expand`、`export` 接受显式 `base_dir`；导出目标、网表类型和文档类型均由枚举约束。

所有工具均设置 `openWorldHint=false`。读取、规划、验证和 DRC 工具为只读；写工具为非只读；覆盖、移除、自动布局布线、保存和上下文切换标记为 destructive。参数错误、Bridge 失败和 revision 冲突通过 `ToolError` 进入 MCP `isError=true`；BoardSpec 校验失败、DRC 违规与计划差异保留为正常结构化业务结果。

## Layout 实机门槛

在专用工程的空 PCB1 上完成 Layout 读取：

- 初始 revision：`sha256:ffcc8293a45becdd7e9e378caee3b6587d1abc3f1544d65f122543695dda81c8`。
- 读取到 0 个器件、0 个网络、0 条走线；严格 PCB DRC 报告 2 条既有网表不一致违规。
- 从同一工程已验证原理图读取 8,376 字符的 PROTEL2 网表，调用 `load_netlist` 后返回 `staged=true`、`requires_user_confirmation=true`，EasyEDA 显示“确认导入信息”和待增加器件列表。
- 在 EasyEDA 选择“取消”；再次读取 PCB 后 revision 保持完全相同，器件、网络和走线计数仍为 0。
- 实测发现仅含 `PROTEL NETLIST 2.0` 头的空网表会被 EasyEDA 界面拒绝。v0.3.0 现于 Bridge 调用前返回 `INVALID_NETLIST` 且 `isError=true`，不再把该输入报告为 staged。

因此 `staged` 仅表示 EasyEDA 已打开可审查的导入预览，不表示已应用、已保存或通过 DRC。

## Schematic 实机门槛

在专用工程 P1 上完成真实工具调用和回读：

| 项目 | 结果 |
|---|---:|
| 器件 / 网络 / 节点 | 11 / 5 / 31 |
| 导线 / Port / Flag / No Connect | 29 / 3 / 24 / 38 |
| 拓扑 expected / actual | 11/5/31 / 11/5/31 |
| 可见端点证据 | 58 / 58，100% |
| 严格 Schematic DRC | 0 |

- 使用伪造旧 revision 执行放置得到 MCP `isError=true` 和 `STALE_SCHEMATIC`，画布未被修改。
- 对 C1 执行同坐标、同旋转、同镜像的 checked write，返回 `readback={}`，revision 与 DRC 均未变化。
- 显式 `save_schematic` 成功，回读差异为空，保存前后拓扑均为 11/5/31，严格 DRC 保持 0。
- 半离线模式下 `create_project` 的底层调用返回 HTTP 500；工具将其转换为 `WRITE_STATUS_UNKNOWN`，随后上下文回读确认没有创建工程，未宣称成功。

## 插件与可移植性验证

- `plugin.json` 与 `mcp.json` 通过官方 Agent Plugins JSON Schema。
- 插件通过 `plugin-creator` validator。
- portable 与 Codex compatibility 两套清单使用相同的固定 `v0.3.0` Git 子目录命令；Codex compatibility 清单和受信任项目策略声明启动超时 300 秒、Core 工具超时 120 秒、EDA 工具超时 3600 秒。
- 插件 skill 与仓库权威 `.agents/skills/board-spec` 的受跟踪文件逐字节一致，并排除 `.venv`、构建缓存等本机内容。
- Codex 配置默认发现 Core 3 个工具；Layout 与 Schematic 需显式启用。所有写工具均列入 `approval_mode="prompt"` 清单。
- 临时 `CODEX_HOME` 完成 marketplace 注册、插件安装和当前 Codex CLI 配置解析；将仓库标记为 trusted 后，`codex mcp list` 报告 Core 启用、Layout 与 Schematic 关闭。
- 从 `/tmp` 启动 Core 服务，使用显式 `base_dir` 完成 validate、expand，以及 PROTEL2、KiCad、BOM CSV、Mermaid 四种导出。

## 自动验证与构建

- BoardSpec Core：19 passed。
- MCP：108 passed；覆盖四个入口精确工具集、metadata、instructions、输入/输出 schema、structured content、annotations、ToolError、审批清单、Bridge 降级和插件同步。
- EDA extension：`npm run lint` 和 `npm run build` 通过。
- `plugin.json`、`mcp.json` 官方 JSON Schema 验证通过；`plugin-creator` validator 通过。
- 发布脚本成功生成现有完整 bundle、独立插件 ZIP 和根级 `SHA256SUMS`；正式发布资产将在干净提交上重新构建。

## 发布边界

- Core 不依赖 EasyEDA Bridge；EDA 服务需要 EasyEDA Pro、官方 Bridge 和明确的目标上下文。
- MCP annotations 用于客户端决策，不能替代服务端 revision、context、显式保存和丢弃参数。
- Layout 本轮只验证读取、DRC、网表预览和取消，没有应用网表、布局、走线或保存 PCB。
- Schematic 本轮复用既有专用测试夹具验证闭环；未把该夹具声明为新的电路设计或生产交付物。

被 Git 忽略的 `out/v0.3.0-release-e2e/` 保存本轮 MCP 原始响应。本文记录可提交、可审查的结果与边界。
