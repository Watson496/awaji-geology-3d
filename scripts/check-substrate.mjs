import { openPanelSections } from "./browser-panels.mjs";
import { chromium } from "@playwright/test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
const browser = await chromium.launch({
	channel: "chrome",
	headless: true,
	args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
});
try {
	const page = await browser.newPage({
			viewport: { width: 1440, height: 1000 },
		}),
		errors = [];
	page.on("pageerror", (e) => errors.push(e.message));
	page.on("console", (m) => {
		if (m.type() === "error") errors.push(m.text());
	});
	const model = JSON.parse(await readFile("web/data/model.json", "utf8"));
	const report = JSON.parse(
		await readFile("web/data/reference/metrics.json", "utf8"),
	).fault_conditioning.substrate;
	const cover = JSON.parse(
		await readFile("web/data/surficial-cover.json", "utf8"),
	).units;
	await page.goto("http://127.0.0.1:4173");
	await page.waitForFunction(() => window.__awaji?.ready);
	await openPanelSections(page);
	// The interaction fixture below starts without overlays; initial defaults are verified separately.
	for (const [field, label] of [
		["surfaceEnabled", "地表地質図"],
		["faultPlanes", "地下の推定面"],
	]) {
		if (await page.evaluate((f) => window.__awaji[f], field))
			await page.getByRole("button", { name: label, exact: true }).click();
		await page.waitForFunction((f) => !window.__awaji[f], field);
	}

	await page
		.getByRole("button", { name: "出典・推定条件", exact: true })
		.click();
	const dialog = page.getByRole("dialog");
	await dialog.getByText("被覆層下の区分未確定", { exact: true }).waitFor();
	for (const [key, row] of Object.entries(report.under_cover)) {
		const r = dialog.getByRole("row").filter({ hasText: key });
		assert.equal(
			await r
				.getByRole("cell", {
					name: `${(row.unknown_fraction * 100).toFixed(1)}%`,
					exact: true,
				})
				.count(),
			1,
		);
	}
	await page.screenshot({ path: "artifacts/substrate-evidence-report.png" });
	await page.getByRole("button", { name: "出典を閉じる", exact: true }).click();
	for (const unit of model.units.filter((u) => cover[u.key])) {
		await page
			.getByRole("textbox", { name: "凡例を検索", exact: true })
			.fill(unit.key);
		const input = page.getByRole("textbox", {
			name: `${unit.name}の不透明度（数値）`,
			exact: true,
		});
		await input.fill("0");
		await input.press("Tab");
		await page.waitForFunction(
			(id) => window.__awaji.unitOpacity[id - 1] === 0,
			unit.id,
		);
	}
	await page.getByRole("textbox", { name: "凡例を検索", exact: true }).fill("");
	await page.getByRole("button", { name: "鉛直切断", exact: true }).click();
	await page.waitForFunction(() => window.__awaji.volumeCut);
	assert.ok((await page.evaluate(() => window.__awaji.bodyCount)) > 5);
	await page.screenshot({ path: "artifacts/substrate-beneath-cover.png" });
	assert.deepEqual(errors, []);
	console.log(
		"Substrate evidence table, hidden cover transparency, retained rock bodies and arbitrary clipping passed.",
	);
} finally {
	await browser.close();
}
