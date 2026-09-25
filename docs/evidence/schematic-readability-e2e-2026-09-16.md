# Quick-PCB Schematic 网络可读性 E2E 证据（2026-09-16）

## 结论

- 在既有一次性工程内固定全部器件位置，只替换冲突网络标记、短引线和相关导线；没有修改其它工程。
- MOSFET LED 与 STC51 时钟的 Protel2 拓扑分别保持为 11 个器件/5 个网络/31 个节点和 25 个器件/21 个网络/76 个节点，缺失、多余及错误连接均为空。
- 两页严格原理图 DRC 均为 0，可读性问题均为 0，跨区/多端网络可见端点覆盖率均为 100%。
- 两页再次执行 resolved plan diff 时所有 create/replace/delete/move 集合为空，并已分别显式保存。
- 本证据只覆盖指定 EDA 版本、一次性工程和两个单页夹具的逻辑及绘图闭环，不代表 PCB、固件、EMC、热设计、可制造性或生产验收。

## 环境与隔离

- EasyEDA Pro：`3.2.186`。
- 类型定义：`@jlceda/pro-api-types@0.4.23`。
- Bridge：`easyeda-bridge`，执行前确认服务身份且 `edaConnected=true`。
- 目标窗口：`4038b88f-92a6-4200-8038-ffee2e01f72f`。
- 一次性工程：`QuickPCB_Schematic_MCP_E2E_20260915_195355`。
- Project UUID：`3f59eb7b00dc777eaf1f51d7016c1f743e8216fd9780db3eebb0a531ec4758e8`。
- MOSFET LED Page UUID：`199c90652dcebe54`。
- STC51 Page UUID：`626a564fe369a216`。

所有写入均固定到上述窗口、工程和图页，并受 `context_revision` 与 `revision` 双重保护。页面切换和保存均为显式操作；既有器件位置保持不变。

## 最终结果

| 项目 | MOSFET LED | STC51 时钟 |
|---|---:|---:|
| 器件 | 11 | 25 |
| 网络 | 5 | 21 |
| 节点 | 31 | 76 |
| 导线（含短引线） | 29 | 72 |
| Net Port | 3 | 35 |
| Power/Ground Flag | 24 | 33 |
| No Connect | 38 | 25 |
| 拓扑缺失/多余/错误 | 0 / 0 / 0 | 0 / 0 / 0 |
| 严格原理图 DRC | 0 | 0 |
| 可读性问题 | 0 | 0 |
| 可见端点覆盖率 | 100% | 100% |
| 重复执行差异 | 空 | 空 |
| 显式保存 | 成功 | 成功 |

最终内容 revision：

- MOSFET LED：`sha256:6d373e6442e39aad22095d71af4e119b3bf440a471c4b0aaafe0c0da78c98dbe`
- STC51：`sha256:2d64afa566979b8e776201306e94e2d4fa464c6fd756f99078f5f6e5f657351a`

## 表达规则与验证

- 同一区域的两端网络使用连续正交导线；空间跨度达到 2000 mil、跨区域或至少 3 个端点的网络使用从真实引脚开始的短引线和同名 Net Port。
- 电源和地使用短引线与对应 Net Flag，不使用普通文本冒充电气连接。
- 端口方向仅来自可信引脚类型；被动、未定义或冲突来源保持 `BI`。网络作为端点集合验证，不强制推导单一源和目标。
- 可读性验证覆盖标记 BBox 与器件/其它标记重叠、短引线起止点、标记名称、方向、端点覆盖和无关导线穿越。
- EasyEDA Pro 3.2.186 不提供可用的 v4 Net Label 创建 API，因此本轮高扇出与跨区连接明确使用 Net Port。

页面截图仅用于视觉 QA，不替代快照、网表、DRC 或可读性报告。截图 SHA-256：

- `mosfet-led-page.png`：`afdcf1c1336c1fa0d4c862f98f9c73e70ae74c631e6599e31c6cee6d7723743`
- `stc51-clock-page.png`：`48c710287968c041f71a508964b13a30b0369fe5c6e6b010fd82c3d69a2f51ae`

## 可复现证据

被 Git 忽略的 `out/schematic-readability-e2e-20260916/` 保存：

- `manifest.json`
- `mosfet-led-{before-snapshot,resolved-plan,initial-diff,snapshot,diff,topology,drc,readability}.json`
- `stc51-clock-{before-snapshot,resolved-plan,initial-diff,snapshot,diff,topology,drc,readability}.json`
- `mosfet-led-page.png`、`stc51-clock-page.png`

修复入口为 `mcp-server/scripts/remediate_schematic_readability.py`。脚本默认复用已保存的 resolved plan；仅显式传入 `--refresh-plans` 才重新解析。每个案例可用 `--case` 独立运行，写入超时后停止并要求先回读，不直接重试。

## 自动验证

- MCP 测试：95 passed。
- 所有生成的 EasyEDA JavaScript：`node --check` 通过。
- `git diff --check`：通过。
- MCP 工具：53 个，其中 Schematic 27 个。

运行期 JSON 和截图用于本机复核，不提交到版本库；本文只记录可审查的结果和边界。
