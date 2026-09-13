# BoardSpec → 嘉立创 EDA Pro E2E 证据（2026-09-13）

## 结论

- 一次性工程 `BoardSpec_E2E_MOSFET_LED` 完成真实库解析、BoardSpec 零错误校验、模块展开、合法物理位号分配、BOM/Mermaid/Protel2 导出、EDA 导入预览与应用、原理图/PCB Protel2 回读。
- BoardSpec、EDA 原理图和 EDA PCB 的拓扑均为 11 个物理实例、5 条网络、31 个网络节点；逐项比较无缺失、无新增、无变化。
- U1 的 38 个未使用引脚均已显式 No Connect；审核后的连接引脚类型在工程库副本中生效。严格原理图 DRC 为 0。
- PCB DRC 只剩 31 个未布线焊盘，正好对应 31 个网络节点；原先的 `Netlist Error / Import Changes` 已在原理图—PCB 同步后消失。因本轮明确不做 PCB Layout/走线，这些物理连接错误不在闭环验收范围内，不能据此声称 PCB 已完成或可生产。

## 一次性工程

- 工程路径：`/Users/he0xd4c0/Documents/LCEDA-Pro/projects/BoardSpec_E2E_MOSFET_LED.eprj2`
- Project UUID：`d4504048af0eb1333408012f8092da677aa4ed14c367e86849a81f06e754d718`
- Board UUID：`2f834dcd0fbec578`
- Schematic UUID：`d13cff7c2776cd32`
- Page UUID：`2238765dcf01ef7a`
- PCB UUID：`2e64815962c98d59`
- 使用已连接的官方 MCP Bridge；未安装或重装 BoardSpec `.eext`，未修改既有示例工程。

## 锁定的真实器件来源

| 角色 | LCSC | Device UUID | Symbol UUID | Footprint UUID |
|---|---|---|---|---|
| U1 STM32F103C8T6 | C8734 | `accfc2f6010745268febab2459577079` | `3e713d8cedaf4a829e10ee0ae904ac12` | `db7d248fbf3949e6aaa163768e52acf8` |
| J1 2-pin header | C49661 | `7ae76943e7ac41e999b8d2ac980cae08` | `454b86b735ef4c9eb58937fa59491299` | `b62899a8137c4e7a995565f9824cf212` |
| C1–C5 100 nF | C82153 | `a3dffd24d450471f827cab017c45fa48` | `2b5197ad461e412480ab71fd36672a36` | `14a08379d3874582bdd84020bde81eba` |
| Q1 2N7002 | C8545 | `f8007837564a4f1fa0e6b57b81dccb0d` | `65262e964a954b63a27fe858d18f82a0` | `bdad16194d454cb292a50525f39c3ffd` |
| R1 2.2 kΩ | C25879 | `a5af5fd5005a45819ff0ab771881db3d` | `b75169e2e2c1498f874dfc4cabcaff1e` | `df9dfd54cabd403f88cae9927dcd418d` |
| R2 100 kΩ | C25741 | `acc294b6661948399f609b41c77ed19f` | `5b6d839cb6dd45f8bc4194b8b542e63d` | `df9dfd54cabd403f88cae9927dcd418d` |
| LED1 green | C9900003727 | `4fe29c140a734d7fa498982f1825f005` | `f27e3a393170428592765d36df3e60ae` | `8ed4432f9b16474d8ef6744b56521721` |

系统库 UUID 均为 `0819f05c4eef4c71ace90d822a990e87`。J1 回读确认恰好两针，未触发替换。

## 位号、类型与 No Connect

`reference_map`：顶层 `C1–C5/J1/U1` 保持原位号；`STATUS1/LED → LED1`、`STATUS1/Q → Q1`、`STATUS1/R_LED → R1`、`STATUS1/R_PD → R2`。

工程库审核：U1 `#1/#9/#24/#36/#48` 为 `Power`，`#8/#23/#35/#47` 为 `Ground`，`#15` 为 `OUT`；Q1 `#1` 为 `IN`、`#2/#3` 为 `Passive`；R/C/LED/J 的引脚为 `Passive`。其余 MCU 引脚保持 `Undefined`，并显式 No Connect：

`#2,#3,#4,#5,#6,#7,#10,#11,#12,#13,#14,#16,#17,#18,#19,#20,#21,#22,#25,#26,#27,#28,#29,#30,#31,#32,#33,#34,#37,#38,#39,#40,#41,#42,#43,#44,#45,#46`

## 自动化结果

- `boardspec-validate`：`ok: true`，`errors: []`，`warnings: []`。
- Python 测试：52 passed（核心 + MCP 模拟测试）。
- 回读比较：11/11 components、5/5 nets、31/31 nodes；missing/extra/changed 均为空。
- 原理图严格 DRC：`passed: true`，违规数组为空。
- PCB DRC：31 个 `Connection Error / Common`；仅为没有 PCB 走线的焊盘，按网络分布为 GND 12、3V3 12、LED_CTRL 3、两个内部网络各 2；无 `Netlist Error`。

## 产物

- 自包含规格：`examples/boardspec-e2e-mosfet-led.yaml`
- 展开结果：`out/BoardSpec_E2E_MOSFET_LED/expanded.yaml`
- BOM：`out/BoardSpec_E2E_MOSFET_LED/bom.csv`
- Mermaid：`out/BoardSpec_E2E_MOSFET_LED/connectivity.mmd`
- 导出 Protel2：`out/BoardSpec_E2E_MOSFET_LED/netlist.net`
- EDA PCB 回读：`out/BoardSpec_E2E_MOSFET_LED/eda-pcb-readback.net`
- EDA 原理图回读：`out/BoardSpec_E2E_MOSFET_LED/eda-schematic-readback.net`
- 自动比对：`out/BoardSpec_E2E_MOSFET_LED/roundtrip-report.json`
- EDA 审核快照：`out/BoardSpec_E2E_MOSFET_LED/eda-audit.json`
- DRC 原始结果：`out/BoardSpec_E2E_MOSFET_LED/schematic-drc.json`、`out/BoardSpec_E2E_MOSFET_LED/pcb-drc.json`

## 验收边界

这次证据只覆盖声明、校验、展开、BOM/网表导出、真实 EDA 导入、回读一致性、No Connect 和原理图电气规则。它不覆盖复位、启动配置、时钟、板框、PCB 布局、走线、SI/PI、热设计或量产准备。
