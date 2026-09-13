# EasyEDA Layout MCP v0.1

Layout MCP 是 BoardSpec 连接规格之后的独立物理实现层。它读取当前嘉立创 EDA Pro PCB，返回紧凑且可下钻的几何状态，并把模型明确请求的修改直接传给 EDA。它不修改 BoardSpec，不提供布局建议，不维护影子工程，也不调用文档保存。

## 通用约定

- 坐标和尺寸单位统一标记为 `mil`，数值保留 EDA 返回精度。
- 每个读取响应包含 `format: layout/easyeda-v0.1`、`source`、活动 PCB、查询 `range`、`revision` 和 `unit`。
- 大表使用 `{"fields": [...], "rows": [...]}`，列名只出现一次。
- `dicts.layers` 保存层 ID/名称/类型字典；大量重复的网络名通过 `dicts.nets` 的零基索引引用。字典索引只用于响应编码，写工具仍接收真实网络名和层 ID。
- 写工具必须携带最近一次读取返回的 `expected_revision`。状态已变化时返回 `STALE_LAYOUT`，不执行修改。
- 每次写入固定执行：读取状态、严格 DRC 基线、EDA 修改、状态回读、严格 DRC。修改不会自动撤销或保存。
- 写入后出现的新违规会留在画布中，由调用方根据 DRC 增量继续修正。

## 读取工具

### `get_layout_summary(cursor?, page_size=100)`

返回板框 BBox、对象计数、分页后的器件位置、网络长度/过孔统计，以及 BBox 重叠、板外器件和 DRC 类型计数。网络完成度由严格 DRC 的未布线/连接错误计数给出；空间占用是器件 BBox 并集面积与板框 BBox 面积的比值，不伪装为精确铜面积。`page_size` 限制为 1–500，`next_cursor` 为空时分页结束。

### `get_layout_components(designators?, region?, include_pads=false)`

按位号或矩形区域读取器件。`region` 为 `{left,right,top,bottom}`。启用 `include_pads` 后增加独立的列式 `pads` 表，返回焊盘 primitive ID、编号、网络字典索引、层、坐标、角度和 BBox。

### `get_layout_routing(nets?, region?)`

读取活动铜层上的 Line、Arc、Via 和 Polyline，并按网络返回确定性长度统计。各行 `net` 值是 `dicts.nets` 的索引；板框层不会混入布线结果。

### `get_board_geometry()`

返回板框、图层、物理叠层、规则区域、覆铜边界及已重建的覆铜填充。无法安全归类为布线对象的自由焊盘、图片、对象、尺寸和字符串只作为 `{id,type,bbox}` 返回。

### `get_layout_rules()`

原样返回 EDA 当前设计规则配置、网络类和差分对，不推导或替换工程规则。

### `get_layout_violations(ids?, nets?, region?)`

运行严格 PCB DRC，将 EDA 嵌套结果扁平化。稳定违规 ID 由错误类型、规则、网络、对象和位置生成，不依赖易变化的 EDA `globalIndex`。

## 写工具

### `set_component_placement(expected_revision, edits)`

每个 edit 使用位号选择器，并支持两种定位方式：

```json
{"designator":"C1","x":1200,"y":800,"rotation":90,"layer":1}
{"designator":"C1","relative_to":"U1.#24","dx":40,"dy":0,"locked":false}
```

`relative_to` 只接受现有位号或精确 `DESIGNATOR.#PAD_NUMBER`。器件层只允许 1（Top）或 2（Bottom）。

### `run_auto_layout(expected_revision)`

调用 EDA 全板 `pcb_Document.autoLayout()`。当前 API 没有局部器件参数，因此工具不提供虚假的选择范围。

### `create_route(expected_revision, net, branches, rule_overrides?)`

branch 的起点、终点和路标可使用精确焊盘选择器或 `{x,y,layer}`：

```json
{
  "start":"U1.#15",
  "waypoints":[{"x":1400,"y":900,"layer":1}],
  "end":"R1.#1"
}
```

路径在当前点所属层创建直线；后一个点改变层时，在该点创建过孔。发生换层时必须显式提供 `hole_diameter` 和 `diameter`。端点焊盘必须属于目标网络。

### `edit_routing(expected_revision, actions)`

按 `get_layout_routing` 返回的 primitive ID 修改或删除 `line|arc|via`。修改属性使用紧凑 snake_case 名称，例如 `width`、`start_x`、`angle`、`hole_diameter`；工具将其映射为 EDA 属性。

### `run_auto_routing(...)`

映射到 EDA 自动布线的网络、铜层、45/90 度拐角、保留/移除既有走线及忽略网络参数。调用前验证全部网络和铜层存在。

### `set_board_outline(expected_revision, contours, replace=false)`

每个 contour 是至少三个 `{x,y,width?}` 点，工具闭合并创建 BoardOutline 线段。已有板框时必须显式 `replace=true`；替换不是原子操作。

### `edit_keepouts(expected_revision, actions)`

创建、修改或删除 EDA Region。创建时必须提供层、非空 `rule_types` 和 `polygon`；修改时只需发送发生变化的属性。`polygon` 使用 EDA polygon source 数组，例如 `[100,100,"L",500,100,500,400]`。

### `edit_copper_pours(expected_revision, actions, rebuild=true)`

创建、修改或删除 Pour；创建时要求已有网络、活动铜层和 `polygon`，修改时只需发送变化的属性。默认在修改后调用 EDA 覆铜重建，但不会选择或改变设计规则。

## 写响应和失败语义

```json
{
  "ok": true,
  "applied": true,
  "partial": false,
  "revision_before": "sha256:...",
  "revision_after": "sha256:...",
  "results": [],
  "readback": {},
  "drc": {"before_count":0,"new":[],"resolved":[],"remaining_count":0}
}
```

参数和选择器在任何修改前整体校验。EDA 运行期仍可能部分成功；此时返回 `PARTIAL_APPLY` 和逐项结果，画布保持实际状态。`readback.changes` 是写后重新采集并与写前状态比较得到的精确图元差异，而不是对请求参数的复述。回读或写后 DRC 失败返回 `WRITE_VERIFICATION_FAILED`，并明确标记修改可能已经应用。

## 编码测量

真实 EDA E2E 可把同一步的原始采集 JSON 与紧凑 MCP JSON 交给 `scripts/measure_layout_encoding.py`。脚本记录字符数、UTF-8 字节数和 `o200k_base` token 数，但输出中的 `ratio_gate` 固定为空；这些数据仅用于观察，不作为模型或压缩率验收门槛。安装测量依赖使用 `pip install -e '.[metrics]'`。
