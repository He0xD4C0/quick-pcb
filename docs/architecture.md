# 系统架构

```
┌────────────┐   MCP 工具    ┌──────────────┐  HTTP /execute  ┌──────────────────┐
│  LLM/Client │ ◄──────────► │  MCP server   │ ◄─────────────► │ 官方 WebSocket 桥 │
│ 意图与Layout │              │  (Python)     │  Port 49620-629 │ (Node)           │
└────────────┘               └──────┬───────┘                 └────────┬─────────┘
                                    │ 本地校验/展开/导出                 │ WebSocket
                              ┌─────▼──────┐                          ┌▼────────────────┐
                              │ boardspec-core│                       │ run-api-gateway  │
                              │ (Python 包) │                         │ .eext 网关扩展   │
                              └────────────┘                         └────────┬─────────┘
                                                                      ┌──────▼──────┐
                                                                      │ 嘉立创EDA Pro │
                                                                      │ lib_Device    │
                                                                      │ sch_Netlist   │
                                                                      │ pcb_Net       │
                                                                      └──────────────┘
```

## 组件

- **boardspec-core**：DSL 的确定性核心。Schema 校验、引用校验、模块展开、保守 ERC、四个导出器（Protel2/KiCad/BOM/mermaid）。不依赖 EDA。
- **mcp-server**：MCP server，保留 12 个 BoardSpec/连接工具，并增加 14 个 Layout 工具。Layout 状态编码、revision 与 DRC 增量在 Python 中确定性处理；桥仍只转发 JS。
- **eda-extension**：嘉立创 EDA 插件（`.eext`）。菜单「导入网表 (Protel2)」读文件并 `pcb_Net.setNetlist`；「导出 BOM」调 `pcb_ManufactureData.getBomFile`。

## 数据流（闭环）

1. LLM 用 `search_part` / `get_part` → 桥调 `eda.lib_Device.search/get` → 拿到**真实**器件与引脚。
2. LLM 产出 BoardSpec YAML。
3. LLM 用 `validate` → `boardspec-core` 做 Schema + 引用 + ERC → 错误回传修正（循环直到无错误）。
4. LLM 用 `expand`（展开模块）→ `export`（网表 + BOM）。
5. 落地：打开目标 PCB，MCP `load_netlist` 或插件菜单「导入网表」→ `eda.pcb_Net.setNetlist()` → 工程师在“确认导入信息”中审查并应用修改。
6. LLM 按需读取紧凑 Layout 快照，再显式调用布局、布线或板级几何工具；每次写入直接落到当前 PCB，随后回读并运行严格 DRC。

## 关键 API（当前安装并核实，`@jlceda/pro-api-types@0.4.23`）

| 能力 | API |
|---|---|
| 查器件 | `eda.lib_Device.search()` / `getByLcscIds()` / `get()` |
| 读真实引脚 | `ISCH_PrimitiveComponent.getAllPins()` |
| 读工程器件 | `eda.sch_PrimitiveComponent.getAll()` |
| 标记 No Connect | `ISCH_PrimitiveComponentPin.setState_NoConnected()`；器件引脚其它电气属性只读 |
| 导入网表到 PCB | `eda.pcb_Net.setNetlist(netlistTypeValue, netlistString)`；桥执行环境传枚举字符串值（如 `"Protel2"`），不引用不可用的全局枚举对象 |
| 读网表 | `eda.sch_Netlist.getNetlist(...)` 或 `eda.pcb_Net.getNetlist(...)` |
| 原理图 DRC | `eda.sch_Drc.check(true, false, true)` |
| PCB DRC | `eda.pcb_Drc.check(true, false, true)` |
| Layout 读取 | `pcb_PrimitiveComponent/Line/Arc/Via/Polyline/Pour/Poured/Region`、`pcb_Layer`、`pcb_Drc`、`pcb_Net` |
| Layout 写入 | 对应图元 `create/modify/delete`、`pcb_Document.autoLayout/autoRouting`、`IPCB_PrimitivePour.rebuildCopperRegion` |
| BOM 导出 | `eda.pcb_ManufactureData.getBomFile(name, 'xlsx'|'csv')` |
| 文件对话框 | `eda.sys_FileSystem.openReadFileDialog()` / `saveFile()` |
| 消息 | `eda.sys_Dialog.showInformationMessage()` |

网表格式 `ESYS_NetlistType`：`Allegro / PADS / Protel2(=Altium) / JLCEDA / EasyEDA / DISA / DSNET`。本系统主选 `Protel2`（文本格式公开、可读、可 diff）。

## 联调步骤

1. **启动官方桥**：克隆 `easyeda/easyeda-api-skill`，`npm install && npm run server`（监听 49620–49629）。
2. **连接 EDA**：在嘉立创 EDA 专业版安装 `run-api-gateway.eext`（下载：https://jlcext.com/item/oshwhub-official/run-api-gateway），加载后自动连接桥。
3. **探活**：`curl http://localhost:49620/health` → 200。
4. **跑 MCP**：注册并启动 `boardspec-mcp`，然后走查库、校验、展开、导入预览、应用、回读和 DRC。MCP 桥路径不要求安装 BoardSpec `.eext`。

## 待验证项（实现时需实测）

1. `pcb_Net.setNetlist` 的最终应用仍由 EDA “确认导入信息”界面控制；必须先检查预览，再应用并回读。`sch_Netlist.setNetlist` 不会从任意网表生成原理图导线。
2. 工程库符号的引脚类型审核仍需在 EDA 符号编辑器完成；放置实例 API 不允许修改该属性。
3. Layout 写工具已在一次性测试 PCB 上完成真实画布 E2E；版本、revision 链、DRC 和拓扑证据见 `docs/evidence/layout-e2e-2026-09-14.md`。其它 EDA 版本和生产设计仍需分别验证。

## 分层边界

- BoardSpec 不生成原理图图形、坐标、走线、层叠、焊盘、符号或封装图形。
- Layout MCP 不改变 BoardSpec 或网表拓扑，不提供布局建议，不维护 undo/影子工程，也不自动保存 EDA 文档。
- 不重写 `boardspec-core`，不引入 networkx 图模型，也不做 KiCad/Altium 原生工程导出；Layout MCP 仅用 Pydantic 声明严格的工具入参 schema。
- 不自研桥（复用官方 `run-api-gateway` + WebSocket bridge）。
