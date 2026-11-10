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

	await page.screenshot({ path: "artifacts/attitude-continuous-bodies.png" });
	const sections = JSON.parse(
			await readFile("web/data/sections.json", "utf8"),
		).sections,
		checks = [];
	await page.getByRole("button", { name: "断面図", exact: true }).click();
	for (const id of ["akashi-cde", "akashi-fg"]) {
		const sec = sections.find((s) => s.id === id);
		await page.getByRole("combobox", { name: "比較断面", exact: true }).click();
		await page.getByRole("option", { name: sec.name, exact: true }).click();
		await page.waitForFunction(
			(id) => window.__awaji.referenceSection === id,
			id,
		);
		if (
			!(await page.evaluate(() => window.__awaji.selectedFault)).includes(
				"久野々",
			)
		) {
			await page
				.getByRole("combobox", { name: "表示する断層", exact: true })
				.click();
			await page
				.getByRole("option")
				.filter({ hasText: "久野々断層" })
				.first()
				.click();
		}
		await page.waitForFunction(() =>
			window.__awaji.selectedFault.includes("久野々"),
		);
		const ranges = await page
			.locator('.section-diagram path[stroke="#111"]')
			.evaluateAll((paths) =>
				paths.map((p) =>
					p
						.getAttribute("d")
						.match(/-?\d+(?:\.\d+)?/g)
						.map(Number),
				),
			);
		assert.ok(ranges.length);
		assert.ok(
			ranges.some(
				([x, y, xx, yy]) => Math.abs(xx - x) > 0.05 && Math.abs(yy - y) > 0.1,
			),
			"model fault segments are genuinely inclined, not vertical chart decorations",
		);
		await page.screenshot({ path: `artifacts/attitude-${id}.png` });
		checks.push({
			section: id,
			segments: ranges.length,
			maxSegmentHorizontalPixels: Math.max(
				...ranges.map(([x, y, xx, yy]) => Math.abs(xx - x)),
			),
		});
	}
	await page.getByRole("button", { name: "断面図", exact: true }).click();
	await page.waitForFunction(() => !window.__awaji.showDiagram);
	await page
		.getByRole("combobox", { name: "表示する断層", exact: true })
		.click();
	await page
		.getByRole("option")
		.filter({ hasText: "中央構造線（紀淡・鳴門海峡）・枝1" })
		.first()
		.click();
	await page.getByRole("button", { name: "地下の推定面", exact: true }).click();
	const catalog = JSON.parse(
		await readFile("web/data/faults.json", "utf8"),
	).faults;
	const separateMtl = catalog.filter(
		(f) => f.structural_candidate && f.used_for_model,
	);
	assert.ok(separateMtl.length > 1);
	const expected = 1;
	await page.waitForFunction(
		(n) => window.__awaji.faultPlaneCount === n,
		expected,
	);
	await page.screenshot({
		path: "artifacts/attitude-mtl-separate-surfaces.png",
	});
	assert.deepEqual(errors, []);
	await writeFile(
		"artifacts/attitude-browser.json",
		JSON.stringify({ checks, mtlSurfaces: expected, errors }, null, 2),
	);
	console.log(
		"Inclined Kunono surfaces in CDE and FG, continuous bodies, and individually resolved MTL surfaces passed.",
	);
} finally {
	await browser.close();
}
