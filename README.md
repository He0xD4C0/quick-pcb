# Quick PCB：BoardSpec → 嘉立创 EDA Pro

Quick PCB 把电路连接意图写成可审查、可 diff 的 BoardSpec YAML，再由确定性工具完成校验、模块展开、BOM/网表导出，并通过 MCP 与嘉立创 EDA Pro 官方 Bridge 交互。

当前源码与本地发布包版本：`v0.4.0`。远端 `v0.4.0` Git 标签和 Release 尚未发布。

## 能做什么

- 用 YAML 声明元件、网络、电源域、No Connect 和工程约束。
- 使用真实元件库引脚数据进行 Schema、引用和保守 ERC 校验。
- 通过独立只读 Library MCP 查询嘉立创 EDA 系统库，向 LLM 提供紧凑候选表、精确 C 编号查询和可追溯器件详情。
- 展开可复用模块，导出 Protel2、KiCad 交换网表、BOM CSV 和 Mermaid 连接图。
- 在嘉立创 EDA Pro 中预览并应用网表，回读器件、网络和引脚进行逐项比较。
- 通过独立 Layout MCP 读取或精确修改 PCB，并在写入后回读和运行严格 DRC。
- 通过 Schematic MCP 生成 A4/A3 横向自适应的基础工程图计划，只修改图页自带的原生图框明细表并采用模块网格；器件落位后依据真实引脚和 BBox，为每个网络端点生成真实同名 Net Port 或电源/地 Flag，并回读验证拓扑、NET 名称可见性与严格 DRC。

## 明确边界

- BoardSpec 只描述“有什么、连到哪”，自身不包含原理图坐标或绘图 primitive；Schematic MCP 在独立计划中生成这些信息。
- Layout MCP 不修改 BoardSpec 拓扑，不提供布局建议，不维护 undo，也不自动保存 EDA 文档。
- DRC 为 0 只证明通过当前 EDA 规则，不等于固件、实物功能、EMC、热设计、可制造性或量产就绪。
- 引脚、封装和器件参数必须来自可信库或工程审核，工具不会根据名称猜测。
- 默认工作流先以 `search_parts` 比较真实嘉立创系统库候选，再用 `get_part` 核对入选器件的引脚、极性、符号和封装；自建符号仅作为查无可靠候选时的明确例外。
- 元件库查询不用于图纸模板；Schematic MCP 不放置 `Drawing-Symbol_*`，也不使用线条或普通文本拼装图框。
- “基础工程制图”是本项目的可读性规范，不宣称完整符合国家标准。

## Release 安装

Release 目录包含可移植 Agent Plugin、两个平台无关的 Python wheel、一个嘉立创 EDA 插件、完整源码快照和 SHA-256 校验和，不包含本机虚拟环境或 `node_modules`。

```text
release/
  quick-pcb-v0.4.0/
    README.md
    RELEASE-MANIFEST.txt
    SHA256SUMS
    extension/boardspec-eda-extension_v1.0.0.eext
    python/boardspec_core-0.1.0-py3-none-any.whl
    plugin/quick-pcb/
    python/boardspec_mcp-0.4.0-py3-none-any.whl
    source/quick-pcb-v0.4.0-source.tar.gz
  quick-pcb-plugin-v0.4.0.zip
  quick-pcb-v0.4.0.tar.gz
  SHA256SUMS
```

校验并解压完整发布包：

```bash
cd release
shasum -a 256 -c SHA256SUMS
tar -xzf quick-pcb-v0.4.0.tar.gz
cd quick-pcb-v0.4.0
shasum -a 256 -c SHA256SUMS
```

安装 Python 组件：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install python/*.whl
.venv/bin/boardspec-mcp
```

可用的 stdio 命令为 `boardspec-core-mcp`、`boardspec-library-mcp`、`boardspec-layout-mcp`、`boardspec-schematic-mcp` 和兼容的全量 `boardspec-mcp`。嘉立创 EDA 插件位于 `extension/`；在嘉立创 EDA Pro 中进入“设置 → 扩展 → 扩展管理器”并导入 `.eext`。

MCP 与 EDA 实时连接还需要官方 `easyeda-api-skill` Bridge 和 `run-api-gateway.eext`。HTTP 200 只代表 Bridge 服务可访问；只有 Bridge 身份正确且 `edaConnected=true` 才表示 EDA 已连接。

## Agent Plugin

仓库内 `plugins/quick-pcb` 同时提供 Agent Plugins 1.0 清单和 Codex 兼容清单。要求 Python 3.10+、Git 和 `uv`；四个 MCP 进程通过固定的 `v0.4.0` Git 标签安装并缓存运行时。Core 与只读 Library 默认启用，Layout 与 Schematic 按需启用，所有 EDA 写工具要求审批。

仓库 marketplace 位于 `.agents/plugins/marketplace.json`，项目默认策略位于 `.codex/config.toml`。支持 Agent Plugins 1.0 的客户端可直接加载 `plugins/quick-pcb`；其它 stdio MCP 客户端可复制 `plugins/quick-pcb/mcp.json` 中需要的服务配置。

## 开发环境

要求 Python 3.10+、Node.js 20.17+、npm 和 Git。

安装核心包：

```bash
python3 -m venv boardspec-core/.venv
boardspec-core/.venv/bin/python -m pip install -e "./boardspec-core[dev]"
boardspec-core/.venv/bin/boardspec-validate boardspec-core/tests/fixtures/status-led.yaml
```

安装 MCP 服务：

```bash
python3 -m venv mcp-server/.venv
mcp-server/.venv/bin/python -m pip install -e "./boardspec-core[dev]"
mcp-server/.venv/bin/python -m pip install -e "./mcp-server[dev]"
```

安装并构建 EDA 插件：

```bash
cd eda-extension
npm install
npm run build
```

插件单独产出到 `eda-extension/build/dist/boardspec-eda-extension_v1.0.0.eext`。

## 生成 Release

先确保准备发布的修改已经提交且工作区干净，然后执行：

```bash
./scripts/build-release.sh
```

脚本会依次运行两套 Python 测试、EDA 插件 lint/编译，构建 wheel 和 `.eext`，从当前 Git `HEAD` 生成源码快照，写入组件版本与提交信息，并为所有产物生成 SHA-256 校验和。首次构建 wheel 时，Python 构建隔离环境可能需要联网下载 `setuptools`。

开发过程中可用 `./scripts/build-release.sh --allow-dirty` 检查构建流程；这类包会在清单中标记 `dirty=true`，不应对外发布。

`release/` 是本地构建输出并被 Git 忽略。正式发布时上传以下三个文件：

- `release/quick-pcb-v0.4.0.tar.gz`
- `release/quick-pcb-plugin-v0.4.0.zip`
- `release/SHA256SUMS`

## 项目结构

```text
boardspec-core/   BoardSpec DSL、校验、展开、ERC 和导出器
mcp-server/       BoardSpec 与 EasyEDA Pro Layout/Schematic MCP 服务
plugins/quick-pcb/ 可移植 Agent Plugin 与 Codex 兼容清单
eda-extension/    嘉立创 EDA Pro 导入网表/导出 BOM 插件
examples/         已验证的 BoardSpec 示例及真实器件映射
docs/             协议、架构、工具契约和 E2E 证据
scripts/          统一 Release 构建入口
```

## 验证证据

- v0.3.1 交付完整的 5 V MOSFET LED 验收工程：原生 EasyEDA 工程、可读原理图 PDF、PCB 预览、Gerber/钻孔、BOM、CPL、离线校验脚本和实物台架测试步骤。原理图与 PCB 均回读为 9 个器件、6 个网络、19 个节点；严格 DRC 为 0，EasyEDA 本机 PCB DRC 124 项为 0 问题。
- v0.4.0 Library MCP 实机查询 `100nF 0402`、`C1523` 和 `C2150`，并从 C1523 的官方符号归档回读两枚真实引脚；查询全程不修改、切换或保存 EDA 工程。
- STC51 + DS1302 时钟夹具：25 个器件、21 个网络、76 个节点，最终严格 PCB DRC 为 0。
- MOSFET LED 夹具：11 个器件、5 个网络、31 个节点，最终严格 PCB DRC 为 0。
- Schematic MCP 在隔离的一次性工程中绘制并显式保存以上两个单页原理图：拓扑分别为 11/5/31 与 25/21/76，均无组件重叠且严格原理图 DRC 为 0。
- 2026-09-16 可读性修复实机复验中，两页跨区/多端网络的可见端点覆盖率均为 100%，标记与器件/标记 BBox 无重叠，重复执行差异为空。
- 这些结果是特定测试工程和 EDA 版本的实机证据，不自动外推到其它版本或生产设计。

## 文档

- [BoardSpec v0.1 DSL 规范](docs/board-spec-v0.1.md)
- [BoardSpec v0.2 匿名连接规范](docs/board-spec-v0.2.md)
- [MCP 工具契约](docs/mcp-tools.md)
- [Library MCP 真实系统库 E2E](docs/evidence/part-library-mcp-e2e-2026-09-27.md)
- [Layout MCP v0.1](docs/layout-mcp-v0.1.md)
- [Schematic MCP v0.1](docs/schematic-mcp-v0.1.md)
- [Schematic MCP 真实 EDA E2E](docs/evidence/schematic-mcp-e2e-2026-09-15.md)
- [Schematic 网络可读性 E2E](docs/evidence/schematic-readability-e2e-2026-09-16.md)
- [系统架构](docs/architecture.md)
- [STC51 真实 EDA E2E](docs/evidence/stc51-clock-e2e-2026-09-14.md)
- [Layout MCP 真实 EDA E2E](docs/evidence/layout-e2e-2026-09-14.md)
- [v0.3.1 验收工程与制造文件证据](docs/evidence/quickpcb-5v-demo-2026-09-25.md)
- [v0.3.1 验收工程](examples/quickpcb-5v-mosfet-led-demo/README.md)
