# 双 6H30Pi 耳放：原生单页候选工程

**2026-09-27：完整单页图已在 EasyEDA Pro 绘制、保存、重开并导出。仍是候选工程，电气和原生 DRC 验收未通过。**

## 直接打开

- [原生工程](delivery/6H30Pi-Stereo-CANDIDATE.eprj2)
- [可移植工程](delivery/6H30Pi-Stereo-CANDIDATE.epro2)
- [原生预览](delivery/6H30Pi-Stereo-CANDIDATE.png)
- [检查与未通过项报告](delivery/REPORT.md)
- [实际位号 BOM](delivery/BOM.csv)

一页包含左右声道、高低档、音量、完整交流电源及候选保护电路；138 个实体器件，79 个网络，使用真实嘉立创库和明确声明的自建例外、NET 端口、正交导线。

保存重开和原生几何／引脚回读核对通过；原生 DRC 仍为 11 项致命错误、1 项错误、0 项警告，均涉及未确认的自建器件封装／管脚到焊盘绑定。原生制造网表被前置检查阻止。输出电容漏电上限不能保证 ≤2mV，完整电源和保护故障未验收。不能直接接真实耳机，不宣称生产就绪。

`status.json` 区分图纸已交付和总体电气验收未完成。`parts.lock.json` 保留供应商原始库信息，`delivery/native-bindings.json` 记录导入重映射后的实际项目 ID。`completion-sources.json` 是补充资料审核。`boardspec.yaml`、`topology-candidate.json`、`reference-map.json` 和 BOM 使用相同的最终位号与连接依据。

## 仿真重现

需要 ngspice 和 Python。由本次新连接生成音频部分标称回归：

```sh
uv run --no-project --with numpy python scripts/simulate_candidate_audio.py
```

结果在 `simulation/audio-results.json`。这不是整机电源、容差、噪声和故障的通过报告。

## 保留的过程证据

旧设计已归档并核验恢复，入口为 `archive-pointer.json`。`evidence/eda/` 的加载测试、诊断、各次编辑与回读均为过程记录；其中 `LIBRARY-TEST-ONLY` 工程不是最终耳放工程。实际交付以 `delivery/` 为准。

本地活动工程：`/Users/he0xd4c0/Documents/LCEDA-Pro/projects/6H30Pi-Rebuild.eprj2`，仅一个原理图、一张页面。未重启 Codex，未修改其他工程。MCP 诊断修复见 `code-repair-report.md`。
