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
			viewport: { width: 1440, height: 1050 },
		}),
		errors = [];
	page.on("pageerror", (e) => errors.push(e.message));
	page.on("console", (m) => {
		if (m.type() === "error") errors.push(m.text());
	});
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

	const model = JSON.parse(await readFile("web/data/model.json", "utf8"));
	const initial = await page.evaluate(() => window.__awaji);
	assert.equal(initial.mode, "unified");
	assert.ok(initial.bodyCount > 5);
	assert.equal(await page.getByLabel("表示形式", { exact: true }).count(), 0);
	const diagram = page.getByRole("button", { name: "断面図", exact: true }),
		surface = page.getByRole("button", { name: "地表地質図", exact: true }),
		rocks = page.getByRole("button", { name: "岩体を一括表示", exact: true });
	await diagram.click();
	await page.waitForFunction(() => window.__awaji.showDiagram);
	await page.getByRole("img", { name: "距離と標高の地質断面図" }).waitFor();
	assert.equal(
		(await page.evaluate(() => window.__awaji)).bodyCount,
		initial.bodyCount,
	);
	await surface.click();
	await page.waitForFunction(() => window.__awaji.surfaceVisible);
	const alpha = page.getByRole("slider", {
		name: "地表地質図の不透明度",
		exact: true,
	});
	await alpha.press("Home");
	await page.waitForFunction(
		() => window.__awaji.surfaceOpacity === 0 && !window.__awaji.surfaceVisible,
	);
	assert.equal(
		(await page.evaluate(() => window.__awaji)).surfaceEnabled,
		true,
	);
	await alpha.press("End");
	await page.waitForFunction(() => window.__awaji.surfaceOpacity === 100);
	const unit = model.units.find((u) => u.key === "K21_pim_a");
	await page
		.getByRole("textbox", { name: "凡例を検索", exact: true })
		.fill(unit.key);
	await page
		.getByRole("button", { name: `${unit.name}を非表示`, exact: true })
		.click();
	await page.waitForFunction(
		(n) => window.__awaji.bodyCount === n - 1,
		initial.bodyCount,
	);
	const individual = await page.evaluate(() => window.__awaji.unitOpacity);
	await rocks.click();
	await page.waitForFunction(() => window.__awaji.bodyCount === 0);
	assert.equal(
		(await page.evaluate(() => window.__awaji)).surfaceVisible,
		true,
	);
	await page.getByRole("img", { name: "距離と標高の地質断面図" }).waitFor();
	await page.screenshot({ path: "artifacts/unified-surface-and-diagram.png" });
	await rocks.click();
	await page.waitForFunction(
		(n) => window.__awaji.bodyCount === n - 1,
		initial.bodyCount,
	);
	assert.deepEqual(
		await page.evaluate(() => window.__awaji.unitOpacity),
		individual,
	);
	await page
		.getByRole("button", { name: `${unit.name}を表示`, exact: true })
		.click();
	await page.getByRole("textbox", { name: "凡例を検索", exact: true }).fill("");
	await page.getByRole("button", { name: "鉛直切断", exact: true }).click();
	await page.waitForFunction(() => window.__awaji.volumeCut);
	const slider = page.getByRole("slider", {
		name: "水平の切断位置",
		exact: true,
	});
	await slider.press("End");
	for (let i = 0; i < 12; i++) await slider.press("ArrowLeft");
	const cut = model.nz - 12;
	await page.waitForFunction((k) => window.__awaji.cuts[2] === k, cut);
	const combined = await page.evaluate(() => window.__awaji);
	assert.equal(combined.clippingPlane.length, 2);
	await diagram.click();
	await page.waitForFunction(() => !window.__awaji.showDiagram);
	assert.deepEqual(
		(await page.evaluate(() => window.__awaji)).cuts,
		combined.cuts,
	);
	assert.equal((await page.evaluate(() => window.__awaji)).surfaceOpacity, 100);
	assert.equal((await page.evaluate(() => window.__awaji)).volumeCut, true);
	await page.screenshot({ path: "artifacts/unified-combined-cut-below.png" });
	async function exported(name) {
		const dl = page.waitForEvent("download");
		await page.getByRole("button", { name: "GLB", exact: true }).click();
		const file = `artifacts/${name}.glb`;
		await (await dl).saveAs(file);
		const bytes = await readFile(file);
		return JSON.parse(
			bytes.subarray(20, 20 + bytes.readUInt32LE(12)).toString(),
		);
	}
	const elevation =
		(model.zmin + ((cut - 0.5) * (model.zmax - model.zmin)) / model.nz) / 1000;
	let glb = await exported("unified-below");
	assert.ok(glb.meshes.length > 0);
	for (const mesh of glb.meshes)
		for (const p of mesh.primitives)
			assert.ok(
				glb.accessors[p.attributes.POSITION].max[1] <= elevation + 0.0003,
				"below-side GLB clipping",
			);
	await page.getByText("上側", { exact: true }).click();
	await page.waitForFunction(() => window.__awaji.horizontalReversed);
	assert.equal(
		(await page.evaluate(() => window.__awaji)).clippingPlane[1][1],
		1,
	);
	await page.screenshot({ path: "artifacts/unified-combined-cut-above.png" });
	glb = await exported("unified-above");
	assert.ok(glb.meshes.length > 0);
	for (const mesh of glb.meshes)
		for (const p of mesh.primitives)
			assert.ok(
				glb.accessors[p.attributes.POSITION].min[1] >= elevation - 0.0003,
				"above-side GLB clipping",
			);
	await diagram.click();
	await page.waitForFunction(() => window.__awaji.showDiagram);
	await page.getByRole("combobox", { name: "比較断面", exact: true }).click();
	await page
		.getByRole("option", { name: "明石（1990）C–D–E", exact: true })
		.click();
	await page.waitForFunction(
		() => window.__awaji.referenceSection === "akashi-cde",
	);
	await page.screenshot({ path: "artifacts/unified-reference-and-bodies.png" });
	await page
		.getByRole("button", { name: "切断をリセット", exact: true })
		.click();
	await page.waitForFunction(() => window.__awaji.clippingPlane.length === 0);
	assert.equal(
		(await page.evaluate(() => window.__awaji)).referenceSection,
		"akashi-cde",
	);
	assert.equal((await page.evaluate(() => window.__awaji)).showDiagram, true);
	await page.setViewportSize({ width: 390, height: 844 });
	await page
		.getByRole("button", { name: "操作パネルを閉じる", exact: true })
		.click();
	await page.screenshot({ path: "artifacts/unified-mobile.png" });
	assert.deepEqual(errors, []);
	await writeFile(
		"artifacts/unified-view-check.json",
		JSON.stringify(
			{
				errors,
				verified: [
					"independent diagram, surface and bodies",
					"surface opacity endpoints",
					"global rock toggle preserves individual state",
					"simultaneous cuts and upper/lower GLB bounds",
					"reference comparison and cut-only reset",
					"mobile",
				],
			},
			null,
			2,
		),
	);
	console.log(
		"Unified view visibility, transparency, diagram independence, both horizontal clipping sides and GLB bounds passed.",
	);
} finally {
	await browser.close();
}
