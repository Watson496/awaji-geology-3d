import { test } from "node:test";
import assert from "node:assert/strict";
import * as THREE from "three";
import { clipGeometry } from "../web/src/clip-geometry.js";

test("切断後のGLB用メッシュは残す半面だけを持ち、面積と法線を保つ", () => {
	const source = new THREE.PlaneGeometry(2, 2),
		plane = new THREE.Plane(new THREE.Vector3(-1, 0, 0), 0);
	const geometry = clipGeometry(source, [plane]),
		p = geometry.attributes.position,
		n = geometry.attributes.normal;
	let area = 0;
	for (let i = 0; i < p.count; i += 3) {
		const a = new THREE.Vector3().fromBufferAttribute(p, i),
			b = new THREE.Vector3().fromBufferAttribute(p, i + 1),
			c = new THREE.Vector3().fromBufferAttribute(p, i + 2);
		area += b.clone().sub(a).cross(c.clone().sub(a)).length() / 2;
	}
	assert.ok(Math.abs(area - 2) < 1e-6);
	for (let i = 0; i < p.count; i++) {
		assert.ok(p.getX(i) <= 1e-6);
		assert.ok(Math.abs(n.getZ(i) - 1) < 1e-6);
	}
	assert.equal(source.attributes.position.count, 4);
	geometry.dispose();
	source.dispose();
});
