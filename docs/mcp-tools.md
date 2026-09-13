# MCP 工具契约

MCP server `boardspec` 暴露原有 12 个 BoardSpec/EDA 连接工具和 14 个 PCB Layout 工具。本地工具直接调用 `boardspec-core`；依赖官方桥的工具通过桥客户端转发 JS 到嘉立创 EDA 专业版。

## 通用约定

- 所有工具返回 JSON 对象。诊断对象统一含 `code`、`path`、`message`，可选 `hint`。
- 依赖桥的工具在桥不可达时返回 `{ok: false, code: "BRIDGE_UNAVAILABLE", message}`；桥已启动但没有 EDA 窗口连接时，`bridge_status` 返回 `EDA_UNAVAILABLE`。**绝不回退到编造引脚**。

## 工具

### `bridge_status`

探活官方桥与 EDA 客户端。

返回：连接完成时为 `{ok, base_url, eda_window_count, active_window_id}`；桥不可达时为 `BRIDGE_UNAVAILABLE`；桥可达但 EDA 未连接时为 `EDA_UNAVAILABLE`。

### `search_part(query, limit=10)`

查嘉立创真实器件库。

返回：桥执行 `eda.lib_Device.search(query)` 的 `result`（`ILIB_DeviceSearchItem[]`），含 `uuid`、`libraryUuid`、`name`、`symbol`、`footprint`。

### `get_part(part_uuid, library_uuid="")`

按 UUID 取单个器件完整记录。

返回：`eda.lib_Device.get(uuid, libraryUuid)` 的器件记录，并通过其关联符号归档解析 `pins[]`（`number`、`name`、`type`、`part`）及 `pinSource`。同时返回可复制到 `definitions` 的 `board_spec_definition`，其中保留 UUID、LCSC 编号、原始引脚类型和未审核状态。符号归档不可用或无法解析时保留器件记录，并返回 `PIN_DATA_UNAVAILABLE` 警告；不得猜测引脚。

### `get_project_component(designator)`

读取唯一匹配位号的已放置原理图器件、关联器件/符号/封装 UUID，以及每个引脚的编号、名称、电气类型和 `noConnected` 状态。

### `get_netlist(netlist_type="PROTEL2", document_kind="schematic")`

只读返回当前原理图或 PCB 网表；`document_kind` 可取 `schematic` 或 `pcb`，用于导入后的图结构回读比较。

### `set_no_connects(designator, pin_selectors, apply=false)`

选择器必须是 `#PIN_NUMBER`。默认只返回变更预览；只有 `apply=true` 才设置已放置器件引脚的 `noConnected`，随后回读确认。

### `run_schematic_drc()`

以严格、无 UI、详细结果模式运行当前原理图 DRC，返回 `passed` 和违规数组。

### `run_pcb_drc()`

以严格、无 UI、详细结果模式运行当前 PCB DRC，返回 `passed` 和违规数组。

### `validate(spec_yaml)`

校验 BoardSpec YAML（Schema + 引用 + ERC）。

返回：`{ok, errors, warnings}`。`ok=false` 时 `errors` 非空。

### `expand(spec_yaml)`

递归展开 `kind: module`。

返回：`{ok, errors, warnings, expanded_spec}`；`expanded_spec.reference_map` 给出逻辑路径到物理位号的稳定映射。

### `export(spec_yaml, target)`

导出。`target` ∈ `protel2_netlist` | `kicad_netlist` | `bom_csv` | `mermaid`。

返回：`{ok, errors, warnings, content}`。

### `load_netlist(netlist_text, netlist_type="PROTEL2", document_kind="pcb")`

在当前 PCB 中打开网表导入审查。`netlist_type` ∈ `PROTEL2` | `JLCEDA` | `ALLEGRO` | `PADS`。`document_kind="schematic"` 只作为显式兼容选项；它不会从任意网表生成原理图导线。

成功调用返回 `staged: true` 和 `requires_user_confirmation: true`；这不表示修改已经应用。工程师必须在 EDA 的“确认导入信息”界面审查差异并点击“应用修改”，才能提交到当前编辑会话。

## PCB Layout 工具

Layout 工具使用独立的 `layout/easyeda-v0.1` 快照格式，覆盖紧凑总览、器件/焊盘、走线、板级几何、规则、DRC、布局、布线、板框、keepout 和覆铜。所有写工具直接修改当前 EDA 画布，要求 `expected_revision`，并在写前后执行严格 DRC；不提供 undo 或自动保存。

完整参数、列式响应、选择器和失败语义见 [Layout MCP v0.1](layout-mcp-v0.1.md)。

## 桥协议（官方）

官方桥由 `easyeda-api-skill` 提供，监听 49620–49629 端口：

- `GET /health` → 200 表示桥服务可达；必须继续检查 `edaConnected` 和 `edaWindowCount` 判断 EDA 是否已连接。
- `POST /execute`，body `{"code": "<JS>"}` → 返回 `{type: "result"|"error", result|error}`。

MCP 的 `bridge_client.BridgeClient` 封装这两个端点；`BOARDSPEC_BRIDGE_URL` 环境变量可覆盖默认端口扫描。
