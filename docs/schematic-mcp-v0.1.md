# EasyEDA Schematic MCP v0.1

> 状态：已在当前工作区实现，并于 2026-09-15 完成初始真实写入，于 2026-09-16 使用 EasyEDA Pro 3.2.186 完成网络可读性修复后的回读、拓扑比较、可读性验证、严格 DRC、幂等复验和显式保存。该功能尚未进入已发布的 v0.2.0。

Schematic MCP 位于 BoardSpec 连接规格与嘉立创 EDA Pro 原理图画布之间。BoardSpec 继续只声明“有什么、连到哪”；Schematic MCP 负责把已校验、已展开的拓扑转换为确定性的器件位置、导线、网络端口和电源标志。

## 能力与边界

- 使用审核后的 EasyEDA 库 UUID 放置器件，使用精确位号和 `U1.#24` 形式的引脚选择器。
- 规划结果为独立 `SchematicPlan`；位置和绘图 primitive 不写回 BoardSpec。
- 支持单页两遍布局、真实引脚几何解析、混合连线、计划 diff、写后回读、Protel2 拓扑比较、可读性验证和严格 DRC。
- 每次写入固定到明确的 EDA 窗口，并由 `context_revision` 与 `revision` 双重保护。
- 不隐式保存、关闭、删除或切换工程/文档；切换需要显式确认，保存只能调用 `save_schematic`。
- v0.1 不创建或修改库符号/封装，不支持层次化跨页连接、总线、差分对或仿真模型。
- 验收只覆盖原理图逻辑和绘制闭环，不代表人工审图、PCB 同步、固件、EMC、热设计、可制造性或生产就绪。

## 数据流

```text
BoardSpec YAML
  -> validate / expand
  -> SchematicPlan（本地、确定性、可 diff）
  -> 受控小批量写入
  -> SchematicSnapshot（写后回读）
  -> Protel2 拓扑比较 + strict DRC
  -> 显式 save_schematic
```

## 状态、单位与选择器

统一快照格式为 `schematic/easyeda-v0.1`：

```json
{
  "format": "schematic/easyeda-v0.1",
  "source": {
    "window_id": "...",
    "project_uuid": "...",
    "schematic_uuid": "...",
    "page_uuid": "...",
    "document_uuid": "...",
    "tab_id": "..."
  },
  "context_revision": "sha256:...",
  "revision": "sha256:...",
  "unit": "mil",
  "components": [],
  "wires": [],
  "labels": [],
  "ports": [],
  "flags": [],
  "no_connects": []
}
```

- `context_revision` 哈希窗口、工程、原理图、页面、文档和标签页身份。
- `revision` 只哈希规范化的原理图内容，不随活动窗口切换而改变。
- 外部坐标一律为 mil；写入坐标必须位于 10 mil 网格，调用 EasyEDA API 时除以 10。
- 器件由唯一位号选择，引脚由精确编号选择；不根据引脚名猜测物理脚。
- 编辑和删除已有图元时必须使用回读得到的 primitive ID。
- Pydantic 输入模型均拒绝未知字段。

## 27 个 Schematic MCP 工具

### 窗口、工程与文档

- `get_eda_windows()`：列出全部 Bridge 窗口，不切换全局活动窗口。
- `get_schematic_context(window_id?)`：读取活动工程、原理图、页面和文档身份。
- `create_project(window_id, friendly_name, project_name?, description?)`：仅允许在没有活动设计文档的窗口创建工程。
- `open_project(window_id, project_uuid, confirm_discard_unsaved=false)`：显式打开工程；存在其它活动文档时默认返回 `DOCUMENT_SWITCH_UNSAFE`。
- `create_schematic(window_id, name, confirm_discard_unsaved=false)`：在当前工程创建、打开并命名原理图。
- `create_schematic_page(window_id, schematic_uuid, name)`：创建并命名图页，不隐式打开或保存。
- `open_schematic_page(window_id, page_uuid, expected_context_revision, confirm_discard_unsaved=false)`：受上下文保护地显式切换图页。
- `save_schematic(window_id, expected_context_revision, expected_revision)`：受双 revision 保护地显式保存。

当前半离线 EasyEDA Pro 3.2.186 中，beta `createProject` 未可靠完成创建，因此真实 E2E 工程通过 GUI 新建；`create_project` 的安全拒绝和状态未知语义已由模拟 Bridge 测试覆盖。原理图、图页创建和保存已在一次性工程中真实验证。

### 只读查询

- `get_schematic_summary(window_id?, cursor?, page_size=100)`：返回计数、分页器件、拓扑摘要和 DRC 类型计数。
- `get_schematic_components(window_id?, designators?, region?, include_pins=false)`：按位号或区域回读器件和可选真实引脚。
- `get_schematic_wiring(window_id?, nets?, region?)`：回读导线、标签、端口和标志，包括标记 BBox、旋转、方向及标志类型；运行时不能提供的属性明确标为 `null/unsupported`。区域筛选按 BBox、点或折线路径相交判断。
- `get_schematic_violations(window_id?, ids?, nets?, region?)`：运行严格 DRC，返回稳定违规 ID、位置和筛选结果。`passed` 只由完整违规集合决定，不能因筛选后为空而变为通过。

### 本地规划与验证

- `plan_schematic(spec_yaml, options?)`：先验证并展开 BoardSpec，再生成确定性计划；不连接 EDA。
- `resolve_schematic_plan(plan, window_id, expected_context_revision, expected_revision)`：回读真实引脚坐标、器件 BBox 和页面图元，把逻辑连接意图解析为最终导线、短引线和网络标记；只读，不修改画布。
- `diff_schematic_plan(plan, window_id, expected_context_revision, expected_revision)`：只读比较计划与当前图页，不自动删除额外内容。
- `verify_schematic_topology(spec_yaml, window_id?, base_dir?)`：把当前 Protel2 网表与展开后的 BoardSpec 比较，报告缺失/多余器件和节点。
- `verify_schematic_readability(plan, window_id?)`：验证端点覆盖、短引线、标记名称/方向/BBox、器件或标记重叠和导线穿越，返回稳定问题 ID。

规划选项：

```json
{
  "page_policy": "single_page",
  "wiring_policy": "hybrid",
  "grid_mil": 100,
  "column_gap_mil": 1000,
  "row_gap_mil": 600,
  "group_by_module": true,
  "high_fanout_primitive": "auto",
  "readability_policy": "standard_hybrid",
  "stub_lengths_mil": [200, 300, 400, 500, 600],
  "marker_clearance_mil": 100,
  "cross_region_distance_mil": 2000,
  "use_trusted_pin_directions": true,
  "preserve_existing_placements": false,
  "measured_geometry": {},
  "base_dir": null
}
```

`plan_schematic` 生成 `schematic-plan/v0.2` 的逻辑计划；`resolve_schematic_plan` 在器件落位后生成 resolved 计划。旧 `schematic-plan/v0.1` 保持可读取和比较。

同一区域且距离小于 2000 mil 的两端网络优先使用连续正交导线；跨区域、空间跨度较大或至少 3 个端点的网络使用短引线加同名网络端口；电源和地使用短引线加 Net Flag。短引线依次尝试 200/300/400/500/600 mil，并避让膨胀 100 mil 的器件 BBox、已规划标记、无关导线和引脚；普通候选失败时进入确定性外侧通道，仍无法安全放置则返回 `READABILITY_UNRESOLVED`，不生成重叠图元。

出线边由引脚相对器件 BBox 的最近边确定；左/右/上/下分别使用 `180°/0°/270°/90°`。仅可信 `IN` 映射为 `IN`，可信 `OUT/Open Collector/Open Emitter/HIZ` 映射为 `OUT`；`BI` 保持 `BI`，被动、未定义、终结器或来源冲突一律保守回退为 `BI`。网络本质仍是端点集合，不强制解释为单一“源 → 目标”。

`high_fanout_primitive="port"` 是 EasyEDA Pro v3 的兼容选择。它不改变 BoardSpec 拓扑；端口方向只按上述可信类型映射，其余显式回退为 `BI`。

### 受控写入

- `place_schematic_components`：按库 UUID、器件 UUID/名称和精确位号放置器件；同位号同器件可重复调用而不重复创建。
- `set_schematic_component_placement`：按位号移动、旋转或镜像，不更换器件身份。
- `remove_schematic_components`：按 primitive ID 删除，要求 `confirm_topology_change=true`。
- `create_schematic_wires`：解析精确引脚或坐标端点并创建避障正交导线。
- `edit_schematic_wires`：按 primitive ID 修改或删除导线。
- `place_schematic_net_labels`：放置局部网络标签；EasyEDA Pro v3 会快速返回 `API_UNAVAILABLE`。
- `place_schematic_net_ports`：放置显式 `IN`、`OUT` 或 `BI` 端口。
- `place_schematic_net_flags`：放置显式 `Power`、`Ground`、`AnalogGround` 或 `ProtectGround` 标志。
- `edit_schematic_net_markers`：按回读 primitive ID 替换或删除标签、端口和电源标志；替换时先创建并验证新图元，再删除旧图元；纯删除要求 `confirm_topology_change=true`。
- `set_schematic_no_connects`：按位号和 `#PIN` 选择器设置 No Connect。

旧 `set_no_connects` 保留为兼容接口；新工作流使用带窗口、上下文和内容 revision 保护的 `set_schematic_no_connects`。

## 写入事务协议

每个绘图写工具执行：

1. 确认 Bridge 服务身份及 EDA 已连接；
2. 固定目标 `window_id` 并读取当前状态；
3. 检查 `expected_context_revision` 和 `expected_revision`；
4. 在写入前校验整批 UUID、位号、引脚、网络、坐标和 primitive ID；
5. 采集严格 DRC 基线；
6. 在同一次 `/execute` JavaScript 中再次检查窗口/工程/页面及规范化内容版本，然后才执行首个变更；
7. 写后回读、重新计算版本、汇总实际新增/修改/删除和拓扑；
8. 再次运行严格 DRC 并返回增量。

成功响应包含 `revision_before`、`revision_after`、`readback`、`topology` 和 `drc`。部分项目失败时返回 `PARTIAL_APPLY`。Bridge 超时或写入期间 HTTP 5xx 返回 `WRITE_STATUS_UNKNOWN`；调用方必须先重新读取状态，不得直接重试。

主要诊断码包括：

- `SCHEMATIC_CONTEXT_UNAVAILABLE`、`DOCUMENT_SWITCH_UNSAFE`
- `CONTEXT_CHANGED`、`STALE_SCHEMATIC`
- `PLAN_INVALID`、`DESIGNATOR_CONFLICT`
- `COMPONENT_NOT_FOUND`、`PIN_NOT_FOUND`、`PRIMITIVE_NOT_FOUND`
- `COORDINATE_OFF_GRID`、`WIRE_PATH_INVALID`、`ROUTE_BLOCKED`
- `READABILITY_UNRESOLVED`、`READABILITY_FAILED`
- `API_UNAVAILABLE`、`PARTIAL_APPLY`
- `WRITE_STATUS_UNKNOWN`、`WRITE_VERIFICATION_FAILED`
- `TOPOLOGY_MISMATCH`、`SAVE_FAILED`

## EasyEDA API 映射与版本差异

| 能力 | EasyEDA Pro API | 3.2.186 结果 |
|---|---|---|
| 创建工程 | `dmt_Project.createProject` | beta，半离线环境不可靠 |
| 创建原理图/图页 | `dmt_Schematic.createSchematic/createSchematicPage` | 已验证 |
| 打开图页 | `dmt_EditorControl.openDocument` | 已验证，显式切换 |
| 保存 | `sch_Document.save` | 已验证 |
| 器件创建/修改/删除 | `sch_PrimitiveComponent.create/modify/delete` | 已验证 |
| 器件和引脚读取 | `sch_PrimitiveComponent.getAll/getAllPinsByPrimitiveId` | 已验证 |
| 导线创建/修改/删除 | `sch_PrimitiveWire.create/modify/delete` | 已验证 |
| 网络标签 | `sch_PrimitiveAttribute.createNetLabel` | v4 API；v3 不调用 |
| 网络端口 | `sch_PrimitiveComponent.createNetPort` | 已验证 |
| 电源/地标志 | `sch_PrimitiveComponent.createNetFlag` | 已验证 |
| 网表 | `sch_Netlist.getNetlist("Protel2")` | 已验证 |
| 严格 DRC | `sch_Drc.check(true, false, true)` | 已验证 |

本地类型包为 `@jlceda/pro-api-types@0.4.23`。类型声明存在不代表当前 EDA 版本可执行；运行时仍进行版本和回读检查。

## 真实 E2E 验收

一次性工程 `QuickPCB_Schematic_MCP_E2E_20260915_195355` 在隔离的第二个 EDA 窗口中完成，既有 AIO/STC51 工程未被切换或修改。

| 案例 | 器件 | 网络 | 节点 | 标记重叠 | 可见端点覆盖 | 严格 DRC | 重复 diff |
|---|---:|---:|---:|---:|---:|---:|---|
| MOSFET LED | 11 | 5 | 31 | 0 | 100% | 0 | 空 |
| STC51 时钟 | 25 | 21 | 76 | 0 | 100% | 0 | 空 |

两个页面均在固定既有器件位置的条件下完成网络表达修复和显式保存。拓扑集合完全一致，可读性问题为空，重复执行的新增、替换、删除和移动差异均为空。初始能力证据见 [Schematic MCP 真实 EDA E2E](evidence/schematic-mcp-e2e-2026-09-15.md)，最终可读性证据见 [Schematic 网络可读性 E2E](evidence/schematic-readability-e2e-2026-09-16.md)。

## 自动测试

- MCP 测试覆盖严格模型、单位/网格、快照与版本稳定性、窗口定向、上下文内复核、写入超时/HTTP 5xx、四边方向、可信类型映射、短引线/外侧通道、标记替换、重复调用、规划、避障、diff、拓扑、DRC 和版本差异；当前为 95 passed。
- 测试逐个把生成的 Bridge JavaScript 包装为异步函数并运行 `node --check`。
- 实机证据脚本：`mcp-server/scripts/capture_schematic_e2e.py`。
- 可读性修复脚本：`mcp-server/scripts/remediate_schematic_readability.py`。
- 最新快照、resolved plan、diff、拓扑、DRC、可读性报告和截图位于被 Git 忽略的 `out/schematic-readability-e2e-20260916/`。
