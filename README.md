# BoardSpec → 嘉立创 EDA 系统

把电路设计意图写成**可审查、可 diff 的 EDA 中立连接规格**（BoardSpec YAML），由确定性工具校验、查库、展开、导出网表/BOM；独立的 Layout MCP 再以紧凑快照读取并精确操作嘉立创 EDA 专业版 PCB。

**核心原则**：
- BoardSpec 层只声明「有什么元件、连到哪、电源域/地怎么分」，不包含坐标或走线。
- Layout 层只在模型显式调用时直接修改当前 EDA PCB，并在每次写入后回读和运行严格 DRC；它不提供布局建议、不撤销、不自动保存。
- **引脚名必须来自真实元件库**，LLM 不凭记忆编引脚。
- 电源和地显式声明，便于 ERC。
- 所有文本可版本控制、可 diff、可回滚。
- YAML 按 1.2 语义安全解析并拒绝重复键，避免网络名 `ON`/`OFF` 被误判为布尔值。
- 连接规格仍止于**网表 + BOM**；物理布局通过独立、EasyEDA 专用的 MCP tools 完成。

## 目录结构

```
quick-pcb/
  boardspec-core/   # Python 包：DSL 校验/展开/ERC/导出
  mcp-server/       # MCP server：暴露 BoardSpec 工具 + 官方桥客户端
  eda-extension/    # 嘉立创 EDA 插件（.eext）：网表/BOM 导入导出
  docs/             # 文档
```

## 快速开始

### 1. 安装核心包

```bash
cd boardspec-core
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/boardspec-validate tests/fixtures/status-led.yaml
.venv/bin/boardspec-export tests/fixtures/status-led.yaml protel2_netlist
```

### 2. 安装 MCP server

```bash
cd mcp-server
python3 -m venv .venv
.venv/bin/pip install -e ../boardspec-core
.venv/bin/pip install -e .
```

把 MCP server 注册到 Claude Code：

```bash
claude mcp add boardspec -- .venv/bin/boardspec-mcp
```

### 3. 构建嘉立创 EDA 插件

```bash
cd eda-extension
npm install
npm run build   # 产出 build/dist/boardspec-eda-extension_v1.0.0.eext
```

在嘉立创 EDA 专业版中导入该 `.eext`（设置 → 扩展 → 扩展管理器）。

### 4. 端到端联调

详见 [docs/architecture.md](docs/architecture.md) 的「联调」一节。

应用网表后，可把当前 EDA PCB 的 Protel2 回读结果与 BoardSpec 展开图逐项比较：

```bash
BOARDSPEC_BRIDGE_URL=http://127.0.0.1:49620 \
  boardspec-core/.venv/bin/python mcp-server/scripts/verify_roundtrip.py \
  --spec examples/boardspec-e2e-mosfet-led.yaml \
  --output-dir out/BoardSpec_E2E_MOSFET_LED
```

可直接复用的 STC51 + DS1302 电子时钟连接规格位于
[`examples/boardspec-e2e-stc51-clock.yaml`](examples/boardspec-e2e-stc51-clock.yaml)，
对应的真实 EasyEDA 器件映射位于
[`examples/parts.stc51-clock.json`](examples/parts.stc51-clock.json)。实机布局闭环见
[`docs/evidence/stc51-clock-e2e-2026-09-14.md`](docs/evidence/stc51-clock-e2e-2026-09-14.md)。

## MCP 工具

| 工具 | 说明 | 依赖 |
|---|---|---|
| `bridge_status` | 探活官方桥 + EDA 客户端 | 官方桥 |
| `search_part` | 查嘉立创真实器件库 | 官方桥 |
| `get_part` | 按 UUID 取器件详情 | 官方桥 |
| `get_project_component` | 回读已放置器件及引脚/No Connect | 官方桥 |
| `get_netlist` | 回读当前原理图或 PCB 网表 | 官方桥 |
| `set_no_connects` | 预演或应用精确 No Connect | 官方桥 |
| `run_schematic_drc` | 运行原理图严格 DRC | 官方桥 |
| `run_pcb_drc` | 运行 PCB 严格 DRC | 官方桥 |
| `validate` | Schema + 引用 + ERC 校验 | 本地 |
| `expand` | 展开 `kind: module` 模块 | 本地 |
| `export` | 导出网表/BOM/mermaid | 本地 |
| `load_netlist` | 暂存 PCB 网表导入预览 | 官方桥 |
| `get_layout_summary` / `get_layout_components` | 紧凑总览与器件/焊盘几何 | 官方桥 |
| `get_layout_routing` / `get_board_geometry` | 布线、板框、叠层、keepout、覆铜、障碍物 | 官方桥 |
| `get_layout_rules` / `get_layout_violations` | 当前规则和可筛选严格 DRC | 官方桥 |
| `set_component_placement` / `run_auto_layout` | 精确或 EDA 自动布局 | 官方桥 |
| `create_route` / `edit_routing` / `run_auto_routing` | 精确及 EDA 自动布线 | 官方桥 |
| `set_board_outline` / `edit_keepouts` / `edit_copper_pours` | 板级几何与铜皮编辑 | 官方桥 |

详见 [docs/mcp-tools.md](docs/mcp-tools.md)。

## 文档

- [BoardSpec DSL 规范](docs/board-spec-v0.1.md)
- [MCP 工具契约](docs/mcp-tools.md)
- [Layout MCP v0.1](docs/layout-mcp-v0.1.md)
- [系统架构](docs/architecture.md)
- [STC51 电子时钟真实 EDA E2E 证据](docs/evidence/stc51-clock-e2e-2026-09-14.md)
