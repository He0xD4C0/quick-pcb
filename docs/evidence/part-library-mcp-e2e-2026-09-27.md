# Library MCP 嘉立创系统库只读 E2E（2026-09-27）

## 环境

- Quick PCB：v0.4.0 工作树
- 官方 Bridge：`http://127.0.0.1:49620`
- Bridge 身份：`easyeda-bridge`
- EDA 状态：`edaConnected=true`，3 个窗口连接
- 活动窗口：`3fcec9b3-812e-4746-a0aa-5d3f2e82db75`

本轮仅调用 `eda.lib_Device.search`、`eda.lib_Device.getByLcscIds`、`eda.lib_Device.get`、符号归档读取和封装读取。没有调用工程/文档创建、打开、保存、图元修改或网表导入 API。

## 候选表查询

`search_parts("100nF 0402", page=1, page_size=3)` 返回：

- `ok=true`
- `format=parts/easyeda-v0.1`
- `returned=3`
- `next_page=2`
- C 编号：`C1525`、`C307331`、`C25079`
- 固定列覆盖身份、制造商、描述、装配分类、数据手册、CAD UUID、CAD 完整度、品类属性和缺失项。

表格中的容量、精度、耐压和温度系数保持嘉立创原始键值；工具没有换算单位或生成适用性评分。

## 精确 C 编号查询

`get_parts_by_lcsc_ids(["C1523", "C2150"])` 返回两行且 `missing_lcsc_ids=[]`：

- `C1523` → `0402B102K500NT`
- `C2150` → `SS8050(RANGE:200-350)_C2150`

查询使用 `allowMultiMatch=true`，不会在同一 C 编号存在重复库记录时静默选第一项。

## 单件详情与引脚溯源

对 C1523 的 device/library UUID 调用 `get_part`：

- 器件：`0402B102K500NT`
- 真实引脚：2 枚，编号 `1`、`2`
- 原始引脚类型：两枚均为 `IN`
- `pinSource.kind=EasyEDA symbol archive`
- 符号 UUID：`b1ff2babae254708b1720c9728a80208`
- 系统库 UUID：`0819f05c4eef4c71ace90d822a990e87`
- `board_spec_definition.review.status=unreviewed`
- 本次无引脚解析警告

## 非修改证据与边界

查询前后 Bridge 的活动窗口 ID、窗口数量和三个窗口 ID 完全一致。Library MCP 的四个工具均标记为只读，且实现不生成 EDA 文档写代码。

以上只证明嘉立创 EDA 系统库的工程/CAD 数据可查询。该数据源不提供经过本工具验证的实时价格、库存、交期或生命周期，不能把“基础库/扩展库”解释为当前可采购性证明。
