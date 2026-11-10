import { openPanelSections } from "./browser-panels.mjs";
import { chromium } from "@playwright/test";
import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";
import { bodyAgeRank, groupColors } from "../web/src/rock-body-legend.js";

const catalog = JSON.parse(await readFile("web/data/rock-bodies.json", "utf8"));
const nojima = catalog.bodies.find((b) => b.identity === "nojima-gd");
const sumoto = catalog.bodies.find((b) => b.identity === "sumoto-gd");
assert.equal(nojima.source_unit, sumoto.source_unit);
assert.equal(nojima.color, sumoto.color);
assert.notEqual(nojima.id, sumoto.id);
const browser = await chromium.launch({
	channel: "chrome",
	headless: true,
	args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
});
try {
	const page = await browser.newPage({
		viewport: { width: 1440, height: 900 },
	});
	const errors = [];
	page.on("pageerror", (e) => errors.push(e.message));
	page.on("console", (m) => {
		if (m.type() === "error") errors.push(m.text());
	});
	await page.goto("http://127.0.0.1:4173");
	await page.waitForFunction(() => window.__awaji?.ready);
	await openPanelSections(page);
	assert.equal(await page.locator(".unit-card").count(), 0);
	const headings = await page.locator(".rock-group-name").evaluateAll((nodes) =>
		nodes.map((n) => ({
			name: n.querySelector("span:nth-child(2)").textContent,
			colors: [...n.querySelectorAll(".rock-group-swatch")].map(
				(s) => s.style.background,
			),
		})),
	);
	const rank = (name) =>
		Math.min(
			...catalog.bodies
				.filter((b) => b.group === name)
				.map((b) => bodyAgeRank(b.source_symbol ?? "")),
		);
	assert.deepEqual(
		headings.map((g) => rank(g.name)),
		headings.map((g) => rank(g.name)).sort((a, b) => a - b),
	);
	assert.equal(headings[0].name, "沖積層・人工地盤");
	assert.equal(headings.at(-1).name, "未拘束");
	for (const heading of headings) {
		const members = catalog.bodies.filter(
			(b) =>
				b.group === heading.name &&
				Object.values(b.cell_counts).some((n) => n > 0),
		);
		assert.equal(
			heading.colors.length,
			Math.min(4, groupColors(members, "reference").length),
		);
	}
	await page.screenshot({ path: "artifacts/rock-groups-collapsed.png" });
	await page
		.getByRole("button", { name: "深成岩類を展開", exact: true })
		.click();
	const no = page.getByRole("textbox", {
		name: `${nojima.name}の不透明度（数値）`,
		exact: true,
	});
	await no.fill("25");
	await no.press("Tab");
	await page.waitForFunction(
		(id) => window.__awaji.opacity[id - 1] === 25,
		nojima.id,
	);
	assert.equal(
		await page.evaluate((id) => window.__awaji.opacity[id - 1], sumoto.id),
		90,
	);
	await page
		.getByRole("button", { name: `${sumoto.name}を非表示`, exact: true })
		.click();
	assert.equal(await no.isEnabled(), true);
	await page
		.getByRole("button", { name: `${sumoto.name}を表示`, exact: true })
		.click();
	const groupSlider = page.getByRole("slider", {
		name: "深成岩類全体の不透明度",
		exact: true,
	});
	await groupSlider.focus();
	await groupSlider.press("Home");
	await page.waitForFunction(
		(ids) => ids.every((id) => window.__awaji.opacity[id - 1] === 0),
		catalog.bodies
			.filter(
				(b) =>
					b.group === "深成岩類" &&
					Object.values(b.cell_counts).some((n) => n > 0),
			)
			.map((b) => b.id),
	);
	await no.fill("100");
	await no.press("Tab");
	await page.waitForFunction(
		(id) => window.__awaji.unitOpacity[id - 1] === 1,
		nojima.id,
	);
	assert.equal(
		await page.evaluate((id) => window.__awaji.opacity[id - 1], sumoto.id),
		0,
	);
	await page
		.getByRole("textbox", { name: "凡例を検索", exact: true })
		.fill("大阪層群");
	assert.ok((await page.locator(".unit-card").count()) >= 3);
	assert.equal(await page.locator(".rock-group").count(), 1);
	await page
		.getByRole("textbox", { name: "凡例を検索", exact: true })
		.fill("K21_pim_a");
	assert.ok((await page.locator(".unit-card").count()) >= 3);
	await page.getByRole("textbox", { name: "凡例を検索", exact: true }).fill("");
	await page.screenshot({ path: "artifacts/rock-groups-desktop.png" });
	await page.getByRole("button", { name: "鉛直切断", exact: true }).click();
	await page.waitForFunction(
		() => window.__awaji.volumeCut && window.__awaji.sectionCount > 0,
	);
	await page.getByRole("button", { name: "断面図", exact: true }).click();
	await page.waitForFunction(() => window.__awaji.showDiagram);
	await page.setViewportSize({ width: 390, height: 844 });
	await page
		.getByRole("button", { name: "岩体の操作", exact: true })
		.scrollIntoViewIfNeeded();
	assert.equal(
		await page.evaluate(
			() => document.documentElement.scrollHeight > innerHeight,
		),
		false,
	);
	await page.screenshot({ path: "artifacts/rock-groups-mobile.png" });
	assert.deepEqual(errors, []);
	await writeFile(
		"artifacts/rock-groups-check.json",
		JSON.stringify(
			{ distinct_bodies_same_native_class: [nojima.id, sumoto.id], errors },
			null,
			2,
		),
	);
	console.log(
		"Rock groups: independent same-legend bodies, group opacity, search, cuts and mobile passed.",
	);
} finally {
	await browser.close();
}
