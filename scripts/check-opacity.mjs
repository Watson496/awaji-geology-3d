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
	const p = await b.newPage({ viewport: { width: 1440, height: 1000 } }),
		errors = [];
	p.on("pageerror", (e) => errors.push(e.message));
	p.on("console", (m) => {
		if (m.type() === "error") errors.push(m.text());
	});
	const model = JSON.parse(await readFile("web/data/model.json", "utf8")),
		u = model.units.find((u) => u.key === "K21_pim_a");
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

	const initial = await p.evaluate(() => window.__awaji);
	assert.equal(initial.opacity[u.id - 1], 90);
	assert.equal(initial.unitOpacity[u.id - 1], 0.9);
	await p.getByRole("textbox", { name: "凡例を検索", exact: true }).fill(u.key);
	const number = p.getByRole("textbox", {
		name: `${u.name}の不透明度（数値）`,
		exact: true,
	});
	await number.fill("0");
	await number.press("Tab");
	await p.waitForFunction(
		(id) => window.__awaji.unitOpacity[id - 1] === 0,
		u.id,
	);
	assert.equal(
		(await p.evaluate(() => window.__awaji)).bodyCount,
		initial.bodyCount - 1,
	);
	await number.fill("100");
	await number.press("Tab");
	await p.waitForFunction(
		(id) => window.__awaji.unitOpacity[id - 1] === 1,
		u.id,
	);
	assert.equal(
		(await p.evaluate(() => window.__awaji)).bodyCount,
		initial.bodyCount,
	);
	const slider = p.getByRole("slider", {
		name: `${u.name}の不透明度`,
		exact: true,
	});
	await slider.press("Home");
	await p.waitForFunction(
		(id) => window.__awaji.unitOpacity[id - 1] === 0,
		u.id,
	);
	await slider.press("End");
	await p.waitForFunction(
		(id) => window.__awaji.unitOpacity[id - 1] === 1,
		u.id,
	);
	await p.getByRole("textbox", { name: "凡例を検索", exact: true }).fill("");
	await p.getByRole("button", { name: "地表地質図", exact: true }).click();
	const surface = p.getByRole("slider", {
		name: "地表地質図の不透明度",
		exact: true,
	});
	await surface.press("Home");
	await p.waitForFunction(
		() => window.__awaji.surfaceOpacity === 0 && !window.__awaji.surfaceVisible,
	);
	await surface.press("End");
	await p.waitForFunction(
		() =>
			window.__awaji.surfaceOpacity === 100 && window.__awaji.surfaceVisible,
	);
	const bulk = p.getByRole("slider", {
		name: "岩体全体の不透明度",
		exact: true,
	});
	await bulk.press("Home");
	await p.waitForFunction(
		() =>
			window.__awaji.opacity.every((a) => a === 0) &&
			window.__awaji.bodyCount === 0,
	);
	await bulk.press("End");
	await p.waitForFunction(() =>
		window.__awaji.unitOpacity.every((a) => a === 1),
	);
	await bulk.press("Home");
	for (let i = 0; i < 15; i++) await bulk.press("ArrowRight");
	await p.waitForFunction(
		() =>
			window.__awaji.opacity.every((a) => a === 15) &&
			window.__awaji.unitOpacity.every((a) => a === 0.15),
	);
	await p.waitForFunction(
		(id) =>
			window.__awaji.opacity[id - 1] === 15 &&
			window.__awaji.unitOpacity[id - 1] === 0.15,
		u.id,
	);
	await p.getByRole("textbox", { name: "凡例を検索", exact: true }).fill(u.key);
	await p.waitForFunction(
		(el) => parseFloat(el.value) === 15,
		await number.elementHandle(),
	);
	await number.fill("100");
	await number.press("Tab");
	await p.waitForFunction(
		(id) => window.__awaji.unitOpacity[id - 1] === 1,
		u.id,
	);
	assert.equal(
		await p.getByLabel("岩体全体の不透明度の値", { exact: true }).innerText(),
		"個別",
	);
	await p.getByRole("textbox", { name: "凡例を検索", exact: true }).fill("");

	await p.getByRole("button", { name: "断面図", exact: true }).click();
	await p.getByRole("img", { name: "距離と標高の地質断面図" }).waitFor();
	await p.screenshot({ path: "artifacts/opacity-controls.png" });
	assert.deepEqual(errors, []);
	console.log(
		"Rock numeric input and slider: 0 hidden / 100 opaque; surface: 0 hidden / 100 opaque; section diagram passed.",
	);
} finally {
	await b.close();
}
