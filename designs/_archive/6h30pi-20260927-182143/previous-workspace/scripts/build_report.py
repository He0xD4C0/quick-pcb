#!/usr/bin/env python3
from pathlib import Path
import json,hashlib,datetime
ROOT=Path(__file__).resolve().parents[1]
def read(n):return json.loads((ROOT/'results'/n).read_text())
def main():
 a=read('audio.json');l=read('limits.json');p=read('power.json');pr=read('protection.json');r=read('ripple.json');s=read('startup.json');h=read('heater_capacity.json');st=read('stereo_integrated.json');v=read('artifact-validation.json');pad=read('pad_tolerance.json')
 hi16=a['nominal']['R16_high'];hi18=a['nominal']['R18_high'];lo16=a['nominal']['R16_low'];lo18=a['nominal']['R18_low']
 thd=lambda load,mv:a['distortion'][f'R{load}_{mv}mV']['thd_percent']
 tol=l['tolerance_samples'];nt=sum(x['thd_50mV']['thd_percent']>.1 for x in tol)
 nativefile=ROOT/'results/native-full-validation.json'
 native=json.loads(nativefile.read_text()) if nativefile.exists() else {'complete':False,'reason':'Full native import/readback/DRC not yet recorded.'}
 nominal_pass=all(abs(x['gain_difference_dB']-20)<=.5 and abs(x['response_20Hz_dB'])<=.5 and abs(x['response_20kHz_dB'])<=.5 and max(x['p_upper_W'],x['p_lower_W'])<=3.2 for x in [hi16,hi18]) and all(thd(load,50)<=.1 and thd(load,100)<=.5 and a['distortion'][f'R{load}_100mV']['input_Vrms']<=1 for load in [16,18])
 lines=f'''# 双 6H30Pi OTL 耳放 — v0.1 候选设计与验证报告

日期：2026-09-27。**结论：未通过整机验收，禁止接入真实耳机。** 本报告不表示 PCB 已过测或生产就绪。

本轮完成了两支 6H30Pi、双档输入、完整交流供电与分立保护的候选连接设计；实际运行了 ngspice 47。没有把不合格结果改写为通过，也没有改用半导体输出缓冲器。

## 1. 交付索引与状态

- `schematic/QuickPCB_6H30Pi_OTL_IEM_v01_review2.eprj2`：本机 EasyEDA 实际保存并通过 SQLite 完整性校验的可编辑工程。
- `schematic/6H30Pi-OTL.epro2`：EasyEDA Pro 原生可导入工程归档，内嵌项目自建符号和器件；不是图片或 KiCad 网表冒充工程。
- `schematic/6H30Pi-OTL.epru`：该归档中的原生文本源；`scripts/build_schematic.py` 可重新生成。
- `output/pdf/6H30Pi-OTL-schematic.pdf`：10 页逐引脚网络标号原理图 PDF；同名网络跨页连接。
- `boardspec.yaml` / `circuit.json` / `BOM.csv`：连接权威、符号管脚、额定值与来源。BOM 中 `alias` 是功能名，`ref` 是实际位号。
- `models/`：官方曲线提取点、两套拟合模型、误差报告；`sources/`：成功存档的厂商 PDF 及 SHA-256。
- `simulation/stereo-generic.cir`：两声道、电源和保护的完整通用模型网表；`scripts/` 是各验收夹具和复现入口。
- `results/*.json`：机器可读结果；`results/*.png`：曲线；`results/raw/`：每次 ngspice 网表、日志和波形。
- `BENCH_TEST.md`：后续假负载验证流程和停止条件。

| 层次 | 当前证据 | 结论 |
|---|---|---|
| BoardSpec / 静态连接 | {v['components']} 个器件、{v['nets']} 个网络、{v['connected_pins']} 个管脚，原生文件连接逐一比对一致 | 静态检查通过 |
| 原生 EasyEDA 全工程 | {native.get('reason','见 native-full-validation.json')} | {'已完成，见原始结果' if native.get('complete') else '尚未完成完整导入、回读和应用 DRC'} |
| 音频标称仿真 | 见下表 | 标称模型下通过所列目标 |
| 参数偏差、噪声、瞬态保护 | 见失败清单 | 未通过 |
| 实物、EMC、电气安全、PCB | 无测量 / 本阶段未做 PCB | 待测，禁止宣称合格 |

完整设计已在专用新工程 `QuickPCB_6H30Pi_OTL_IEM_v01_review2` 导入、逐页保存、回读并运行严格 DRC。165 个器件、377 个管脚、79 个网络一致。严格 DRC 的 165 条致命错误均为缺少 PCB 封装，其余错误 0、连接警告 0；本阶段未虚构封装来消除错误，因此**严格 DRC 未全部通过**。已检查原生符号显示与 PDF 排版。格式探针只是开发证据，不替代完整工程回读。未重启 Codex，未修改用户原有 EDA 工程。

## 2. 电路与最终候选值

每声道一个 6H30Pi 双三极管构成 WCF。信号经 3.5mm 输入、DPDT 高/低切换、双联 10k 对数电位器、4.7uF 输入电容进入上管；输出经过 1000uF/250V 隔直电容及独立继电器送到 3.5mm 插座。低档串联 8.2k、对地 1k，按电位器及栅极实际负载仿真。高档直通；分压支路仍挂在输入，故源阻抗影响档差。

- 每声道 RS = **127Ω / 1W / 1%**；RK = **68Ω / 1W / 1%**，CK = 2200uF/16V。
- 上管栅偏置：100k/100k，47uF 滤波，串联 47k 与 100Ω；直流等效栅阻约 97.1k，1% 最坏仍小于 100k。
- 上阳极至下栅反馈：4.7uF/250V，100Ω 栅阻，100k 栅漏；下管采用阴极自偏置。
- 中点 MID 对地 100kΩ/2W 泄放，隔直后 OUT 对地 10kΩ/2W，插座侧 100kΩ；输出电容必须在独立仪表确认放电后接触。
- 输出电容有效容量标称 1000uF，ESR 预算 0.15Ω；继电器接触电阻预算 0.15Ω。实际漏电与容量必须逐件验证。
- 一支管的 1/2/3 = P2/G2/K2，6/7/8 = P1/G1/K1，**4/5 是灯丝、9 是屏蔽**。图中是电气引脚功能，不是 PCB 焊盘图；接线按管座底视图核对。
- 保守限制：每半管 4W、50mA 连续；每支灯丝按最大 0.9A 估算；灯丝 6.0–6.6V；绝对灯丝/阴极差按 100V 控制。额定条件设计目标仍是每半管 <=3.2W。

RS 的 93.1Ω 试验值只对主模型达到很低 THD。最终改为 127Ω，使两组官方曲线对应模型在 50mV/16Ω 时分别约 0.095% 和 0.092%。这只是模型折中，不能证明实际管子一定达标；完整扫描保存在 `rs_model_balance.json`。

## 3. 标称音频验收

条件：B+=160V 理想稳压；25–27°C 模型温度；源阻抗 100Ω；音量最大；16Ω/18Ω **纯电阻**；继电器闭合。右声道电路相同；两声道共电源另有完整集成夹具。真实 IE900、DT 30 IE 的复阻抗和微音没有建模。

| 项目 | 16Ω | 18Ω | 判定 |
|---|---:|---:|---|
| 高档实际电压增益 | {hi16['gain_1k']:.4f} | {hi18['gain_1k']:.4f} | 缓冲器，均小于 1 |
| 低档实际电压增益 | {lo16['gain_1k']:.5f} | {lo18['gain_1k']:.5f} | — |
| 高低档差 / dB | {hi16['gain_difference_dB']:.3f} | {hi18['gain_difference_dB']:.3f} | 20±0.5，通过 |
| 20Hz 相对 1kHz / dB | {hi16['response_20Hz_dB']:.3f} | {hi18['response_20Hz_dB']:.3f} | ±0.5，通过 |
| 20kHz 相对 1kHz / dB | {hi16['response_20kHz_dB']:.4f} | {hi18['response_20kHz_dB']:.4f} | ±0.5，通过 |
| 100mVrms 所需输入 / Vrms | {a['distortion']['R16_100mV']['input_Vrms']:.3f} | {a['distortion']['R18_100mV']['input_Vrms']:.3f} | <1V，通过 |
| 50mVrms、1kHz THD / % | {thd(16,50):.4f} | {thd(18,50):.4f} | <=0.1，标称通过但裕量小 |
| 100mVrms、1kHz THD / % | {thd(16,100):.4f} | {thd(18,100):.4f} | <=0.5，标称通过 |

标称 Iq = {hi16['iq_A']*1000:.2f}mA/声道，上/下半管耗散 {hi16['p_upper_W']:.3f}/{hi16['p_lower_W']:.3f}W。P1/G1/K1=P2/G2/K2 电压依次约 {hi16['op']['v(pa)']:.2f}/80/{hi16['op']['v(mid)']:.2f}/0/{hi16['op']['v(k)']:.3f}V。B+=144/160/176V 与发射系数 ±20% 的 12 个应力角点中，最大半管功耗 {max(max(x['p_upper_W'],x['p_lower_W']) for x in a['corners'].values()):.3f}W；这是有限场景，不能代替制造公差包络。

输出阻抗：20Hz **{a['zout_ohm']['20']:.2f}Ω**，1kHz **{a['zout_ohm']['1000']:.2f}Ω**，20kHz **{a['zout_ohm']['20000']:.2f}Ω**。它不属于低输出阻抗耳放；真实耳机阻抗随频率变化时，端电压也会变化。不能把纯电阻频响结果宣称为 IE900 实际频响。

音量位置 0.1/0.5/1、源阻抗 <=100Ω 的档差满足目标。源阻抗 1kΩ 时约 19.28dB，**不满足** 20±0.5dB；这是已知输入条件限制。8.2k/1k 各 ±1%、电位器 ±20% 的角点档差为 {min(x['difference_dB'] for x in pad):.3f}–{max(x['difference_dB'] for x in pad):.3f}dB。

## 4. 管模型与偏差

没有借用 6H30-DR 或其他型号模型。`fit_tube.py` 从存档官方 6H30Pi-EB PDF 的矢量曲线直接提取点，拟合 Koren 方程；坐标标定、曲线路径编号和所有点均保存。主模型使用转移曲线的交错训练/留出点，留出 RMS 相对误差约 **2.42%**，最大约 **7.05%**。

同一 PDF 的两组曲线并不一致：Vp=80V、Vg=-2V 时，阳极曲线约 34.27mA，转移曲线约 45.41mA。主模型对另一族曲线 RMS 偏差约 46.7%，因此另保留阳极曲线模型。直流曲线残差不能界定小信号 THD 的误差。

32 个固定种子敏感性场景包含 B+154–164V、两半管发射系数 0.8–1.2、μ 比例 0.9–1.1、RS/RK ±1%、输出电容 ±20%。其中 **{nt}/32** 个场景在 50mV/16Ω 时超过 0.1% THD，最大 **{max(x['thd_50mV']['thd_percent'] for x in tol):.3f}%**。这些是敏感性采样，不是统计良率或完整最坏情况证明。

不包含：胆管本征噪声、微音、灯丝泄漏/耦合、经过测量验证的升温动态。正栅流只用未校准的二极管近似。ngspice Fourier 很低的 THD 值有约 0.003% 量级数值限制，不应作为仪器级精度声明。

## 5. 完整交流电源

候选 T1：**>=100VA，220VAC 初级，150VAC/0.25A、9.5VAC/5A、12VAC/0.3A 三组隔离次级**；要求供应商确认负载电压、绕组电阻、绝缘和屏蔽。初级 T630mA H 250V 保险、DPST 开关、独立螺栓 PE；高压次级 T315mA，灯丝次级 T5A。保险最终取值仍须通过实际浪涌试验。

高压：UF4007 桥、220uF/350V +22Ω/5W +220uF/350V、IRF820 串联调整、MPSA42 误差级、6.2V 基准、4.7Ω 取样限流、100uF 输出，三个高压节点配置泄放。QHV 裸片连接与冷却：G/D/S=1/2/3，tab=D，绝缘安装，目标散热器 <=8°C/W。普通开关 MOSFET 的连续线性 SOA 和闭环稳定性尚未核准，不能凭仿真功耗直接批准制作。

灯丝：9.5VAC 桥整流、15000uF/25V、LM1084 可调线性稳压；121Ω/487Ω 设定，220uF 铝电解输出并保留稳定性所需 ESR。两支灯丝并联；HMINUS 通过 150k/47k 抬升至约 38V，47uF/100V 滤波。散热器目标 <=1.5°C/W，tab=OUT，必须与接地机箱绝缘。辅助 12VAC 独立整流，以普通分立稳压和分立驱动供继电器。

市电 ±10% 仿真：B+均值 {p['hv']['0.9']['Bplus_Vmean']:.2f}–{p['hv']['1.1']['Bplus_Vmean']:.2f}V，纹波约 {min(x['Bplus_ripple_Vpp'] for x in p['hv'].values())*1000:.1f}–{max(x['Bplus_ripple_Vpp'] for x in p['hv'].values())*1000:.1f}mVpp；HV 绕组最大 {max(x['secondary_Arms'] for x in p['hv'].values()):.3f}Arms，调整管高线耗散约 {p['hv']['1.1']['pass_W_est']:.2f}W。按实际时间间隔积分计算 RMS，未用自适应采样点直接平均。

灯丝在 2.5A、市电 ±10%、储能电容 ±20% 的夹具中，最低输出 {min(x['output_min_V'] for x in h.values()):.3f}V；绕组最大 {max(x['secondary_Arms'] for x in h.values()):.2f}Arms，储能电容最大约 {max(x['bulk_ripple_Arms'] for x in h.values()):.2f}Arms，稳压器最高约 {max(x['regulator_W'] for x in h.values()):.2f}W。输出恒定来自带 1.5V dropout 的行为模型，**不表示真实稳压器无纹波/无噪声**。二极管热设计、LDO 误差/温漂/稳定性、绕组浪涌和磁场尚须实测。

完整两声道网表完成了 **10 秒冷启动电气瞬态**，此时继电器仍断开；60 秒冷启动尝试在 90 秒运行上限超时，初始化暖态夹具出现 timestep too small，**完整暖态整机仿真尚未验证**。结果和失败日志见 `stereo_integrated.json` 与 `results/raw/stereo*.log`。分块仿真不能替代这一整机门槛。其变压器是理想电压比加假定铜阻，初级并未实现反射负载；不能用它评估初级浪涌或保险分断能力。真实升温另由假设发射函数进行敏感性测试。

## 6. 噪声与纹波单独报告

- 20Hz–20kHz，理想 B+ 条件下模型内电阻等噪声：16Ω 为 {l['noise']['16']['onoise_total']*1e6:.3f}uVrms，18Ω 为 {l['noise']['18']['onoise_total']*1e6:.3f}uVrms。模型的胆管电流源本身无噪声，这绝不是整机底噪预测。
- 将通用电源模型稳态纹波 FFT 通过 B+→输出传递函数：220V/16Ω 下约 **{r['cases']['220V_16ohm']['HP_20Hz_20kHz_ripple_Vrms']*1000:.3f}mVrms**；198V/18Ω 下约 **{r['cases']['198V_18ohm']['HP_20Hz_20kHz_ripple_Vrms']*1000:.3f}mVrms**，主要是 100Hz。这是明显的低噪声设计问题，不可用于声称适合高灵敏度 IEM。
- 不包含胆管噪声、微音、变压器磁场、实际灯丝纹波/泄漏、布线地环路、稳压参考噪声。未测耳机声压级。

## 7. 瞬态、故障与不通过项

保护含分立 RC+齐纳+达林顿延时、掉 AC 复位、正负 DC 窗口检测及双继电器。继电器采用无内置续流二极管版本并用外部二极管+齐纳钳位；其引脚在工程中使用功能端名，订货封装必须核对，不能直接当 PCB 焊盘号。

| 场景 | 模型结果 | 判定 |
|---|---|---|
| 正常冷启动 | 首次接通 {pr['cases']['startup']['relay_on_first_s']:.2f}s；输出峰值 {pr['cases']['startup']['max_abs_output_V']:.3f}V | 启动冲击不合格 |
| 两声道升温不同步 | 延后至 {pr['cases']['asymmetric_warmup']['relay_on_first_s']:.2f}s；峰值 {pr['cases']['asymmetric_warmup']['max_abs_output_V']:.3f}V | 不合格 |
| 掉电 | 乐观释放延迟 {pr['cases']['power_off']['optimistic_release_after_event_s']*1000:.2f}ms；峰值 {pr['cases']['power_off']['max_abs_output_V']:.3f}V | 未建立可接受冲击界限，不放行 |
| 输出电容短路 | 线性故障代理峰值 {pr['cases']['dc_fault_positive']['max_abs_output_V']:.2f}V，约 {pr['cases']['dc_fault_positive']['optimistic_release_after_event_s']*1000:.1f}ms 释放；16Ω 能量 {pr['cases']['dc_fault_positive']['energy_into_16ohm_J']:.2f}J | 严重不合格；继电器电流/功率限值也可能超出 |
| -5V DC 注入 | 峰值 {pr['cases']['dc_fault_negative']['max_abs_output_V']:.2f}V，释放 {pr['cases']['dc_fault_negative']['optimistic_release_after_event_s']*1000:.1f}ms | 不合格 |
| 125uA 电容漏电情景 | 16Ω 稳态 DC {pr['cases']['leakage']['dc_end_V']*1000:.3f}mV | 超过 2mV |
| 空载 | DC 检测网络本身向输出注入偏置，输出约 {pr['cases']['no_load']['dc_end_V']:.3f}V | 热插拔风险，未放行 |

**故障代理不等于实际故障峰值的精确预测**：短路夹具使用 82.13V / 25Ω 戴维南源，继电器是无机械延迟的理想阈值开关，未覆盖电弧和触点焊接。它足以否定当前保护论证，不能提供真实样机的安全上界。未经耳机厂家认可的故障能量阈值，不把任意能量数字称作“耳机安全”。

`startup.json` 另运行实际曲线模型的三种上下半管发射爬升情景（继电器强制断开），最大的原始隔直后节点冲击约 {max(x['raw_out_peak_V'] for x in s['cases'].values()):.1f}V；60 秒时某延迟情景仍有 {max(abs(x['raw_out_at_60s_V']) for x in s['cases'].values()):.2f}V。因此单一固定延时不能建立安全性。所有这些爬升函数均是假设，不是测得的 6H30 升温曲线。

快速重启、输出电容开路、低阻短路、空载、输入档位跳变夹具和 1Vrms 过载电流测试也已存档。档位跳变夹具只验证给定理想跳变；没有建模具体开关触点反跳、接头插拔和 DAC 偏置，相关物理试验仍待做。低阻短路的器件热承受能力不能仅由 30ms 电气计算判定。

## 8. 为什么不能签署工程可用

1. 32 个参数情景中已有失真超标，两个官方曲线族冲突使精密 THD 预测缺少充分依据。
2. 当前高压稳压与 WCF 的组合留下约毫伏级输出电源纹波，不适合以低底噪为目标的高灵敏度 IEM。
3. 增加分立 DC 检测后，启动、电容漏电、正负 DC 故障仍没有达到放行条件；继电器不能逆转断开前已经注入耳机的能量。
4. 原生完整导入、保存与回读已完成，但严格 DRC 仍报缺少封装；完整暖态整机仿真也未收敛，不能把分块通过当作整机通过。
5. 尚无样机电气安全、温升、噪声、实际耳机阻抗和故障测量；BOM 仍含功能选型及待确认封装，不能直接采购投产。

后续若继续同一纯胆输出方案，应先解决保护与电源纹波，并用假负载和实测管曲线验证，再讨论是否满足 IEM 目标。未自行改成混合输出架构，也未通过放宽指标来宣布成功。

## 9. 主要依据

- [EHX 6H30Pi-EB 官方资料](https://shop.ehx.com/catalog/tubes-specs/6H30Pi-EB.pdf)：管脚、额定值、曲线，存档 SHA-256 见 `sources/index.json`。
- [Sovtek 官方资料](https://shop.ehx.com/catalog/addimages/6h30pi-sovtek.pdf)：交叉核对限值，采用较保守的约束。
- [WCF 拓扑分析](https://tubecad.com/2019/04/blog0462.htm)、[Koren 模型原理](https://www.normankoren.com/Audio/Tubemodspice_article.html)：拓扑与方程依据，非所用管子的厂商模型。
- [Hammond 整流供电指南](https://www.hammfg.com/es/electronics/transformers/rectifier?referer=968)：绕组 RMS 和电容纹波核算方向。
- [LM1084](https://www.ti.com/lit/ds/symlink/lm1084.pdf)、[IRF820](https://www.vishay.com/docs/91059/91059.pdf)、[MPSA42](https://www.onsemi.com/download/data-sheet/pdf/mpsa42-d.pdf)：器件额定值、引脚、稳压器使用要求。
- [Pickering 104](https://www.pickeringrelay.com/wp-content/uploads/pdfs/104-high-voltage-sil-reed-relays.pdf)：触点能力及释放时间来源。该 PDF 本机下载返回 403，仅网页读取成功，未把错误响应伪装成存档资料。
'''
 (ROOT/'DESIGN_REPORT.md').write_text(lines)
 summary={'date':'2026-09-27','release_status':'NOT_ACCEPTED','physical_test_status':'NOT_PERFORMED','pcb_scope':'NOT_DESIGNED','native_complete':bool(native.get('complete')),'static_connectivity_passed':v['static_ok'],'nominal_audio_targets_passed':nominal_pass,'native_strict_drc_passed':bool(native.get('strict_drc_passed')),'integrated_warm_simulation_passed':st['cases']['warm']['status']=='RAN','tolerance_thd_failures':nt,'tolerance_cases':len(tol),'protection_passed':False,'real_headphones_permitted':False,'model_globally_qualified':False}
 (ROOT/'results/acceptance.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
