# Layout 编码测量与联调状态（2026-09-14）

## 编码测量冒烟

使用 100 条走线的合成输入验证 `scripts/measure_layout_encoding.py`。这不是实际 PCB 的压缩率结论，只用于确认字符与 token 记录链路可工作。

| 表示 | 字符 | UTF-8 字节 | `o200k_base` tokens |
|---|---:|---:|---:|
| 重复键原始 JSON | 10483 | 10483 | 3905 |
| `fields + rows` 与网络字典 | 2505 | 2505 | 1839 |

测量输出的 `ratio_gate` 为 `null`，不设压缩率门槛，也不把该 tokenizer 或任何模型作为产品验收条件。

## 真实 EDA 联调边界

本轮检查时 49620–49629 端口没有可用 EasyEDA bridge，`bridge_status` 返回 `BRIDGE_UNAVAILABLE`。因此尚未执行一次性测试 PCB 上的真实画布写入、写后回读和 DRC；真实 EDA JSON 的对应测量也应在桥与 `run-api-gateway.eext` 连通后补录。
