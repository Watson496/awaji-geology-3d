import { openPanelSections } from "./browser-panels.mjs";
import { chromium } from "@playwright/test";
import assert from "node:assert/strict";
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
	await page.goto("http://127.0.0.1:4173");
	await page.waitForFunction(() => window.__awaji?.ready);
	await openPanelSections(page);
	await page.getByRole("button", { name: "鉛直切断", exact: true }).click();
	await page.waitForFunction(
		() => window.__awaji.volumeCut && window.__awaji.clippingPlane.length === 1,
	);
	assert.equal(
		await page
			.getByRole("slider", { name: "東西の切断位置", exact: true })
			.count(),
		0,
	);
	assert.equal(
		await page
			.getByRole("slider", { name: "南北の切断位置", exact: true })
			.count(),
		0,
	);
	const before = await page.evaluate(() => window.__awaji.clippingPlane[0]);
	assert.ok(Math.abs(before[0]) > 0 && Math.abs(before[2]) > 0);
	await page.getByLabel("平面図で切断位置を変更").scrollIntoViewIfNeeded();
	const plan = await page.getByLabel("平面図で切断位置を変更").boundingBox();
	await page.mouse.move(plan.x + plan.width * 0.4, plan.y + plan.height * 0.4);
	await page.mouse.down();
	await page.mouse.move(
		plan.x + plan.width * 0.65,
		plan.y + plan.height * 0.6,
		{ steps: 3 },
	);
	await page.mouse.up();
	await page.waitForFunction(
		(v) => JSON.stringify(window.__awaji.clippingPlane[0]) !== v,
		JSON.stringify(before),
	);
	await page.waitForTimeout(500);
	const first = await page.evaluate(() => window.__awaji.clippingPlane[0]);
	await page.getByRole("button", { name: "鉛直切断の側を反転" }).click();
	await page.waitForFunction(() => window.__awaji.cutReversed);
	await page.waitForTimeout(500);
	const second = await page.evaluate(() => window.__awaji.clippingPlane[0]);
	first.forEach((x, i) => assert.ok(Math.abs(x + second[i]) < 1e-8));
	await page.screenshot({ path: "artifacts/volume-arbitrary-cut.png" });
	await page
		.getByRole("button", { name: "切断をリセット", exact: true })
		.click();
	await page.waitForFunction(
		() =>
			!window.__awaji.volumeCut && window.__awaji.clippingPlane.length === 0,
	);
	await page
		.getByRole("slider", { name: "水平の切断位置", exact: true })
		.press("ArrowLeft");
	await page.getByRole("button", { name: "鉛直切断", exact: true }).click();
	await page.waitForFunction(() => window.__awaji.clippingPlane.length === 2);
	await page.getByLabel("平面図で切断位置を変更").scrollIntoViewIfNeeded();
	const coords = await page
		.getByLabel("平面図で切断位置を変更")
		.evaluate((el) =>
			window.__awaji.sectionRoute.map(([x, y]) => {
				const q = new DOMPoint(
					x,
					el.viewBox.baseVal.height - 18 - y,
				).matrixTransform(el.getScreenCTM());
				return [q.x, q.y];
			}),
		);
	await page.mouse.move(...coords[1]);
	await page.mouse.down();
	await page.mouse.move(...coords[0]);
	await page.mouse.up();
	await page.waitForFunction(() => window.__awaji.clippingPlane.length === 1);
	assert.equal(
		await page.evaluate(() => window.__awaji.clippingPlane[0][1]),
		-1,
	);

	assert.deepEqual(errors, []);
	console.log(
		"Volume arbitrary cut: oblique plane, dragging, side reversal, reset and console passed.",
	);
} finally {
	await browser.close();
}
