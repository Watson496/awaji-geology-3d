import test from "node:test";
import assert from "node:assert/strict";
import { sampleUnit, faultSectionSegments } from "../web/src/section-view.js";
test("カテゴリの補間で中間の地質単元IDを作らない", () => {
	const meta = {
		shape: [2, 1],
		nz: 1,
		extent_xy: [0, 2, 0, 1],
		zmin: 0,
		zmax: 1,
	};
	for (let x = 0.1; x < 1.9; x += 0.1)
		assert.ok(
			[1, 22].includes(sampleUnit(new Uint8Array([1, 22]), meta, x, 0.5, 0.5)),
		);
	assert.equal(sampleUnit(new Uint8Array([1, 22]), meta, -2, 0.5, 0.5), 0);
});
test("断層の交線は任意の鉛直断面と有限の範囲に従う", () => {
	const tri = [
		[
			[5, 0, -10],
			[5, 10, -10],
			[5, 0, 10],
		],
	];
	const segments = faultSectionSegments(
		tri,
		[
			[0, 0],
			[10, 5],
		],
		-8,
		-2,
	);
	assert.equal(segments.length, 1);
	for (const p of segments[0]) {
		assert.ok(Math.abs(p[0] - 5) < 1e-8);
		assert.ok(Math.abs(p[1] - 2.5) < 1e-8);
		assert.ok(p[2] >= -8 && p[2] <= -2);
	}
	assert.deepEqual(
		faultSectionSegments(
			tri,
			[
				[0, 0],
				[2, 1],
			],
			-8,
			-2,
		),
		[],
	);
});
import * as THREE from "three";
import { smoothSectionMeshes } from "../web/src/section-view.js";
import { clipLineGeometry } from "../web/src/clip-geometry.js";
test("任意断面は滑らかな岩体形状を使い、断面積を保つ", () => {
	const box = new THREE.BoxGeometry(2, 2, 2);
	box.translate(0, -1, 0);
	const meshes = smoothSectionMeshes(
		[{ unit: 1 }],
		[
			[-2000, -1000],
			[2000, 1000],
		],
		(p) => [p[0] / 1000, p[2] / 1000, -p[1] / 1000],
		() => box,
		[null, new THREE.MeshBasicMaterial()],
	);
	assert.equal(meshes.length, 1);
	const p = meshes[0].geometry.attributes.position;
	let area = 0;
	for (let i = 0; i < p.count; i += 3) {
		const a = new THREE.Vector3().fromBufferAttribute(p, i),
			b = new THREE.Vector3().fromBufferAttribute(p, i + 1),
			c = new THREE.Vector3().fromBufferAttribute(p, i + 2);
		area += b.sub(a).cross(c.sub(a)).length() / 2;
	}
	assert.ok(Math.abs(area - 2 * Math.sqrt(5)) < 1e-4);
});
test("断層線は三角形メッシュと同様にGLBでも切り取られる", () => {
	const g = new THREE.BufferGeometry();
	g.setAttribute(
		"position",
		new THREE.Float32BufferAttribute([-2, 0, 0, 2, 0, 0, 3, 0, 0, 4, 0, 0], 3),
	);
	const result = clipLineGeometry(g, [
		new THREE.Plane(new THREE.Vector3(-1, 0, 0), 0),
	]);
	assert.equal(result.attributes.position.count, 2);
	assert.equal(result.attributes.position.getX(1), 0);
});
test("メッシュの頂点を通る切断でも1つの閉じた輪郭を保つ", () => {
	const box = new THREE.BoxGeometry(2, 2, 2);
	const meshes = smoothSectionMeshes(
		[{ unit: 1 }],
		[
			[-2000, -2000],
			[2000, 2000],
		],
		(p) => [p[0] / 1000, p[2] / 1000, -p[1] / 1000],
		() => box,
		[null, new THREE.MeshBasicMaterial()],
	);
	assert.equal(meshes.length, 1);
	const p = meshes[0].geometry.attributes.position;
	let area = 0;
	for (let i = 0; i < p.count; i += 3) {
		const a = new THREE.Vector3().fromBufferAttribute(p, i),
			b = new THREE.Vector3().fromBufferAttribute(p, i + 1),
			c = new THREE.Vector3().fromBufferAttribute(p, i + 2);
		area += b.sub(a).cross(c.sub(a)).length() / 2;
	}
	assert.ok(Math.abs(area - 4 * Math.sqrt(2)) < 1e-4);
});

test("展開した断面は屈曲部でも距離と標高を保つ", async () => {
	const { flattenSectionMeshes } = await import("../web/src/section-view.js");
	const g = new THREE.BufferGeometry();
	g.setAttribute(
		"position",
		new THREE.Float32BufferAttribute([1, -0.1, 0, 1, -0.2, -1, 1, -0.3, -2], 3),
	);
	const m = new THREE.Mesh(g);
	m.userData = { unit: 8, sectionLeg: 1 };
	const result = flattenSectionMeshes(
		[m],
		[
			[0, 0],
			[1000, 0],
			[1000, 2000],
		],
		(p) => [p[0] / 1000, p[2] / 1000, -p[1] / 1000],
	);
	const expected = [1000, -100, 2000, -200, 3000, -300];
	result[0].triangles.forEach((n, i) =>
		assert.ok(Math.abs(n - expected[i]) < 0.001),
	);
});

test("断面の不透明度は非表示で0、表示で100を使う", () => {
	const box = new THREE.BoxGeometry(2, 2, 2),
		material = new THREE.MeshBasicMaterial();
	const slice = (opacity) =>
		smoothSectionMeshes(
			[{ unit: 1 }],
			[
				[-2000, 0],
				[2000, 0],
			],
			(p) => [p[0] / 1000, p[2] / 1000, -p[1] / 1000],
			() => box,
			[null, material],
			[],
			opacity,
		);
	assert.equal(slice([0]).length, 0);
	const opaque = slice([100]);
	assert.equal(opaque.length, 1);
	assert.ok(opaque[0].geometry.attributes.position.count > 0);
	for (const m of opaque) m.geometry.dispose();
	box.dispose();
	material.dispose();
});
