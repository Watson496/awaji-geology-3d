import * as THREE from "three";

// 画面で切り取った形状をGLBにも保存する。法線と頂点色は交点まで補間する。
export function clipGeometry(geometry, planes) {
	if (!planes.length) return geometry.clone();
	const position = geometry.attributes.position,
		normal = geometry.attributes.normal,
		color = geometry.attributes.color,
		index = geometry.index;
	const output = [],
		normals = [],
		colors = [];
	const read = (i) => [
		position.getX(i),
		position.getY(i),
		position.getZ(i),
		normal?.getX(i) || 0,
		normal?.getY(i) || 0,
		normal?.getZ(i) || 0,
		...(color ? [color.getX(i), color.getY(i), color.getZ(i)] : []),
	];
	const distance = (p, v) =>
		p.normal.x * v[0] + p.normal.y * v[1] + p.normal.z * v[2] + p.constant;
	const count = index ? index.count : position.count;
	for (let i = 0; i < count; i += 3) {
		let polygon = [0, 1, 2].map((n) => read(index ? index.getX(i + n) : i + n));
		for (const plane of planes) {
			const next = [];
			for (let j = 0; j < polygon.length; j++) {
				const a = polygon[j],
					b = polygon[(j + 1) % polygon.length],
					da = distance(plane, a),
					db = distance(plane, b);
				if (da >= 0) next.push(a);
				if (da >= 0 !== db >= 0) {
					const t = da / (da - db);
					next.push(a.map((v, k) => v + (b[k] - v) * t));
				}
			}
			polygon = next;
			if (polygon.length < 3) break;
		}
		for (let j = 1; j < polygon.length - 1; j++)
			for (const v of [polygon[0], polygon[j], polygon[j + 1]]) {
				output.push(...v.slice(0, 3));
				const length = Math.hypot(v[3], v[4], v[5]) || 1;
				normals.push(v[3] / length, v[4] / length, v[5] / length);
				if (color) colors.push(...v.slice(6, 9));
			}
	}
	const result = new THREE.BufferGeometry();
	result.setAttribute("position", new THREE.Float32BufferAttribute(output, 3));
	result.setAttribute("normal", new THREE.Float32BufferAttribute(normals, 3));
	if (color)
		result.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
	return result;
}

export function clipLineGeometry(geometry, planes) {
	if (!planes.length) return geometry.clone();
	const p = geometry.attributes.position,
		index = geometry.index,
		points = [];
	for (let i = 0; i < (index ? index.count : p.count); i += 2) {
		const a = new THREE.Vector3().fromBufferAttribute(
				p,
				index ? index.getX(i) : i,
			),
			b = new THREE.Vector3().fromBufferAttribute(
				p,
				index ? index.getX(i + 1) : i + 1,
			);
		let lo = 0,
			hi = 1;
		for (const plane of planes) {
			const da = plane.distanceToPoint(a),
				db = plane.distanceToPoint(b);
			if (da < 0 && db < 0) {
				hi = -1;
				break;
			}
			if (da < 0 !== db < 0) {
				const t = da / (da - db);
				if (da < 0) lo = Math.max(lo, t);
				else hi = Math.min(hi, t);
			}
		}
		if (lo <= hi)
			points.push(
				...a.clone().lerp(b, lo).toArray(),
				...a.clone().lerp(b, hi).toArray(),
			);
	}
	const result = new THREE.BufferGeometry();
	result.setAttribute("position", new THREE.Float32BufferAttribute(points, 3));
	return result;
}
export function clipPointGeometry(geometry, planes) {
	if (!planes.length) return geometry.clone();
	const p = geometry.attributes.position,
		keep = [];
	for (let i = 0; i < p.count; i++) {
		const v = new THREE.Vector3().fromBufferAttribute(p, i);
		if (planes.every((plane) => plane.distanceToPoint(v) >= 0)) keep.push(i);
	}
	const result = new THREE.BufferGeometry();
	for (const [name, attr] of Object.entries(geometry.attributes)) {
		const values = [];
		for (const i of keep)
			for (let k = 0; k < attr.itemSize; k++)
				values.push(attr.array[i * attr.itemSize + k]);
		result.setAttribute(
			name,
			new THREE.Float32BufferAttribute(values, attr.itemSize),
		);
	}
	return result;
}
