import { openPanelSections } from "./browser-panels.mjs";
import { chromium } from "@playwright/test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
const b = await chromium.launch({
	channel: "chrome",
	headless: true,
	args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
});
try {
	const p = await b.newPage({ viewport: { width: 1440, height: 900 } }),
		errors = [];
	p.on("pageerror", (e) => errors.push(e.message));
	p.on("console", (m) => {
		if (m.type() === "error") errors.push(m.text());
	});
	await p.goto("http://127.0.0.1:4173");
	await p.waitForFunction(() => window.__awaji?.ready);
	await openPanelSections(p);
	// 操作の検証は重ね合わせ図を非表示にして始める。初期表示は別に検証する。
	for (const [field, label] of [
		["surfaceEnabled", "地表地質図"],
		["faultPlanes", "地下の推定面"],
	]) {
		if (await p.evaluate((f) => window.__awaji[f], field))
			await p.getByRole("button", { name: label, exact: true }).click();
		await p.waitForFunction((f) => !window.__awaji[f], field);
	}

	for (const name of ["入力点", "海域基盤面", "シナリオ差"])
		assert.equal(await p.getByRole("button", { name, exact: true }).count(), 0);
	const map = p.getByRole("button", { name: "都市圏活断層図", exact: true }),
		alpha = p.getByRole("slider", {
			name: "都市圏活断層図の不透明度",
			exact: true,
		});
	await map.click();
	await p.waitForFunction(() => window.__awaji.activeMapVisible);
	await alpha.press("Home");
	await p.waitForFunction(
		() =>
			window.__awaji.activeMapOpacity === 0 && !window.__awaji.activeMapVisible,
	);
	assert.equal((await p.evaluate(() => window.__awaji)).observed, false);
	await alpha.press("End");
	await p.waitForFunction(
		() =>
			window.__awaji.activeMapMaterialOpacity === 1 &&
			window.__awaji.activeMapVisible,
	);
	await alpha.press("Home");
	for (let i = 0; i < 50; i++) await alpha.press("ArrowRight");
	await p.waitForFunction(
		() =>
			window.__awaji.activeMapOpacity === 50 &&
			window.__awaji.activeMapMaterialOpacity === 0.5,
	);
	await p.getByRole("button", { name: "地表地質図", exact: true }).click();
	await p.waitForFunction(() => window.__awaji.surfaceVisible);
	assert.equal((await p.evaluate(() => window.__awaji)).surfaceOpacity, 65);
	await p.screenshot({ path: "artifacts/map-layers-opacity.png" });
	await map.click();
	await p.waitForFunction(() => !window.__awaji.activeMapVisible);
	await map.click();
	await p.waitForFunction(() => window.__awaji.activeMapVisible);
	assert.equal((await p.evaluate(() => window.__awaji)).activeMapOpacity, 50);
	const download = p.waitForEvent("download");
	await p.getByRole("button", { name: "GLB", exact: true }).click();
	await (await download).saveAs("artifacts/map-layers-opacity.glb");
	const bytes = await readFile("artifacts/map-layers-opacity.glb"),
		glb = JSON.parse(
			bytes.subarray(20, 20 + bytes.readUInt32LE(12)).toString(),
		);
	assert.ok(
		glb.materials.filter(
			(m) =>
				m.pbrMetallicRoughness?.baseColorTexture &&
				Math.abs(m.pbrMetallicRoughness.baseColorFactor[3] - 0.5) < 1e-6,
		).length >= 2,
		"Both GSI map parts export at 50 percent opacity",
	);

	await p.getByRole("button", { name: "出典・推定条件", exact: true }).click();
	const dialog = p.getByRole("dialog");
	await dialog.getByText("検証用表示", { exact: true }).waitFor();
	for (const [name, field] of [
		["入力点", "pointsVisible"],
		["海域基盤面", "marineSurface"],
		["シナリオ差", "differenceVisible"],
	]) {
		await dialog.getByRole("button", { name, exact: true }).click();
		await p.waitForFunction((f) => window.__awaji[f] === true, field);
		await dialog.getByRole("button", { name, exact: true }).click();
		await p.waitForFunction((f) => window.__awaji[f] === false, field);
	}
	await p.getByRole("button", { name: "出典を閉じる", exact: true }).click();
	assert.deepEqual(errors, []);
	console.log(
		"Main layers, independent GSI opacity endpoints and midpoint, retained opacity, and relocated diagnostics passed.",
	);
} finally {
	await b.close();
}
