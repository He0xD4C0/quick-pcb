# 本地代码定位与修复 — 2026-09-27

## 已定位的原生行为

安装的嘉立创EDA Pro 3.2.186中：

- `pro-ui/3.2.181.db96fbff/js/ui.js` 的 `SCH_DrcUtil.check` 调用 `checkERC`，即使 `includeVerboseError=true` 也仅组装 `{type,count}`。详细诊断同时通过 `bottomBarLog` / `schDrcLog` 发出。
- `pro-sch/3.2.181.b4201c52/js/sch.js` 的 `mj → E3 → uy` 是原生网表导出路径。致命错误不为零时不进入序列化回调，`mj`因此返回undefined。重复改用Protel2/DSNET不会修复缺失封装。
- 该导出路径还可能重新注释位号/Unique ID并执行`saveAllFiles`；不能把它简单视为绝无副作用的纯读取。当前验证仅在已授权保存的独立测试工程内执行。通用读取接口的历史行为仍是后续兼容性工作。

原始日志、源文件绝对路径和SHA-256保存在 `evidence/eda/native-diagnosis.json`。

## 代码修复

1. `schematic_bridge.py`：一次严格检查期间临时订阅原生诊断流，finally取消订阅；不清空日志、不改变规则。兼容hook不存在时仍保留原生返回值。
2. `schematic_drc_log.py`：安全解析HTML文本与i18n参数，提取实际对象ID和页面；保留未被明细覆盖的非零数量，缺失/false结果不能当通过；新版本详细返回避免与日志重复计算。
3. `tools.py`：空/undefined/非字符串网表返回 `NETLIST_UNAVAILABLE`，经MCP现有协议转为ToolError；不再返回`ok=true`的空网表。状态捕获也保留网表失败原因。
4. `no_connect_program`：允许同一物理器件的多个符号单元，按真实脚号跨单元定位；不明确或重复的脚号拒绝写入。
5. 测试工程生成器默认拒绝再次产生缺少管座封装的工程；保存检查脚本改为记录实际DRC结果，不再硬编码旧数量。

兼容诊断hook是针对本机3.2版本的受控适配，不保证所有未来EDA版本均提供该私有总线；回退时不会误报通过。

## 实际验证

- `mcp-server/.venv/bin/python -m pytest mcp-server/tests -q`：122 passed。
- 额外启动仓库版Schematic MCP子进程进行真实stdio调用：`get_schematic_violations`返回structuredContent、4条带对象ID的诊断、`passed=false`，业务DRC失败按约定`isError=false`。证据为 `evidence/eda/mcp-stdio-diagnostics.json`。
- 新回归覆盖真实3.2日志、i18n嵌套对象、残缺明细、false/空返回、订阅异常清理、多单元脚号歧义和空网表。
- 在唯一测试页对V1的1/2/3/4/5/7/8/9、J1的1/2、RV1的1–6设置No Connect；这些脚仅在加载测试中刻意不用，不能沿用到耳放电路。
- 保留R1.1—J1.3及R1.2—V1.6的测试连接；保存、关闭本任务页面、重新打开后16项No Connect仍在，符号单元和管脚集合一致。
- 更新 `.eprj2`/`.epro2` 测试证据和SHA-256，SQLite完整性ok。
- 本次调用直接使用仓库代码；未修改安装目录、未重启Codex、未重新安装已缓存的0.3.1插件。

## 剩余真实设计错误

原生严格DRC当前仍为 **3 fatal + 1 error + 0 warning**：V1.A/B/H无Footprint；1–9脚无对应焊盘。详细读取问题和悬空警告已修复，**原生加载关卡仍未通过**。

此前例外中的Belton VT9-ST-C是面板焊线型，不能把未审核的任意九脚PCB封装塞入属性来消除错误。必须完成真实管座/外部端子的物理定义，再做网表一致性验收。所有DRC规则保留。

这仍是加载测试工程，不是完整耳放工程；整机仿真和实物测试未完成。取消此前对用户DRC截图/文字的依赖。
