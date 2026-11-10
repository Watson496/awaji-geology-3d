// 操作の検証では全セクションを開き、本番の初期表示と分ける。
export async function openPanelSections(page) {
	for (const name of ["岩体の操作", "レイヤーの操作", "切断・断面図の操作"]) {
		const control = page.getByRole("button", { name, exact: true });
		if ((await control.getAttribute("aria-expanded")) === "false")
			await control.click();
	}
}
