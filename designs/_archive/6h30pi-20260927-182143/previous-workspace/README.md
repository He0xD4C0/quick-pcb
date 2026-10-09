# 双 6H30Pi 立体声 OTL — 候选工程 v0.1

**未通过验收，禁止接真实耳机。** 高/低两档、双联音量、完整交流电源及分立保护已经形成候选文件并运行仿真；参数偏差、供电纹波和故障保护存在明确问题。EasyEDA 完整工程已导入、保存并回读，原生连接一致；严格 DRC 仍有 165 条缺少 PCB 封装错误。完整暖态整机仿真未收敛，不能称为工程定稿。

先读 [设计与验证报告](DESIGN_REPORT.md) 和 [验收状态](results/acceptance.json)。

## 文件

- [10页原理图 PDF](output/pdf/6H30Pi-OTL-schematic.pdf)
- [EasyEDA Pro 原生导入归档](schematic/6H30Pi-OTL.epro2)，已在 EasyEDA 3.2.186 半离线版实际导入。
- [EasyEDA 实际保存的可编辑工程](schematic/QuickPCB_6H30Pi_OTL_IEM_v01_review2.eprj2)
- [BoardSpec](boardspec.yaml)、[BOM](BOM.csv)、[连接与功能名](circuit.json)
- [SPICE 双声道电源/保护完整网表](simulation/stereo-generic.cir)
- [假负载测试与停止条件](BENCH_TEST.md)
- [模型拟合](results/model_fit.png)、[音频与输出阻抗](results/audio_response.png)、[保护失败波形](results/protection_response.png)

原理图采用逐引脚网络标号表达。功能别名如 RSL/CBL 在器件值后方方括号中，实际位号见 BOM。项目符号是自建的；面板器件、变压器和继电器部分采用功能端名，PCB焊盘和采购封装尚未确认。本阶段不包含PCB。

## 可重复运行

实测环境：Python3.12、ngspice47、macOS。依赖版本固定在 `requirements.txt`。

```sh
cd /path/to/6h30pi-otl-iem
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
# 安装并确认 ngspice 47 可从 PATH 调用后：
./scripts/run_all.sh
```

可在其他当前目录运行绝对路径 `scripts/run_all.sh`；脚本依自身位置定位数据。`QPCB_PYTHON=/absolute/path/python` 可复用已有依赖环境。SPICE原始数据写入 `results/raw/`；多数脚本遇到运行错误会停止；整机集成夹具会记录失败为 UNVERIFIED 并继续生成报告。脚本完整执行只代表测试流程完成，**不等于验收通过**；看 `results/acceptance.json`。

`simulation/stereo-generic.cir` 从其所在目录执行 `ngspice -b stereo-generic.cir`。各夹具的具体网表位于 `results/raw/*.cir`，迁移目录后用脚本重新生成其中的模型绝对路径。

BoardSpec 可用本仓库 `mcp-server/.venv/bin/python .agents/skills/board-spec/scripts/validate.py <绝对路径>/boardspec.yaml` 复核；当前无连接错误，未指定PCB封装会产生正常的未确认警告。应用DRC、实物测试和仪器测量是独立门槛。

## EasyEDA 原生验证

专用新工程 `QuickPCB_6H30Pi_OTL_IEM_v01_review2` 已导入、逐页保存及回读。165 个器件、377 个管脚、79 个网络一致；原生 DRC 的 165 条致命错误均为缺少封装，其他错误 0、警告 0。完整证据见 `results/native-full-validation.json` 和 `results/native-readback/`。项目符号可编辑，但未指定 PCB 封装，不可直接转板生产。

`verify_native.py` 是本机证据采集脚本，绑定本次专用工程 UUID 并在写入前核对身份，不属于离线复现入口。移到其他机器后，应将 `.epro2` 导入**新工程**，不要覆盖已有工程。当前工作未重启 Codex；以后需要重启时仍须先取得用户批准。
