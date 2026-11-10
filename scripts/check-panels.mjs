import { chromium } from "@playwright/test";
import assert from "node:assert/strict";
import { writeFile } from "node:fs/promises";
import { openPanelSections } from "./browser-panels.mjs";
const browser = await chromium.launch({
	channel: "chrome",
	headless: true,
	args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
});
try {
	const page = await browser.newPage({
			viewport: { width: 1440, height: 900 },
		}),
		errors = [],
		results = [];
	page.on("pageerror", (e) => errors.push(e.message));
	page.on("console", (m) => {
		if (m.type() === "error") errors.push(m.text());
	});
	await page.goto("http://127.0.0.1:4173");
	await page.waitForFunction(() => window.__awaji?.ready);
	const sections = ["岩体の操作", "レイヤーの操作", "切断・断面図の操作"];
	assert.deepEqual(
		await page
			.locator(".inspector-accordion .mantine-Accordion-control")
			.evaluateAll((els) => els.map((e) => e.getAttribute("aria-label"))),
		sections,
	);
	assert.equal(
		await page
			.getByRole("button", { name: sections[2], exact: true })
			.getAttribute("aria-expanded"),
		"false",
	);
	await page.screenshot({ path: "artifacts/accordion-default.png" });
	await openPanelSections(page);
	await page.getByRole("button", { name: "鉛直切断", exact: true }).click();
	await page.getByRole("button", { name: "断面図", exact: true }).click();
	await page.getByRole("combobox", { name: "比較断面", exact: true }).click();
	await page
		.getByRole("option", { name: "明石（1990）C–D–E", exact: true })
		.click();
	await page.waitForFunction(
		() => window.__awaji.referenceSection === "akashi-cde",
	);
	const before = await page.evaluate(() => ({
		cut: window.__awaji.volumeCut,
		diagram: window.__awaji.showDiagram,
		route: window.__awaji.sectionRoute,
		opacity: window.__awaji.opacity,
	}));
	for (const name of sections)
		await page.getByRole("button", { name, exact: true }).click();
	assert.deepEqual(
		await page.evaluate(() => ({
			cut: window.__awaji.volumeCut,
			diagram: window.__awaji.showDiagram,
			route: window.__awaji.sectionRoute,
			opacity: window.__awaji.opacity,
		})),
		before,
	);
	await openPanelSections(page);
	await page
		.getByRole("button", { name: "深成岩類を展開", exact: true })
		.click();
	for (const [width, height] of [
		[1440, 900],
		[1366, 768],
		[1280, 720],
		[1920, 1080],
		[900, 600],
		[390, 844],
	]) {
		await page.setViewportSize({ width, height });
		await page
			.getByRole("button", { name: "鉛直切断", exact: true })
			.scrollIntoViewIfNeeded();
		const info = await page.evaluate(() => {
			const w = document.querySelector(".workspace").getBoundingClientRect(),
				shell = document.querySelector(".inspector-shell"),
				dock = document.querySelector(".inspector").getBoundingClientRect(),
				scroll = document.querySelector(".inspector-scroll"),
				list = document.querySelector(".unit-list");
			return {
				width: innerWidth,
				height: innerHeight,
				bodyOverflow: document.documentElement.scrollHeight > innerHeight,
				shellOverflow: shell.scrollHeight - shell.clientHeight,
				dockWidth: dock.width,
				dockBottom: dock.bottom,
				workspaceBottom: w.bottom,
				scrollable: scroll.scrollHeight > scroll.clientHeight,
				listOverflow: getComputedStyle(list).overflowY,
				rowHeight: document.querySelector(".unit-card").getBoundingClientRect()
					.height,
				sceneWidth: document.querySelector(".scene").getBoundingClientRect()
					.width,
			};
		});
		assert.equal(info.bodyOverflow, false);
		assert.ok(info.shellOverflow <= 1, JSON.stringify(info));
		assert.ok(info.dockWidth <= 380, JSON.stringify(info));
		assert.ok(info.dockBottom <= info.workspaceBottom, JSON.stringify(info));
		assert.equal(info.listOverflow, "visible");
		assert.ok(info.rowHeight <= (width <= 700 ? 32 : 30));
		assert.ok(info.sceneWidth > 0);
		await page.screenshot({
			path: `artifacts/accordion-${width}x${height}.png`,
		});
		await page
			.getByRole("button", { name: "岩体の操作", exact: true })
			.scrollIntoViewIfNeeded();
		await page.screenshot({
			path: `artifacts/accordion-rocks-${width}x${height}.png`,
		});
		results.push(info);
	}
	await page
		.getByRole("button", { name: "操作パネルを閉じる", exact: true })
		.click();
	assert.equal(await page.locator(".inspector").isVisible(), false);
	await page
		.getByRole("button", { name: "操作パネルを開く", exact: true })
		.click();
	assert.equal(
		await page
			.getByRole("button", { name: "切断・断面図の操作", exact: true })
			.getAttribute("aria-expanded"),
		"true",
	);
	assert.deepEqual(errors, []);
	await writeFile(
		"artifacts/panels-check.json",
		JSON.stringify({ results, errors }, null, 2),
	);
	console.log(
		"Vertical accordion: independent sections, retained model state, one scrolling area and six viewport sizes passed.",
	);
} finally {
	await browser.close();
}
