/**
 * 导入网表：读本地 Protel2 文本网表 → 写入当前工程。
 *
 * BoardSpec 导出的网表用 Protel2 格式（`[`/`(` 文本网表），对应
 * `ESYS_NetlistType.PROTEL2`（Altium Designer）。
 *
 * 嘉立创 EDA 的网表导入目标是当前 PCB：它会在确认窗口中预览新增
 * 封装、焊盘网络和其它差异。插件不会自动确认或布局这些变更。
 */
const SUPPORTED_EXTENSIONS = ['.net', '.txt'];

export async function importNetlist(): Promise<void> {
	const file = await eda.sys_FileSystem.openReadFileDialog(SUPPORTED_EXTENSIONS, false);
	if (!file) {
		return;
	}

	const netlist = (await file.text()).replace(/\r\n|\r|\n/g, '\r\n');
	if (!netlist || !netlist.trim()) {
		eda.sys_Dialog.showInformationMessage('网表文件为空', 'BoardSpec');
		return;
	}

	try {
		await eda.pcb_Net.setNetlist(ESYS_NetlistType.PROTEL2, netlist);
		eda.sys_Dialog.showInformationMessage('网表已载入 PCB 导入预览', 'BoardSpec');
	}
	catch (error) {
		eda.sys_Dialog.showInformationMessage(
			`网表导入失败：${error instanceof Error ? error.message : String(error)}`,
			'BoardSpec',
		);
	}
}
