# BoardSpec DSL 规范 (board-spec/v0.1)

BoardSpec 是一种 EDA 中立的声明式连接规格。它声明「板上有哪些元件实例、哪些引脚属于同一网络」，不包含坐标、走线、层叠、焊盘、符号或封装图形——这些留给工程师在 EDA 里完成。

文本语法采用 YAML 1.2 子集；实现使用 `ruamel.yaml` 的安全解析模式，并拒绝重复键。`ON`、`OFF`、`yes`、`no` 等未加引号的标量按 YAML 1.2 解析为字符串，而非 YAML 1.1 布尔值。

## 顶层结构

```yaml
spec: board-spec/v0.1
project: {name: demo}
libraries: []     # 元件库声明
definitions: {}   # 项目级新元件 / 模块
instances: {}     # 元件实例
connections: []   # 网络 / 连接
constraints: []   # 设计规则、布局提示
outputs: []       # 导出目标
```

必填字段：`spec`、`project`、`instances`、`connections`。

## 核心语义

- `instances`：声明「板上有哪些元件实例」。
- `connections`：声明「哪些引脚属于同一个网络」，以网络为中心而非命令式连线。
- `definitions`：声明项目级新元件，两类——组合模块（`kind: module`）和物理新零件（`kind: physical`）。

## 端点语法

端点形如 `INSTANCE.PIN_OR_PORT`：

| 写法 | 含义 |
|---|---|
| `U1.PA5` | 匹配库中所有名为 `PA5` 的物理引脚 |
| `U1.VDD` | 匹配所有名为 `VDD` 的物理引脚 |
| `U1.#24` | 只匹配物理引脚编号 `24` |
| `LED1/R.1` | 模块展开后的层级实例 |

模块只通过声明的端口与外部网络连接；展开后层级实例名用 `PARENT/CHILD`。

## 组合模块 `kind: module`

由已有元件和内部网络组成，暴露端口。适合「电源模块」「LED 指示模块」等。

```yaml
definitions:
  project:StatusLED:
    kind: module
    ports:
      VCC:  {dir: power_in}
      GND:  {dir: power_in}
      CTRL: {dir: input}
    parameters:
      resistor: {default: "1k"}
    items:
      R: {part: Device:R, value: "${resistor}"}
      D: {part: Device:LED, value: Green}
    nets:
      - {net: VCC,       endpoints: [R.2]}
      - {net: CTRL_NODE, endpoints: [R.1, D.A]}
      - {net: GND,       endpoints: [D.K]}
    port_map:
      VCC: VCC
      GND: GND
      CTRL: CTRL_NODE
```

## 物理新零件 `kind: physical`

声明引脚、封装引用、符号引用。符号/封装图形由人工或库提供，LLM 只引用。

```yaml
definitions:
  project:MyModule:
    kind: physical
    pins:
      - {number: "1", name: VCC, type: power_in}
      - {number: "2", name: GND, type: power_in}
    footprint: Package_SO:SOIC-8_3.9x4.9mm_P1.27mm
    symbol: project:MyModule
    reference_prefix: U
    source:
      provider: easyeda-pro
      library_uuid: fedcba9876543210
      device_uuid: 0123456789abcdef
      device_name: MyModule-Device
      symbol_uuid: 1122334455667788
      symbol_name: MyModule-Symbol
      footprint_uuid: 8877665544332211
      supplier: LCSC
      supplier_id: C12345
      raw_pin_types: {"1": Undefined, "2": Undefined}
    review:
      status: project_reviewed
      pin_type_authority: project_library
```

`source` 固化查库时的 library/device/symbol/footprint UUID、器件/符号原名及供应商编号。Protel2 的 `PARTTYPE`/`Device` 使用 `source.device_name`，以匹配 EDA 实际库器件；`source.raw_pin_types` 保存 EDA 库原值，`pins[].type` 保存 BoardSpec 实际用于 ERC 的审核值。工具不会把 `Undefined`、`Power` 或 `Ground` 静默推断成工程方向；电源类型必须在工程库副本审核。`project_reviewed` 物理定义的每个引脚必须已连接或在实例上显式标记 No Connect。

## 显式 No Connect

```yaml
instances:
  U1:
    part: project:MyModule
    no_connects: ["#5", "#6"]
```

No Connect 只接受精确的 `#PIN_NUMBER`。不存在的引脚、重复选择器以及同一引脚既连接又 No Connect 都是错误；导出器不会为其生成伪网络。

模块展开后会生成 `reference_map`，把逻辑路径稳定映射为 EDA 位号，例如 `STATUS1/R_LED → R1`。顶层物理实例必须已经是 `U1`、`C3` 一类合法位号；模块内部物理定义必须提供 `reference_prefix`。

## 连接

```yaml
connections:
  - net: 3V3
    kind: power        # power | ground | signal | differential_pair | bus | unconnected | test
    voltage: 3.3
    endpoints: [U1.VDD, C1.1, LED1.VCC]
```

`kind` 与 `voltage` 是元数据；ERC 用它们做启发式检查（电源去耦、对地短路等）。

## 约束 `constraints`

把电气/机械/布局要求保留为声明式；不自行推导物理数值。

```yaml
constraints:
  - kind: electrical
    target: [3V3, GND]
    rule: no_short
    severity: error
```

`kind` 可选：`electrical` / `layout` / `mechanical` / `thermal` / `emc` / `other`。

## 导出目标 `outputs`

```yaml
outputs:
  - type: kicad_netlist   # 或 protel2_netlist / bom_csv / mermaid
    path: out/board.net
```

## 电气类型（pin / port 的 `dir` / `type`）

`input`、`output`、`bidirectional`、`tri_state`、`passive`、`power_in`、`power_out`、`open_collector`、`open_emitter`、`no_connect`、`free`、`unspecified`。

## ERC 规则（保守、不完整）

检测到的冲突（error）：`SCHEMA_INVALID`、`UNKNOWN_PART`、`UNKNOWN_INSTANCE`、`UNKNOWN_PIN`、`DUPLICATE_NET`、`ENDPOINT_MULTIPLE_NETS`、`PIN_CONNECTED_AND_NO_CONNECT`、`UNSPECIFIED_PIN_CONNECTED`、`INVALID_REFERENCE`、`REFERENCE_PREFIX_UNRESOLVED`、`PORT_MAP_INVALID`、`MODULE_CYCLE`、`POWER_INPUT_UNCONNECTED`、`OUTPUT_CONFLICT`、`POWER_SHORT_TO_GROUND`。

启发式警告（warning）：`MISSING_DECOUPLING`、`MISSING_PULLUP`、`UNCONNECTED_PIN`、`INCOMPLETE_PART_DATA`、`FOOTPRINT_UNCONFIRMED`。

警告不是通过证明；`INCOMPLETE_PART_DATA`、`FOOTPRINT_UNCONFIRMED` 或库适配器不可用时，应让工程师验证来源后再进入 EDA。
