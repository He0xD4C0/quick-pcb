# Quick-PCB Schematic MCP 真实 EDA E2E 证据（2026-09-15）

> 这是初始绘图能力的历史证据。端口直接贴近引脚造成的图形可读性问题已在 2026-09-16 修复并重新实机验收；最终状态见 [Schematic 网络可读性 E2E](schematic-readability-e2e-2026-09-16.md)。

## 结论

- 在隔离的新 EasyEDA 窗口和一次性工程中完成 MOSFET LED、STC51 时钟两个单页原理图的器件放置、第二遍布局、混合连线、No Connect、回读、拓扑比较、严格 DRC 和显式保存。
- MOSFET LED 回读为 11 个器件、5 个网络、31 个节点；STC51 时钟回读为 25 个器件、21 个网络、76 个节点。两者与展开后的 BoardSpec 完全一致，缺失和多余集合均为空。
- 两页组件 BBox 重叠均为 0，最终严格原理图 DRC 违规均为 0。
- 本证据只覆盖指定 EasyEDA 版本、一次性工程和两个夹具的单页原理图逻辑/绘图闭环，不代表 PCB、固件、EMC、热设计、制造或生产验收。

## 隔离与环境

- EasyEDA Pro：`3.2.186`，半离线模式。
- 类型定义：`@jlceda/pro-api-types@0.4.23`。
- Bridge：`easyeda-bridge`，`http://127.0.0.1:49620`。
- 目标窗口：`0229ec04-4db4-44b6-9684-c9cc36e3e309`。
- 一次性工程：`QuickPCB_Schematic_MCP_E2E_20260915_195355`。
- Project UUID：`3f59eb7b00dc777eaf1f51d7016c1f743e8216fd9780db3eebb0a531ec4758e8`。
- 既有 AIO 微气候工程和另一个 STC51 工程窗口未被切换、保存或修改。

由于半离线环境中的 beta `createProject` 未可靠完成创建，本次一次性工程通过 EasyEDA GUI 新建。Schematic MCP 的 `create_project` 已实现安全窗口检查和状态未知处理，但不把本次 GUI 创建记为该 API 的成功实机验收。

## 最终结果

| 项目 | MOSFET LED | STC51 时钟 |
|---|---:|---:|
| Schematic/Page UUID | `e2392cf500a2247e` / `199c90652dcebe54` | `fa69b73013a882bd` / `626a564fe369a216` |
| 器件 | 11 | 25 |
| 网络 | 5 | 21 |
| 节点 | 31 | 76 |
| 直接导线 | 2 | 4 |
| Net Port | 3 | 35 |
| Power/Ground Flag | 24 | 33 |
| No Connect | 38 | 25 |
| 组件 BBox 重叠 | 0 | 0 |
| 严格原理图 DRC | 0 | 0 |
| 拓扑缺失/多余 | 0 / 0 | 0 / 0 |
| 显式保存 | 成功 | 成功 |

MOSFET LED 最终 revision：

```text
sha256:3a205c4618016f5e32d94297860161427a9421f2a0789c8167950de2b3159f02
```

STC51 时钟最终 revision：

```text
sha256:dbbfd908f50ca6c540daedef4604e61478dd4495df43ff740e7c1ca80da4b308
```

两个最终计划 diff 均为 `ok=true`：器件 create/move/conflict/extra 为空，wires/labels/ports/flags/no_connects 的 create/delete 也全部为空。

## 规划与连线策略

- 第一遍按 100 mil 网格、模块/连接度/位号稳定顺序放置；回读真实符号 BBox 后进行第二遍布局，最终无器件重叠。
- 电源和地使用显式 Net Flag。
- EasyEDA Pro 3.2.186 的 `createNetLabel` 属于 v4 API，实测调用会挂起，因此当前 v3 E2E 使用双向 Net Port 表达高扇出和标签退化连接。
- 两节点网络先尝试正交导线。路由器同时避让器件 BBox、无关引脚、已有导线和同批导线；无法安全完成的网络显式退化为 Net Port。
- MOSFET LED 使用 2 条安全导线；STC51 时钟使用 4 条安全导线，另有 8 个低扇出网络退化为 16 个端口。

## 实机发现和恢复

1. 首次 11 器件批量写入超时后只回读到 8 个器件；没有直接重试。异步执行随后完成全部 11 个器件，并产生一个引脚重合的意外网络。第二遍布局消除重叠，再按回读 primitive ID 移除意外连接。
2. Net Port/Flag 的一点式支撑图元最初被误计为导线。快照读取器现过滤退化的一点无网导线，只保留真实折线。
3. Flag 写入期间 Bridge HTTP 500，但实际部分/随后异步完成。Bridge 5xx 现带 `status_code`，所有写工具统一转换为 `WRITE_STATUS_UNKNOWN`，要求先回读。
4. EasyEDA 返回的导线路径是扁平坐标数组；读取器现按四元边解析，并通过确定性图链重建规范化折线。
5. 只避让器件 BBox 的初版路由触碰 MCU 引脚列，导致错误合并。精确删除 5 条相关导线后，路由器增加无关引脚和已有/同批导线避让，只在拓扑增量正确时保留导线。

## 可复现证据

被 Git 忽略的 `out/schematic-e2e-20260915/` 保存：

- `manifest.json`
- `capabilities.json`（API 存在性与实机结果分栏）
- `mosfet-led-{snapshot,plan,diff,topology,drc}.json`
- `stc51-clock-{snapshot,plan,diff,topology,drc}.json`
- `mosfet-led-page.png`、`stc51-clock-page.png`

采集入口：

```bash
mcp-server/.venv/bin/python mcp-server/scripts/capture_schematic_e2e.py \
  --bridge-url http://127.0.0.1:49620 \
  --window-id 0229ec04-4db4-44b6-9684-c9cc36e3e309 \
  --mosfet-page 199c90652dcebe54 \
  --stc51-page 626a564fe369a216 \
  --repo "$PWD" \
  --out out/schematic-e2e-20260915
```

脚本会显式切换一次性工程中的两个图页进行只读采集，最终恢复到 STC51 图页；它不保存或修改画布。

## 自动验证

- MCP 测试：84 passed。
- BoardSpec Core：19 passed。
- 所有生成的 EasyEDA JavaScript：`node --check` 通过。
- 50 个 MCP 工具完成注册，其中 Schematic 新增 24 个。

运行期 JSON 和截图用于复核，不提交到版本库；本文件只记录可审查的结果和边界。
