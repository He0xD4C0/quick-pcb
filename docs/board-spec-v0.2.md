# BoardSpec DSL 规范（board-spec/v0.2）

BoardSpec v0.2 在 v0.1 的命名网络模型上增加匿名局部连接，适合以连续导线为主的模拟原理图。元件、引脚、模块、约束和导出格式继续沿用 v0.1；坐标与导线几何仍由 `schematic-plan` 和 EDA 层处理。

## 连接形式

```yaml
connections:
  - net: VCC_9V
    kind: power
    voltage: 9
    endpoints: [J1.#1, C1.#1]

  - connect: [C1.#2, R1.#1]
```

- `net + endpoints` 是显式命名网络，可被约束、模块端口、调试记录和图面标记引用。
- `connect` 是匿名局部网络，只声明这些端点电气等价；至少包含两个不同端点。
- 两种写法互斥。v0.1 仍只接受命名网络。

## 展开与导出

- 匿名连接先展开模块端口，再把排序后的实际端点计算为稳定名称 `N_AUTO_<SHA256前12位大写十六进制>`。
- 展开结果中的连接包含 `net_origin: explicit | generated`。导出器继续为每个真实电气节点写出网络名，因此 KiCad、Protel2 和 Mermaid 输出保持完整。
- 匿名网络名是内部身份，不应显示为 Net Port，也不能作为 `constraints[].target` 或模块 `port_map` 的目标；需要引用时应改用显式 `net`。

## 连续导线原理图

`plan_schematic(..., net_annotation_policy="sparse_named")` 会启用连续布线策略：

- 显式信号网络只放一个 Net Port；显式电源和地各放一个 Flag。
- 匿名网络不放任何标记。
- 两端及多端网络都使用确定性的正交导线树；匿名网络路由失败时返回错误，不退化成内部名称端口。
- 电气验收仍以展开后的端点集合和 EDA 原生网表回读为准。
