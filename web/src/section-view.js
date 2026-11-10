import * as THREE from "three";
import { clipGeometry } from "./clip-geometry.js";

// Categorical trilinear sampling: interpolate indicator weights, never unit IDs.
export function sampleUnit(volume, meta, east, north, elevation) {
	const [nx, ny] = meta.shape,
		nz = meta.nz,
		[xmin, xmax, ymin, ymax] = meta.extent_xy;
	const coords = [
		((east - xmin) / (xmax - xmin)) * nx - 0.5,
		((north - ymin) / (ymax - ymin)) * ny - 0.5,
		((elevation - meta.zmin) / (meta.zmax - meta.zmin)) * nz - 0.5,
	];
	if (coords.some((v, i) => v < -0.5 || v >= [nx, ny, nz][i] - 0.5)) return 0;
	const base = coords.map(Math.floor),
		frac = coords.map((v, i) => v - base[i]),
		weights = new Map();
	for (let a = 0; a < 2; a++)
		for (let b = 0; b < 2; b++)
			for (let c = 0; c < 2; c++) {
				const i = Math.max(0, Math.min(nx - 1, base[0] + a)),
					j = Math.max(0, Math.min(ny - 1, base[1] + b)),
					k = Math.max(0, Math.min(nz - 1, base[2] + c));
				const id = volume[(i * ny + j) * nz + k],
					w =
						(a ? frac[0] : 1 - frac[0]) *
						(b ? frac[1] : 1 - frac[1]) *
						(c ? frac[2] : 1 - frac[2]);
				weights.set(id, (weights.get(id) || 0) + w);
			}
	return [...weights].sort((a, b) => b[1] - a[1])[0]?.[0] || 0;
}
function plane(a, b, bottom, top, xyz) {
	const g = new THREE.BufferGeometry();
	g.setAttribute(
		"position",
		new THREE.Float32BufferAttribute(
			[
				...xyz([a[0], a[1], bottom]),
				...xyz([b[0], b[1], bottom]),
				...xyz([b[0], b[1], top]),
				...xyz([a[0], a[1], top]),
			],
			3,
		),
	);
	g.setAttribute(
		"uv",
		new THREE.Float32BufferAttribute([0, 0, 1, 0, 1, 1, 0, 1], 2),
	);
	g.setIndex([0, 1, 2, 0, 2, 3]);
	g.computeVertexNormals();
	return g;
}
export function sectionMeshes(
	volume,
	meta,
	route,
	settings,
	xyz,
	reference,
	image,
) {
	const lengths = route
		.slice(1)
		.map((p, i) => Math.hypot(p[0] - route[i][0], p[1] - route[i][1]));
	const total = lengths.reduce((a, b) => a + b, 0);
	let distance = 0;
	const meshes = [];
	const colors = meta.units.map((u) =>
		[1, 3, 5].map((n) => parseInt(u.color.slice(n, n + 2), 16)),
	);
	for (let leg = 0; leg < lengths.length; leg++) {
		const a = route[leg],
			b = route[leg + 1],
			width = Math.max(16, Math.ceil((700 * lengths[leg]) / total)),
			height = 300;
		if (!settings.smoothSection) {
			const canvas = document.createElement("canvas");
			canvas.width = width;
			canvas.height = height;
			const ctx = canvas.getContext("2d"),
				pixels = ctx.createImageData(width, height);
			for (let y = 0; y < height; y++)
				for (let x = 0; x < width; x++) {
					const f = (x + 0.5) / width,
						z = meta.zmax - ((y + 0.5) / height) * (meta.zmax - meta.zmin);
					const id = sampleUnit(
							volume,
							meta,
							a[0] + f * (b[0] - a[0]),
							a[1] + f * (b[1] - a[1]),
							z,
						),
						offset = (y * width + x) * 4;
					if (!id || settings.hidden?.includes(id)) continue;
					const c = colors[id - 1];
					pixels.data.set(c, offset);
					pixels.data[offset + 3] = Math.round(
						255 * ((settings.opacity[id - 1] ?? 100) / 100),
					);
				}
			ctx.putImageData(pixels, 0, 0);
			const texture = new THREE.CanvasTexture(canvas);
			texture.colorSpace = THREE.SRGBColorSpace;
			texture.magFilter = THREE.NearestFilter;
			texture.minFilter = THREE.LinearFilter;
			const material = new THREE.MeshBasicMaterial({
				map: texture,
				side: THREE.DoubleSide,
				transparent: true,
				depthWrite: false,
			});
			const m = new THREE.Mesh(
				plane(a, b, meta.zmin, meta.zmax, xyz),
				material,
			);
			m.userData = {
				section: true,
				rasterSection: true,
				disposableMaterial: true,
			};
			meshes.push(m);
		}
		if (reference && image && settings.referenceOpacity > 0) {
			const c = document.createElement("canvas");
			c.width = width;
			c.height = image.height;
			const cc = c.getContext("2d");
			cc.drawImage(
				image,
				(image.width * distance) / total,
				0,
				(image.width * lengths[leg]) / total,
				image.height,
				0,
				0,
				width,
				image.height,
			);
			const t = new THREE.CanvasTexture(c);
			t.colorSpace = THREE.SRGBColorSpace;
			const mat = new THREE.MeshBasicMaterial({
				map: t,
				side: THREE.DoubleSide,
				transparent: true,
				opacity: settings.referenceOpacity / 100,
				polygonOffset: true,
				polygonOffsetFactor: -4,
				depthWrite: false,
			});
			const overlay = new THREE.Mesh(
				plane(
					a,
					b,
					reference.image_range_m[2],
					reference.image_range_m[3],
					xyz,
				),
				mat,
			);
			overlay.renderOrder = 8;
			overlay.userData = {
				section: true,
				referenceImage: true,
				section_id: reference.id,
				source_url: reference.source_url,
				attribution: reference.attribution,
				calibration: reference.calibration,
				disposableMaterial: true,
			};
			meshes.push(overlay);
		}
		distance += lengths[leg];
	}
	return meshes;
}

export function faultSectionSegments(triangles, route, zmin, zmax) {
	const segments = [];
	for (let leg = 1; leg < route.length; leg++) {
		const a = route[leg - 1],
			b = route[leg],
			length = Math.hypot(b[0] - a[0], b[1] - a[1]);
		if (length < 1) continue;
		const tangent = [(b[0] - a[0]) / length, (b[1] - a[1]) / length],
			normal = [tangent[1], -tangent[0]];
		for (const tri of triangles) {
			const signed = tri.map(
				(p) => (p[0] - a[0]) * normal[0] + (p[1] - a[1]) * normal[1],
			);
			if (signed.every((v) => v > 0) || signed.every((v) => v < 0)) continue;
			const points = [];
			for (let i = 0; i < 3; i++) {
				const j = (i + 1) % 3;
				if (signed[i] * signed[j] > 0 || Math.abs(signed[i] - signed[j]) < 1e-9)
					continue;
				const t = signed[i] / (signed[i] - signed[j]);
				points.push(tri[i].map((v, k) => v + t * (tri[j][k] - v)));
			}
			if (points.length < 2) continue;
			const p = points[0],
				q = points[1],
				sp = (p[0] - a[0]) * tangent[0] + (p[1] - a[1]) * tangent[1],
				sq = (q[0] - a[0]) * tangent[0] + (q[1] - a[1]) * tangent[1];
			let lo = 0,
				hi = 1;
			for (const [v, d, mn, mx] of [
				[sp, sq - sp, 0, length],
				[p[2], q[2] - p[2], zmin, zmax],
			]) {
				if (Math.abs(d) < 1e-9) {
					if (v < mn || v > mx) {
						hi = -1;
						break;
					}
				} else {
					const t0 = (mn - v) / d,
						t1 = (mx - v) / d;
					lo = Math.max(lo, Math.min(t0, t1));
					hi = Math.min(hi, Math.max(t0, t1));
				}
			}
			if (lo <= hi)
				segments.push([
					p.map((v, k) => v + lo * (q[k] - v)),
					p.map((v, k) => v + hi * (q[k] - v)),
				]);
		}
	}
	return segments;
}

// Slice the actual smooth body meshes, so arbitrary sections use precisely the
// same boundaries as the 3D bodies rather than displaying a new raster model.
export function smoothSectionMeshes(
	entries,
	route,
	xyz,
	getGeometry,
	materials,
	hidden = [],
	opacity = [],
) {
	const meshes = [];
	const inside = (p, loop) => {
		let result = false;
		for (let i = 0, j = loop.length - 1; i < loop.length; j = i++) {
			const a = loop[i],
				b = loop[j];
			if (
				a[1] > p[1] !== b[1] > p[1] &&
				p[0] < ((b[0] - a[0]) * (p[1] - a[1])) / (b[1] - a[1]) + a[0]
			)
				result = !result;
		}
		return result;
	};
	for (let leg = 1; leg < route.length; leg++) {
		const a = xyz([route[leg - 1][0], route[leg - 1][1], 0]),
			b = xyz([route[leg][0], route[leg][1], 0]),
			length = Math.hypot(b[0] - a[0], b[2] - a[2]);
		if (length < 1e-5) continue;
		const tx = (b[0] - a[0]) / length,
			tz = (b[2] - a[2]) / length,
			nx = tz,
			nz = -tx;
		for (const entry of entries) {
			if (hidden.includes(entry.unit) || opacity[entry.unit - 1] === 0)
				continue;
			const geometry = getGeometry(entry),
				positions = geometry.attributes.position.array,
				indices = geometry.index?.array,
				count = indices ? indices.length : positions.length / 3;
			const edgeKeys = new Set();
			const nodes = new Map(),
				edges = [],
				adjacency = new Map();
			const node = (p) => {
				const key = p.map((v) => Math.round(v / 1e-5)).join(",");
				if (!nodes.has(key)) nodes.set(key, p);
				return key;
			};
			for (let i = 0; i < count; i += 3) {
				const ids = [0, 1, 2].map((k) => (indices ? indices[i + k] : i + k));
				const signed = ids
					.map(
						(j) =>
							(positions[j * 3] - a[0]) * nx +
							(positions[j * 3 + 2] - a[2]) * nz,
					)
					.map((d) => (Math.abs(d) < 1e-9 ? 0 : d));
				if (signed.every((d) => d > 1e-9) || signed.every((d) => d < -1e-9))
					continue;
				const hits = [];
				for (let j = 0; j < 3; j++) {
					const k = (j + 1) % 3;
					if (
						signed[j] * signed[k] > 0 ||
						Math.abs(signed[j] - signed[k]) < 1e-12
					)
						continue;
					const f = signed[j] / (signed[j] - signed[k]),
						p = ids[j] * 3,
						q = ids[k] * 3;
					const x = positions[p] + f * (positions[q] - positions[p]),
						y = positions[p + 1] + f * (positions[q + 1] - positions[p + 1]),
						z = positions[p + 2] + f * (positions[q + 2] - positions[p + 2]);
					hits.push([(x - a[0]) * tx + (z - a[2]) * tz, y]);
				}
				const keys = [...new Set(hits.map(node))];
				if (keys.length < 2) continue;
				const [u, v] = keys;
				if (u === v) continue;
				const edgeKey = [u, v].sort().join("|");
				if (edgeKeys.has(edgeKey)) continue;
				edgeKeys.add(edgeKey);
				const id = edges.length;
				edges.push([u, v]);
				for (const key of [u, v]) {
					if (!adjacency.has(key)) adjacency.set(key, []);
					adjacency.get(key).push(id);
				}
			}
			const used = new Set(),
				loops = [];
			for (let e = 0; e < edges.length; e++) {
				if (used.has(e)) continue;
				const start = edges[e][0];
				let current = start,
					edge = e;
				const loop = [];
				for (let n = 0; n <= edges.length; n++) {
					used.add(edge);
					loop.push(nodes.get(current));
					const [u, v] = edges[edge];
					current = current === u ? v : u;
					if (current === start) break;
					const next = (adjacency.get(current) || []).find((i) => !used.has(i));
					if (next === undefined) break;
					edge = next;
				}
				if (current === start && loop.length >= 3) loops.push(loop);
			}
			const areas = loops.map((loop) =>
				Math.abs(
					THREE.ShapeUtils.area(loop.map((p) => new THREE.Vector2(...p))),
				),
			);
			const parents = loops.map((loop, i) => {
				let parent = -1;
				for (let j = 0; j < loops.length; j++)
					if (
						areas[j] > areas[i] + 1e-10 &&
						inside(loop[0], loops[j]) &&
						(parent < 0 || areas[j] < areas[parent])
					)
						parent = j;
				return parent;
			});
			const depth = (i) => (parents[i] < 0 ? 0 : depth(parents[i]) + 1);
			const shapes = [];
			for (let i = 0; i < loops.length; i++) {
				if (depth(i) % 2) continue;
				const shape = new THREE.Shape(
					loops[i].map((p) => new THREE.Vector2(...p)),
				);
				for (let j = 0; j < loops.length; j++)
					if (parents[j] === i)
						shape.holes.push(
							new THREE.Path(loops[j].map((p) => new THREE.Vector2(...p))),
						);
				shapes.push(shape);
			}
			if (!shapes.length) continue;
			const flat = new THREE.ShapeGeometry(shapes),
				p = flat.attributes.position;
			for (let i = 0; i < p.count; i++) {
				const u = p.getX(i),
					y = p.getY(i);
				p.setXYZ(i, a[0] + u * tx, y, a[2] + u * tz);
			}
			flat.computeVertexNormals();
			const clipped = clipGeometry(flat, [
				new THREE.Plane(new THREE.Vector3(tx, 0, tz), -a[0] * tx - a[2] * tz),
				new THREE.Plane(
					new THREE.Vector3(-tx, 0, -tz),
					a[0] * tx + a[2] * tz + length,
				),
			]);
			flat.dispose();
			if (!clipped.attributes.position.count) {
				clipped.dispose();
				continue;
			}
			const mesh = new THREE.Mesh(clipped, materials[entry.unit]);
			mesh.userData = {
				unit: entry.source_unit ?? entry.unit,
				body: entry.unit,
				section: true,
				sectionLeg: leg - 1,
			};
			meshes.push(mesh);
		}
	}
	return meshes;
}

// Unfold each leg into the same distance/elevation coordinates as the source figure.
export function flattenSectionMeshes(meshes, route, xyz) {
	const lengths = route
		.slice(1)
		.map((p, i) => Math.hypot(p[0] - route[i][0], p[1] - route[i][1]));
	const chain = [0];
	for (const n of lengths) chain.push(chain.at(-1) + n);
	return meshes.map((mesh) => {
		const leg = mesh.userData.sectionLeg,
			a = xyz([...route[leg], 0]),
			b = xyz([...route[leg + 1], 0]);
		const length = lengths[leg] / 1000,
			tx = (b[0] - a[0]) / length,
			tz = (b[2] - a[2]) / length;
		const p = mesh.geometry.attributes.position,
			index = mesh.geometry.index;
		const triangles = [];
		for (let k = 0; k < (index ? index.count : p.count); k++) {
			const j = index ? index.getX(k) : k;
			triangles.push(
				chain[leg] + ((p.getX(j) - a[0]) * tx + (p.getZ(j) - a[2]) * tz) * 1000,
				p.getY(j) * 1000,
			);
		}
		return {
			unit: mesh.userData.body ?? mesh.userData.unit,
			source_unit: mesh.userData.unit,
			triangles,
		};
	});
}
