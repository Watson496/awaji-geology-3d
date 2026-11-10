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
		errors = [],
		results = [];
	page.on("pageerror", (e) => errors.push(e.stack));
	await page.goto("http://127.0.0.1:4173");
	await page.waitForFunction(() => window.__awaji?.ready);
	await openPanelSections(page);
	await page.getByRole("button", { name: "断面図", exact: true }).click();
	const sections = JSON.parse(
		await readFile("web/data/sections.json", "utf8"),
	).sections;
	for (const section of sections) {
		await page.getByRole("combobox", { name: "比較断面", exact: true }).click();
		await page.getByRole("option", { name: section.name, exact: true }).click();
		await page.waitForFunction(
			(id) => window.__awaji.referenceSection === id,
			section.id,
		);
		const check = await page.locator(".section-diagram").evaluate((div) => {
			const image = div.querySelector("image");
			const axis = [...div.querySelectorAll("g")].find(
				(g) => g.querySelector("text")?.textContent === "0",
			);
			return {
				height: Number(image.getAttribute("height")),
				y: Number(image.getAttribute("y")),
				zeroY: Number(axis.querySelector("text").getAttribute("y")) - 4,
				meshes: div.querySelectorAll("path").length,
			};
		});
		assert.ok(check.height > 0 && check.height <= 185.001);
		assert.ok(
			Math.abs(check.y + check.height / 2 - check.zeroY) < 0.01,
			"source sea level must coincide with model 0m axis",
		);
		assert.ok(check.meshes > 5);
		results.push({ id: section.id, ...check });
		if (section.id === "akashi-ab")
			await page.screenshot({
				path: "artifacts/official-section-comparison.png",
			});
		if (section.id === "sumoto-fgh")
			await page.screenshot({ path: "artifacts/official-folded-section.png" });
	}
	assert.deepEqual(errors, []);
	await writeFile(
		"artifacts/official-sections-browser.json",
		JSON.stringify({ results, errors }, null, 2),
	);
	console.log(
		"All six source sections align at sea level and fit their calibrated elevation axes.",
	);
} finally {
	await browser.close();
}
