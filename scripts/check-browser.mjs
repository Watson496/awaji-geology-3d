import { openPanelSections } from "./browser-panels.mjs";
import { chromium } from "@playwright/test";
import { mkdir, writeFile, readFile } from "node:fs/promises";
import assert from "node:assert/strict";
const browser = await chromium.launch({
	channel: "chrome",
	headless: true,
	args: [
		"--enable-webgl",
		"--use-gl=angle",
		"--use-angle=swiftshader",
		"--enable-unsafe-swiftshader",
	],
});
const page = await browser.newPage({
	viewport: { width: 1440, height: 1000 },
	deviceScaleFactor: 1,
});
const errors = [];
page.on("pageerror", (e) => errors.push(e.stack || e.message));
page.on("console", (m) => {
	if (m.type() === "error") errors.push(m.text());
});
page.on("response", (r) => {
	if (r.status() >= 400) errors.push(`${r.status()} ${r.url()}`);
});
async function settle() {
	await page.mouse.move(600, 150);
	await page.evaluate(
		() =>
			new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))),
	);
}
async function setDiagram(value) {
	if ((await page.evaluate(() => window.__awaji.showDiagram)) !== value)
		await page.getByRole("button", { name: "断面図", exact: true }).click();
	await page.waitForFunction((v) => window.__awaji.showDiagram === v, value);
	await settle();
}
async function diagnostic(name) {
	await page
		.getByRole("button", { name: "出典・推定条件", exact: true })
		.click();
	await page
		.getByRole("dialog")
		.getByRole("button", { name, exact: true })
		.click();
	await page.getByRole("button", { name: "出典を閉じる", exact: true }).click();
}
async function shot(name) {
	await settle();
	await page.screenshot({ path: `artifacts/${name}.png` });
}
await mkdir("artifacts", { recursive: true });
await page.goto("http://127.0.0.1:4173");
await page.waitForFunction(() => window.__awaji?.ready);
await openPanelSections(page);
const defaultLayers = await page.evaluate(() => window.__awaji);
assert.equal(defaultLayers.surfaceEnabled, true);
assert.equal(defaultLayers.surfaceVisible, true);
assert.equal(defaultLayers.faultPlanes, true);
assert.ok(defaultLayers.faultCount > 0 && defaultLayers.faultPlaneCount > 0);
// The interaction fixture below starts without overlays; initial defaults are verified separately.
for (const [field, label] of [
	["surfaceEnabled", "地表地質図"],
	["faultPlanes", "地下の推定面"],
]) {
	if (await page.evaluate((f) => window.__awaji[f], field))
		await page.getByRole("button", { name: label, exact: true }).click();
	await page.waitForFunction((f) => !window.__awaji[f], field);
}

const results = { initial: await page.evaluate(() => window.__awaji) };
assert.equal(results.initial.mode, "unified");
assert.ok(results.initial.bodyCount > 5);
assert.equal(results.initial.sectionCount, 0);
const model = JSON.parse(await readFile("web/data/model.json", "utf8"));
assert.deepEqual(results.initial.cuts, [...model.shape, model.nz]);
const chosen = model.units.find((u) => u.key === "K21_pim_a");
await page
	.getByRole("textbox", { name: "凡例を検索", exact: true })
	.fill(chosen.key);
await page
	.getByRole("textbox", {
		name: `${chosen.name}の不透明度（数値）`,
		exact: true,
	})
	.fill("20");
await page.keyboard.press("Tab");
await page.waitForFunction(
	(i) => Math.abs(window.__awaji.unitOpacity[i] - 0.2) < 1e-6,
	chosen.id - 1,
);
const after = await page.evaluate(() => window.__awaji);
for (let i = 0; i < after.unitOpacity.length; i++)
	if (i !== chosen.id - 1)
		assert.equal(after.unitOpacity[i], results.initial.unitOpacity[i]);
results.individualTransparency = after;
await shot("awaji-individual-transparency");
await page
	.getByRole("textbox", {
		name: `${chosen.name}の不透明度（数値）`,
		exact: true,
	})
	.fill("100");
await page.keyboard.press("Tab");
await page.waitForFunction(
	(i) => window.__awaji.unitOpacity[i] === 1,
	chosen.id - 1,
);
await page.getByRole("textbox", { name: "凡例を検索", exact: true }).fill("");
await shot("awaji-overview");
await setDiagram(true);
const freeRoute = await page.evaluate(() => window.__awaji.sectionRoute);
const svg = page.getByLabel("平面図で切断位置を変更");
await svg.scrollIntoViewIfNeeded();
const bounds = await svg.boundingBox();
const px =
		bounds.x + ((freeRoute[0][0] + 9) / (model.shape[0] + 18)) * bounds.width,
	py =
		bounds.y +
		((model.shape[1] - freeRoute[0][1] + 9) / (model.shape[1] + 18)) *
			bounds.height;
await page.mouse.move(px, py);
await page.mouse.down();
await page.mouse.move(px + 12, py - 9, { steps: 3 });
await page.mouse.up();
await page.waitForFunction(
	(r) => JSON.stringify(window.__awaji.sectionRoute) !== JSON.stringify(r),
	freeRoute,
);
await shot("awaji-arbitrary-section");
await page.getByRole("combobox", { name: "比較断面", exact: true }).click();
await page
	.getByRole("option", { name: "明石（1990）A–B", exact: true })
	.click();
await page.waitForFunction(
	() => window.__awaji.referenceSection === "akashi-ab",
);
await shot("awaji-section-overlay");
results.sectionOverlay = await page.evaluate(() => window.__awaji);
await page
	.getByRole("slider", { name: "原断面図の不透明度", exact: true })
	.press("End");
await page.waitForFunction(() => window.__awaji.referenceOpacity === 100);
await page
	.getByRole("slider", { name: "原断面図の不透明度", exact: true })
	.press("Home");
await page.waitForFunction(() => window.__awaji.referenceOpacity === 0);
await setDiagram(false);
await shot("awaji-fence");
await page.getByRole("button", { name: "岩体を一括表示", exact: true }).click();
await page.getByRole("button", { name: "地表地質図", exact: true }).click();
await page
	.getByRole("slider", { name: "地表地質図の不透明度", exact: true })
	.press("End");
await page.waitForFunction(
	() => window.__awaji.bodyCount === 0 && window.__awaji.surfaceOpacity === 100,
);
assert.equal((await page.evaluate(() => window.__awaji)).meshCount, 0);
await shot("awaji-surface");
await page.getByRole("button", { name: "岩体を一括表示", exact: true }).click();
await page.getByRole("button", { name: "地表地質図", exact: true }).click();
await page.waitForFunction(() => window.__awaji.bodyCount > 5);
assert.ok((await page.evaluate(() => window.__awaji)).bodyCount > 5);
await shot("awaji-transparent");
await diagnostic("海域基盤面");
await page.waitForFunction(() => window.__awaji.marineSurface);
await shot("awaji-marine-basement");
await diagnostic("海域基盤面");
await page.getByRole("combobox", { name: "表示する断層", exact: true }).click();
await page.getByRole("option").filter({ hasText: "野島断層" }).first().click();
await page.waitForFunction(() => window.__awaji.faultCount === 1);
await shot("awaji-official-nojima");
await page.getByRole("combobox", { name: "表示する断層", exact: true }).click();
await page.getByRole("option", { name: "すべての断層", exact: true }).click();
await page.waitForFunction(() => window.__awaji.faultCount > 5);

await page
	.getByRole("textbox", { name: "凡例を検索", exact: true })
	.fill(chosen.key);
const beforeHide = (await page.evaluate(() => window.__awaji)).bodyCount;
await page
	.getByRole("button", { name: `${chosen.name}を非表示`, exact: true })
	.click();
await page.waitForFunction(
	(n) => window.__awaji.bodyCount === n - 1,
	beforeHide,
);
await page
	.getByRole("button", { name: `${chosen.name}を表示`, exact: true })
	.click();
await page.waitForFunction((n) => window.__awaji.bodyCount === n, beforeHide);
const xslider = page.getByRole("slider", {
	name: "水平の切断位置",
	exact: true,
});
const targetCut = model.nz - 6;
await xslider.press("End");
for (let i = 0; i < 6; i++) await xslider.press("ArrowLeft");
await page.waitForFunction((v) => window.__awaji?.cuts[2] === v, targetCut);
await page.getByRole("textbox", { name: "凡例を検索", exact: true }).fill("");
await shot("awaji-cutaway");
results.cutaway = await page.evaluate(() => window.__awaji);
const dl = page.waitForEvent("download");
await page.getByRole("button", { name: "GLB", exact: true }).click();
await (await dl).saveAs("artifacts/test-export.glb");
const buffer = await readFile("artifacts/test-export.glb"),
	json = JSON.parse(
		buffer.subarray(20, 20 + buffer.readUInt32LE(12)).toString(),
	);
assert.ok(
	json.materials.some((m) => {
		const c = m.pbrMetallicRoughness?.baseColorFactor;
		return c && c[0] < 0.15 && c[1] < 0.15 && c[2] < 0.15;
	}),
	"unified black fault traces are retained in GLB",
);
const ylimit =
	(model.zmin + ((targetCut - 0.5) * (model.zmax - model.zmin)) / model.nz) /
		1000 +
	0.0002;
for (const m of json.meshes)
	for (const primitive of m.primitives) {
		const a = json.accessors[primitive.attributes.POSITION];
		assert.ok(a.max.every(Number.isFinite));
		assert.ok(a.max[1] <= ylimit, "GLBにも切断位置を反映する");
	}
await setDiagram(true);
const plan = page.getByLabel("平面図で切断位置を変更");
await plan.scrollIntoViewIfNeeded();
const box = await plan.boundingBox();
await page.mouse.move(box.x + box.width * 0.5, box.y + box.height * 0.72);
await page.mouse.down();
await page.mouse.move(box.x + box.width * 0.45, box.y + box.height * 0.55, {
	steps: 5,
});
await page.mouse.up();
await settle();
results.planDrag = await page.evaluate(() => window.__awaji);
await page.getByRole("button", { name: "出典・推定条件", exact: true }).click();
await page.getByRole("dialog").waitFor();
await page.getByRole("button", { name: "出典を閉じる" }).click();
await page.getByRole("button", { name: "出典・推定条件", exact: true }).click();
await page.getByRole("combobox", { name: "検証用モデル", exact: true }).click();
await page.getByRole("option", { name: "比較 B", exact: true }).click();
await page.getByRole("button", { name: "出典を閉じる", exact: true }).click();
await page.waitForFunction(() => window.__awaji?.scenario === "deep");
await diagnostic("シナリオ差");
await shot("awaji-scenario-difference");
results.deep = await page.evaluate(() => window.__awaji);
await page.getByRole("button", { name: "出典・推定条件", exact: true }).click();
await page.getByRole("combobox", { name: "検証用モデル", exact: true }).click();
await page
	.getByRole("option", { name: "採用モデル（通常表示）", exact: true })
	.click();
await page.getByRole("button", { name: "出典を閉じる", exact: true }).click();
await page.waitForFunction(() => window.__awaji?.scenario === "reference");
await diagnostic("シナリオ差");
await setDiagram(false);
await page.getByRole("button", { name: "切断をリセット", exact: true }).click();
await page.waitForFunction(
	() => window.__awaji?.cuts[0] === 200 && window.__awaji?.cuts[1] === 288,
);
if ((await page.evaluate(() => window.__awaji)).observed)
	await page.getByRole("button", { name: "地表地質図", exact: true }).click();
for (const u of model.units) {
	await page
		.getByRole("textbox", { name: "凡例を検索", exact: true })
		.fill(u.key);
	await page
		.getByRole("textbox", { name: `${u.name}の不透明度（数値）`, exact: true })
		.fill("100");
	await page.keyboard.press("Tab");
}
await page.getByRole("textbox", { name: "凡例を検索", exact: true }).fill("");
await page.getByRole("textbox", { name: "鉛直倍率" }).fill("1");
await page.getByRole("textbox", { name: "鉛直倍率" }).press("Tab");
await settle();
const full = page.waitForEvent("download");
await page.getByRole("button", { name: "GLB", exact: true }).click();
await (await full).saveAs("artifacts/awaji-reference.glb");
await setDiagram(true);
await page.getByRole("button", { name: "切断をリセット", exact: true }).click();
await page.getByRole("button", { name: "地表地質図", exact: true }).click();
await page.getByRole("textbox", { name: "鉛直倍率" }).fill("3");
await page.getByRole("textbox", { name: "鉛直倍率" }).press("Tab");
await page.setViewportSize({ width: 390, height: 844 });
await page
	.getByRole("button", { name: "操作パネルを閉じる", exact: true })
	.click();
await shot("awaji-mobile");
results.errors = errors;
await writeFile(
	"artifacts/browser-check.json",
	JSON.stringify(results, null, 2),
);
console.log(JSON.stringify(results, null, 2));
await browser.close();
if (errors.length) process.exitCode = 1;
