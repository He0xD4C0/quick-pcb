# MCP 工具契约

兼容 MCP server `boardspec` 注册全部 57 个工具；独立入口 `boardspec-core`、`boardspec-library`、`boardspec-layout`、`boardspec-schematic` 分别注册 3、4、20、36 个工具。Library 全部只读；Layout 与 Schematic 保留兼容的单件查库工具。本地工具直接调用 `boardspec-core`；依赖官方桥的工具通过桥客户端把 JS 定向发送到嘉立创 EDA 专业版窗口。

## 通用约定

- 所有工具发布结构化输入、output schema、MCP annotations 和 `structuredContent`，同时保留 JSON 文本内容。诊断对象统一含 `code`、`path`、`message`，可选 `hint`。
- `validate`、`expand`、`export` 接受可选 `base_dir`，相对元件库从该目录解析；省略时保持以进程工作目录解析的兼容行为。
- 依赖桥的工具在桥不可达时返回 `{ok: false, code: "BRIDGE_UNAVAILABLE", message}`；桥已启动但没有 EDA 窗口连接时，`bridge_status` 返回 `EDA_UNAVAILABLE`。**绝不回退到编造引脚**。
- Schematic 写工具同时要求 `window_id`、`expected_context_revision` 和 `expected_revision`，不依赖隐式活动窗口；超时或写入期间 HTTP 5xx 返回 `WRITE_STATUS_UNKNOWN`，必须回读后再决定是否重试。

## 工具

### `bridge_status`

探活官方桥与 EDA 客户端。

返回：连接完成时为 `{ok, base_url, eda_window_count, active_window_id}`；桥不可达时为 `BRIDGE_UNAVAILABLE`；桥可达但 EDA 未连接时为 `EDA_UNAVAILABLE`。

### `search_part(query, limit=10)`

兼容接口：查嘉立创真实器件库并原样返回搜索结果。新选型流程优先使用 `search_parts`。

返回：桥执行 `eda.lib_Device.search(query)` 的 `result`（`ILIB_DeviceSearchItem[]`），含 `uuid`、`libraryUuid`、`name`、`symbol`、`footprint`。

## Library MCP 工具

### `search_parts(query, page=1, page_size=10)`

查询嘉立创 EDA 系统库并返回 `parts/easyeda-v0.1` 候选表。`page_size` 为 1–50；结果数量等于页大小时返回下一页提示，但不伪造总数。

候选表使用 `{"fields":[...],"rows":[...]}`，固定覆盖 C 编号、制造商/料号、描述、分类、供应商封装、基础/扩展库、BOM/PCB 标记、数据手册、符号/封装/3D UUID、CAD 完整度、品类原始属性和缺失项。品类参数保持嘉立创原始键值，不做单位推导。

### `get_parts_by_lcsc_ids(lcsc_ids)`

按最多 50 个去重后的立创 C 编号批量查询，并启用多匹配。返回全部匹配；不存在的编号列入 `missing_lcsc_ids` 和 `PARTS_NOT_FOUND` 警告，不因部分缺失丢弃其余结果。

### `get_part(part_uuid, library_uuid="")`

按 UUID 取单个器件完整记录。除器件属性外，还下载关联 `elibz2` 符号归档、解析真实 `pins[]`（`number`、`name`、`type`、`part`）和 `pinSource`，并返回保留 UUID、C 编号、原始引脚类型和未审核状态的 `board_spec_definition`。符号归档不可用或无法解析时保留器件记录并返回 `PIN_DATA_UNAVAILABLE`；不得猜测引脚。

Library MCP 不返回实时价格、库存、交期或生命周期，也不内置适用性评分；LLM 必须先提取电气、额定值、极性、封装和引脚条件，使用 `search_parts` 比较真实候选，再对每个入选候选调用 `get_part`。只有查无可靠候选时才建议自建符号并明确说明例外；该顺序是强提示工作流，不是服务器执行硬门槛。

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

## Schematic 工具

Schematic 工具使用 `schematic/easyeda-v0.1` 快照和 `schematic-plan/v0.2` 计划格式；旧 `schematic-plan/v0.1` 仍可读取和比较。BoardSpec 保持坐标无关；规划器先生成逻辑连接意图，再依据真实引脚坐标与器件 BBox 解析连续导线或“短引线 + 端口/电源标志”。写工具负责上下文保护、基线 DRC、写入、回读、拓扑摘要和写后 DRC。

窗口、工程与文档：

- `get_eda_windows`、`get_schematic_context`
- `create_project`、`open_project`
- `create_schematic`、`create_schematic_page`、`open_schematic_page`、`save_schematic`

只读、规划与验证：

- `get_schematic_summary`、`get_schematic_components`
- `get_schematic_wiring`、`get_schematic_violations`
- `plan_schematic`、`resolve_schematic_plan`、`diff_schematic_plan`
- `verify_schematic_topology`、`verify_schematic_readability`
- `verify_schematic_engineering_drawing`

受控写入：

- `place_schematic_components`、`set_schematic_component_placement`、`remove_schematic_components`
- `create_schematic_wires`、`edit_schematic_wires`
- `place_schematic_net_labels`、`place_schematic_net_ports`、`place_schematic_net_flags`
- `edit_schematic_net_markers`
- `set_schematic_no_connects`
- `set_schematic_page_format`

默认 `engineering_basic` 规划要求 `project.name`、`project.version`、`project.drawing.title` 和 `project.drawing.number`，并在 A4/A3 横向图幅中选择可容纳内容的最小图幅。`set_schematic_page_format` 只 patch 当前图页已有的原生 `titleBlockData`：写入图名、图号、版本、可选人工字段和图页尺寸；工程名、更新日期、页码、总页数由 EDA 管理，只控制显示状态。`Symbol`、`Device`、边框、宽高及分区字段只做回读，结构未随 A4/A3 切换时返回 `PAGE_SIZE_NOT_APPLIED`，绝不查询或放置图纸模板，也不生成假图框。`every_endpoint` 策略为每个普通信号端点生成真实同名 Net Port，为每个电源/地端点生成真实同名 Flag；两端局部网络仍保留正交直连，但直连本身不计作 NET 名称可见。`verify_schematic_readability` 要求 `visible_net_endpoint_coverage=1.0`，并报告缺失、错名与碰撞。

sparse_named 策略启用 continuous 布线：显式信号网络各保留一个 Net Port，电源/地各保留一个 Flag，匿名 connect 网络不放标记；两端和多端网络均由连续正交导线树表达。该策略的命名可见率只检查选中的语义标记，全部端点仍由导线、原生网表和拓扑比较共同验收。

`get_schematic_wiring` 对标记回读 BBox、旋转、方向和标志类型；运行时不支持的属性以 `null` 及 `unsupported` 状态返回。`edit_schematic_net_markers` 按 primitive ID 替换或删除标记；替换先创建并验证新图元，再删除旧图元，纯删除要求 `confirm_topology_change=true`。

所有输入模型拒绝额外字段；坐标为 mil 且必须位于 10 mil 网格；引脚选择器为 `U1.#24`；编辑和删除使用回读 primitive ID。旧 `set_no_connects` 仍作为兼容接口保留。EasyEDA Pro 3.2.186 不支持 v4 的 `createNetLabel`，该工具在 v3 快速返回 `API_UNAVAILABLE`，可显式改用 Net Port。

完整参数、规划规则、状态模型、版本差异和失败语义见 [Schematic MCP v0.1](schematic-mcp-v0.1.md)。初始真实写入见 [Schematic MCP E2E](evidence/schematic-mcp-e2e-2026-09-15.md)，网络表达修复后的复验见 [Schematic 网络可读性 E2E](evidence/schematic-readability-e2e-2026-09-16.md)。

## 桥协议（官方）

官方桥由 `easyeda-api-skill` 提供，监听 49620–49629 端口：

- `GET /health` → 200 表示桥服务可达；必须继续检查 `edaConnected` 和 `edaWindowCount` 判断 EDA 是否已连接。
- `POST /execute`，body `{"code": "<JS>", "windowId": "<EDA window>"}` → 返回 `{type: "result"|"error", result|error}`；旧调用可省略 `windowId`，Schematic 写入不可省略。

MCP 的 `bridge_client.BridgeClient` 封装这两个端点；`BOARDSPEC_BRIDGE_URL` 环境变量可覆盖默认端口扫描。
