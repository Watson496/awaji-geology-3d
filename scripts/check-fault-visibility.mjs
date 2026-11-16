import { openPanelSections } from "./browser-panels.mjs";
import { chromium } from "@playwright/test";
import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";
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
	page.on("pageerror", (e) => errors.push(e.stack));
	page.on("response", (r) => {
		if (r.status() >= 400) errors.push(`${r.status()} ${r.url()}`);
	});
	await page.goto("http://127.0.0.1:4173");
	await page.waitForFunction(() => window.__awaji?.ready);
	await openPanelSections(page);
	// 操作の検証は重ね合わせ図を非表示にして始める。初期表示は別に検証する。
	for (const [field, label] of [
		["surfaceEnabled", "地表地質図"],
		["faultPlanes", "地下の推定面"],
	]) {
		if (await page.evaluate((f) => window.__awaji[f], field))
			await page.getByRole("button", { name: label, exact: true }).click();
		await page.waitForFunction((f) => !window.__awaji[f], field);
	}

	const before = await page.evaluate(() => window.__awaji),
		catalog = JSON.parse(await readFile("web/data/fault-display.json", "utf8"));
	assert.equal(before.mode, "unified");
	assert.equal(before.faultPlanes, false);
	assert.equal(before.faultTraceMaterialTransparent, true);
	assert.equal(before.faultCount, catalog.faults.length);
	await page.screenshot({ path: "artifacts/official-faults-volume.png" });
	await page.getByRole("button", { name: "断層線", exact: true }).click();
	await page.waitForFunction(() => window.__awaji.faultCount === 0);
	await page.screenshot({ path: "artifacts/official-faults-hidden.png" });
	await page.getByRole("button", { name: "断層線", exact: true }).click();
	assert.equal(
		await page
			.getByRole("button", { name: "活断層データ", exact: true })
			.count(),
		0,
	);
	await page
		.getByRole("combobox", { name: "表示する断層", exact: true })
		.click();
	await page
		.getByRole("option")
		.filter({ hasText: "野島断層" })
		.first()
		.click();
	await page.waitForFunction(() => window.__awaji.faultCount === 1);
	assert.deepEqual(
		(await page.evaluate(() => window.__awaji)).unitOpacity,
		before.unitOpacity,
	);
	await page.getByRole("button", { name: "地下の推定面", exact: true }).click();
	await page.waitForFunction(() => window.__awaji.faultPlaneCount === 1);
	await page.screenshot({ path: "artifacts/official-nojima-surface.png" });
	const download = page.waitForEvent("download");
	await page.getByRole("button", { name: "GLB", exact: true }).click();
	await (await download).saveAs("artifacts/official-faults.glb");
	await page.getByRole("button", { name: "地下の推定面", exact: true }).click();
	await page
		.getByRole("button", { name: "都市圏活断層図", exact: true })
		.click();
	await page.waitForFunction(() => window.__awaji.activeMap);
	await page.getByRole("button", { name: "真上から", exact: true }).click();
	await page.screenshot({ path: "artifacts/gsi-active-fault-map-view.png" });
	await page
		.getByRole("button", { name: "都市圏活断層図", exact: true })
		.click();
	await page.getByRole("button", { name: "断面図", exact: true }).click();
	await page.waitForFunction(() => window.__awaji.showDiagram);
	await page.getByRole("combobox", { name: "比較断面", exact: true }).click();
	await page
		.getByRole("option", { name: "明石（1990）A–B", exact: true })
		.click();
	await page.getByRole("img", { name: "距離と標高の地質断面図" }).waitFor();
	assert.ok(
		Number(
			await page.locator(".section-diagram image").getAttribute("height"),
		) <= 185.001,
		"reference image must share the elevation axis scale",
	);
	await page.screenshot({ path: "artifacts/official-section-comparison.png" });
	assert.ok((await page.locator(".section-diagram path").count()) > 5);
	assert.equal(await page.locator(".fault-label").count(), 0);
	assert.deepEqual(errors, []);
	await writeFile(
		"artifacts/official-faults-browser.json",
		JSON.stringify(
			{
				errors,
				displayFaultCount: catalog.faults.length,
				verified: [
					"fault lines drawn after transparent bodies",
					"unified detailed traces with original source provenance",
					"optional Nojima underground surface",
					"GLB export",
					"GSI reference texture",
					"unfolded section with distance/elevation axes",
				],
			},
			null,
			2,
		),
	);
	console.log(
		"Unified fault traces, urban active-fault map and unfolded section passed.",
	);
} finally {
	await browser.close();
}
