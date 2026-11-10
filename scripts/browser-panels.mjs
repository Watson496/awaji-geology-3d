// Interaction fixtures expose every section; production defaults stay compact.
export async function openPanelSections(page) {
	for (const name of ["岩体の操作", "レイヤーの操作", "切断・断面図の操作"]) {
		const control = page.getByRole("button", { name, exact: true });
		if ((await control.getAttribute("aria-expanded")) === "false")
			await control.click();
	}
}
