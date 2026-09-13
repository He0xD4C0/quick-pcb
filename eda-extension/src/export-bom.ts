/**
 * 导出 BOM：调用嘉立创 EDA 的 BOM 导出，产出 xlsx/csv 文件。
 *
 * BoardSpec 侧的 BOM CSV 由 MCP 的 `export` 工具生成；本插件菜单提供
 * 在 EDA 内直接导出当前工程 BOM 的入口，供工程师交叉核对。
 */
export async function exportBom(): Promise<void> {
	try {
		const bomFile = await eda.pcb_ManufactureData.getBomFile('BoardSpec_BOM', 'xlsx');
		if (bomFile) {
			await eda.sys_FileSystem.saveFile(bomFile, 'BoardSpec_BOM.xlsx');
			eda.sys_Dialog.showInformationMessage('BOM 已导出', 'BoardSpec');
		}
	}
	catch (error) {
		eda.sys_Dialog.showInformationMessage(
			`BOM 导出失败：${error instanceof Error ? error.message : String(error)}`,
			'BoardSpec',
		);
	}
}
