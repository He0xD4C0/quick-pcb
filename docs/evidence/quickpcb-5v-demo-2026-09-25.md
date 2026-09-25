# Quick PCB v0.3.1 验收工程证据（2026-09-25）

## 范围

本轮在隔离工程 `QuickPCB_5V_MOSFET_LED_Demo_v031` 中验证 BoardSpec、Schematic MCP、Layout MCP、EasyEDA Pro 保存与制造文件导出。工程只驱动板载低电流 LED；输入为稳压 5 V，控制输入允许 0 V、3.3 V 或 5 V，不支持外接功率负载。

环境为 EasyEDA Pro 3.2.186。Bridge 返回服务身份 `easyeda-bridge`、`edaConnected=true`，且只有一个连接窗口。所有 EDA 写入均使用 revision 前置条件并在写入后回读。网表导入仅作为 staged 操作描述，本文没有把 staged 误写为 applied。

## 电路审核

- Q1 为 2N7002，工程审核后的引脚映射为 1=G、2=S、3=D。
- LED1 引脚映射为 1=K、2=A。
- R1 为 2.2 kΩ。按绿色 LED 1.8–2.4 V 正向压降估算，5 V 下电流约 1.18–1.45 mA；即使按电阻承受全部 5 V 计算，功耗也只有 11.4 mW。
- R2 为 2.2 kΩ 栅极串联电阻，R3 为 100 kΩ 下拉；控制输入悬空时 Q1 保持关断。
- C1 为 100 nF，最终放置在 J1 电源入口旁。

## 原理图

Schematic MCP 生成并显式保存单页原理图，标题栏为 `QPCB-001`、`V1.0`、`QP v0.3.1`、`EDA PASS`。最终回读：

- 9 个器件、19 段导线、10 个端口、9 个电源标志；
- 6 个网络、19 个节点，缺失、额外和变化项均为空；
- 可见端点证据 38/38，覆盖率 100%；
- 严格原理图 DRC 0；
- 以最终状态再次生成计划，器件移动、导线增删和冲突均为空。

最终原理图 revision 为 `sha256:fc19b3b475ef7931d5a40cf8d0f5a29e6cbe4a0c24eab8e443d549c319f6ce65`。

## PCB

PCB 为 45.72 mm × 30.48 mm 双层板，三个接口分布在板边，电源去耦、LED 电流路径和栅极控制形成独立功能区。最终状态包含 35 段 10 mil 走线、0 个过孔、1 个锁定的底层 GND 铜皮。

Layout MCP 回读结果：

- 9 个器件、6 个网络，6/6 网络均为 `complete_by_strict_drc=true`；
- 器件 BBox 重叠为空，板框外器件为空；
- 严格 PCB DRC 返回 `passed=true`、0 条违规；
- 写入前后重复读取 revision 相同；
- BoardSpec 与 PCB Protel2 回读比较为 9/9 器件、6/6 网络、19/19 节点，无缺失、额外或变化网络。

EasyEDA 本机在 2026-09-25 19:25:37 +08:00 执行 124 项 PCB DRC，界面结果为“DRC检查完成，未发现问题”。最终 PCB revision 为 `sha256:9967644d8da8b47508ef39cc73e2416bacc2b7c79dede543bf7b6067eb993337`。

## 制造文件

Gerber 导出再次经过 EasyEDA 的 DRC 门槛，界面报告“文件已生成，可直接用于PCB打样”。ZIP 包含顶/底铜、顶/底阻焊、顶/底丝印、顶层钢网、板框、PTH 钻孔、钻孔图和飞针测试文件。BOM 数量合计为 9，CPL 含 9 个唯一位号；原生 `.eprj2` SQLite 完整性检查为 `ok`。

仓库中的 `examples/quickpcb-5v-mosfet-led-demo/SHA256SUMS` 固定全部示例输入、工程源文件、制造文件和验收记录。`verify_example.py` 已从仓库根目录执行通过。

## 实物边界

本轮没有已制造、已焊接的样板，因此没有声称实物上电已经通过。样板的制造文件、逻辑拓扑和当前规则集下的 DRC 已通过；物理通过条件在 `TESTING.md` 中定义，只有真实板卡完成短路检查、0 V/3.3 V/5 V 控制和电流/节点电压测量后，才能把实物状态改为 passed。
