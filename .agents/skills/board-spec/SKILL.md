---
name: board-spec
description: 将电路需求转换为 EDA 中立的 BoardSpec YAML，并校验、展开模块及导出 BOM、KiCad 或 Protel2 交换网表。用于声明元件、网络和工程约束，并可通过受控桥接预览、应用及回读嘉立创 EDA Pro PCB 网表；不用于生成原生 KiCad/Altium 工程、布局、坐标或走线。
---

# BoardSpec

把电路设计意图写成可审查、可 diff 的连接规格。LLM 声明“有什么、连到哪”；确定性工具负责结构校验、元件库解析、模块展开和导出；工程师负责器件确认、原理图复核与 Layout。

## 必守边界

- 只声明元件实例、逻辑网络、可复用模块、约束和导出目标。
- 不生成原生 KiCad/Altium 工程文件，不选择坐标、走线、层叠、焊盘、符号图形或封装图形。
- 引脚名称和编号必须来自用户提供的可信库、项目 `kind: physical` 定义或查库工具；不得凭记忆补写。
- 物理定义必须保留 library/device/symbol/footprint UUID、库原始引脚类型和审核状态；`Undefined`、`Power`、`Ground` 不得被静默推断为工程电气方向。
- No Connect 只接受精确 `#PIN_NUMBER`，且同一引脚不能既连接又标记 No Connect；网表导出不得制造伪网络。
- 显式声明每个电源域和地。不要用隐式全局电源符号掩盖连接关系。
- 只有结构校验和元件/引脚解析都成功时，才称规格“已校验”。使用演示库或不完整库时必须明确降级结论。
- 新建规格时返回完整 YAML。修改已有规格时，只有在调用方能应用 RFC 6902 JSON Patch 且最终完整规格已重新校验时才返回 Patch；否则返回完整 YAML。
- 把电气、机械或布局要求保留为声明式 `constraints`；不要自行推导未提供的物理数值。

## 工作流

1. 从需求中识别电源域、地、接口、关键器件、额定值、约束和所需输出。把缺失或冲突的信息列为待确认项。
2. 创建或修改规格前，读取 [BoardSpec v0.1 Schema](references/board-spec-v0.1.schema.json)。需要调用本地脚本或外部工具时，再读取 [工具与 CLI 契约](references/tools.md)。
3. 先查库再写端点。优先使用用户给定的元件库/数据表；本 Skill 自带的 `parts.demo.json` 仅用于示例和自测。
4. 生成完整 BoardSpec YAML。项目级复用电路优先建成 `definitions.<id>.kind: module`。
5. 运行 `scripts/validate.py`。根据结构化错误修正后重跑，直到无错误；不要静默删除有问题的连接。
6. 若用户要求平坦网表或 BOM，先运行 `scripts/expand.py`，再运行相应导出器。存在任何验证错误时停止导出。
7. 进入 EDA 时先预览导入差异；只有位号、网络及引脚集合与展开图完全一致才应用。应用后回读 Protel2，按“网络名 → 物理位号 → 引脚号”逐项比较。
8. 交付规格、实际运行的校验摘要、警告，以及需要工程师确认的器件/封装/电气问题。不要把未走线 PCB 的连接 DRC、脚本未覆盖的 ERC 或布局审查描述成已完成。

## 最小规格

```yaml
spec: board-spec/v0.1
project:
  name: demo
libraries: []
definitions: {}
instances: {}
connections: []
constraints: []
outputs: []
```

端点使用 `INSTANCE.PIN_OR_PORT`。`PIN_OR_PORT` 为逻辑名称时会匹配库中所有同名物理引脚；使用 `#PIN_NUMBER` 可指定单个物理脚。模块只通过声明的端口与外部网络连接；模块展开后层级实例名使用 `PARENT/CHILD`。

## 诊断处理

诊断对象必须包含 `code`、JSON Pointer `path`、`message`，并在能给出安全建议时包含 `hint`。重点处理：

- `SCHEMA_INVALID`、`UNKNOWN_PART`、`UNKNOWN_INSTANCE`、`UNKNOWN_PIN`
- `DUPLICATE_NET`、`ENDPOINT_MULTIPLE_NETS`、`PORT_MAP_INVALID`、`MODULE_CYCLE`
- `PIN_CONNECTED_AND_NO_CONNECT`、`UNSPECIFIED_PIN_CONNECTED`
- `INVALID_REFERENCE`、`REFERENCE_PREFIX_UNRESOLVED`
- `POWER_INPUT_UNCONNECTED`、`OUTPUT_CONFLICT`、`POWER_SHORT_TO_GROUND`
- `MISSING_DECOUPLING`、`MISSING_PULLUP`、`UNCONNECTED_PIN`

警告不是通过证明。尤其是 `INCOMPLETE_PART_DATA`、`FOOTPRINT_UNCONFIRMED` 或库适配器不可用时，应让工程师验证来源后再进入 EDA。

## 参考资源

- [Schema](references/board-spec-v0.1.schema.json)：每次创建或修改规格时读取。
- [工具与 CLI 契约](references/tools.md)：需要查库、校验、展开或导出时读取。
- [状态 LED 示例](examples/status-led.yaml)：仅在需要模块示例时读取；其演示元件库不是生产数据源。
