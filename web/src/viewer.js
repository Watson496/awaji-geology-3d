import { dataUrl } from "./data-url.js";
import * as THREE from "three";
import { LineSegments2 } from "three/addons/lines/LineSegments2.js";
import { LineSegmentsGeometry } from "three/addons/lines/LineSegmentsGeometry.js";
import { LineMaterial } from "three/addons/lines/LineMaterial.js";
import {
	sectionMeshes,
	sampleUnit,
	faultSectionSegments,
	smoothSectionMeshes,
	flattenSectionMeshes,
} from "./section-view.js";
import {
	clipGeometry,
	clipLineGeometry,
	clipPointGeometry,
} from "./clip-geometry.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFExporter } from "three/addons/exporters/GLTFExporter.js";

export function createViewer(view, callbacks = {}) {
	const settings = {
		scenario: "reference",
		cut: [100, 144, 52],
		surface: true,
		rocksVisible: true,
		showDiagram: false,
		surfaceOpacity: 65,
		horizontalReversed: false,
		opacity: [],
		points: false,
		faults: true,
		faultLayers: ["seamless", "active"],
		activeMap: false,
		activeMapOpacity: 100,
		faultPlanes: true,
		marine: false,
		selectedFault: "all",

		volumeCut: false,
		cutReversed: false,
		sectionRoute: [
			[30, 160],
			[170, 130],
		],
		referenceSection: "free",
		referenceOpacity: 0,
		difference: false,
		exaggeration: 3,
		panel: window.innerWidth > 650,
	};
	const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
	renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
	renderer.outputColorSpace = THREE.SRGBColorSpace;
	renderer.setClearColor(0, 0);
	renderer.localClippingEnabled = true;
	view.appendChild(renderer.domElement);
	const scene = new THREE.Scene();
	scene.add(new THREE.HemisphereLight(0xffffff, 0x7d8185, 2.4));
	const sun = new THREE.DirectionalLight(0xffffff, 2.6);
	sun.position.set(-30, 45, 20);
	scene.add(sun);
	const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 400);
	const controls = new OrbitControls(camera, renderer.domElement);
	controls.enableDamping = true;
	controls.minDistance = 8;
	controls.maxDistance = 170;
	const root = new THREE.Group();
	root.scale.y = 3;
	scene.add(root);
	const geology = new THREE.Group(),
		observation = new THREE.Group(),
		evidence = new THREE.Group(),
		traces = new THREE.Group(),
		frame = new THREE.Group();
	root.add(geology, observation, evidence, traces, frame);
	const marineGroup = new THREE.Group();
	root.add(marineGroup);
	let marineSurface;
	const grid = new THREE.GridHelper(80, 16, 0xc5cbd0, 0xdce1e5);
	grid.position.y = -9.1;
	scene.add(grid);
	let meta,
		volume,
		observed,
		terrain,
		disagreement,
		constraints,
		metrics,
		problemColumns;
	let nx, ny, nz, xmin, xmax, ymin, ymax, dx, dy, dz, cx, cy;
	let faultCatalog,
		displayCatalog,
		faultSurfaces = [],
		sectionCatalog;
	const referenceImages = new Map();
	let hidden = new Set(),
		sequence = 0,
		disposed = false;
	const materials = [];
	const purple = new THREE.MeshStandardMaterial({
		color: 0xa271c6,
		roughness: 0.85,
		side: THREE.DoubleSide,
	});
	const observedMaterial = new THREE.MeshStandardMaterial({
		polygonOffset: true,
		polygonOffsetFactor: -2,
		polygonOffsetUnits: -2,
		vertexColors: true,
		side: THREE.DoubleSide,
		roughness: 1,
	});
	const faultMaterial = new THREE.LineBasicMaterial({
		color: 0x111111,
		depthTest: false,
	});
	function home(direction = "iso") {
		const views = {
			iso: [48, 40, 61],
			top: [0, 85, 0.01],
			south: [0, 5, 82],
			east: [82, 5, 0],
		};
		camera.position.set(...(views[direction] || views.iso));
		controls.target.set(0, 0, 0);
		controls.update();
	}
	home();
	function resize() {
		const w = view.clientWidth,
			h = view.clientHeight;
		if (!w || !h) return;
		renderer.setSize(w, h);
		camera.aspect = w / h;
		camera.fov = Math.max(
			35,
			Math.min(
				82,
				(2 * Math.atan((58 * h) / (180 * Math.max(160, w - 50))) * 180) /
					Math.PI,
			),
		);
		camera.clearViewOffset();
		camera.updateProjectionMatrix();
		traces.traverse((o) => o.material?.resolution?.set(w, h));
	}
	const observer = new ResizeObserver(resize);
	observer.observe(view);
	resize();
	let lastBearing = 0;
	renderer.setAnimationLoop(() => {
		controls.update();
		renderer.render(scene, camera);
		const n = new THREE.Vector3(0, 0, -1).applyQuaternion(
			camera.quaternion.clone().invert(),
		);
		const bearing = (Math.atan2(n.x, n.y) * 180) / Math.PI;
		if (Math.abs(bearing - lastBearing) > 0.5) {
			callbacks.onBearing?.(bearing);
			lastBearing = bearing;
		}
	});
	async function load(url, kind = "json") {
		const r = await fetch(dataUrl(url));
		if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
		return kind === "json" ? r.json() : r.arrayBuffer();
	}
	function clear(group) {
		for (const child of [...group.children]) {
			group.remove(child);
			if (!child.userData.cached) child.geometry?.dispose();
			if (child.userData.disposableMaterial) {
				child.material.map?.dispose();
				child.material.dispose();
			}
			if (group === frame) child.material?.dispose();
		}
	}
	function xyz(p) {
		return [(p[0] - cx) / 1000, p[2] / 1000, -(p[1] - cy) / 1000];
	}
	function index(i, j, k) {
		return (i * ny + j) * nz + k;
	}
	function volumeRoute() {
		return [settings.sectionRoute[0], settings.sectionRoute.at(-1)].map(
			([i, j]) => [xmin + i * dx, ymin + j * dy],
		);
	}
	function cuts() {
		return settings.cut;
	}
	function updateFrame(cut) {
		clear(frame);
		if (settings.volumeCut) return;

		if (!settings.rocksVisible) return;
		const left = (xmin - cx) / 1000,
			right = (xmax - cx) / 1000,
			south = -(ymin - cy) / 1000,
			north = -(ymax - cy) / 1000,
			bottom = meta.zmin / 1000,
			top = meta.zmax / 1000;
		const x = (xmin + (cut[0] - 0.5) * dx - cx) / 1000,
			z = -(ymin + (cut[1] - 0.5) * dy - cy) / 1000,
			y = (meta.zmin + (cut[2] - 0.5) * dz) / 1000;
		const points = [
			[
				[x, bottom, south],
				[x, bottom, north],
				[x, top, north],
				[x, top, south],
			],
			[
				[left, bottom, z],
				[right, bottom, z],
				[right, top, z],
				[left, top, z],
			],
			[
				[left, y, south],
				[right, y, south],
				[right, y, north],
				[left, y, north],
			],
		];
		for (let axis = 2; axis < 3; axis++) {
			if (cut[axis] >= [nx, ny, nz][axis]) continue;
			const g = new THREE.BufferGeometry().setFromPoints(
				[...points[axis], points[axis][0]].map((p) => new THREE.Vector3(...p)),
			);
			const line = new THREE.Line(
				g,
				new THREE.LineBasicMaterial({
					color: [0xd66b62, 0x469c83, 0x5389ce][axis],
					transparent: true,
					opacity: 0.65,
				}),
			);
			line.userData.helper = true;
			frame.add(line);
		}
	}
	const geometryCache = new Map(),
		assetCache = new Map();
	let activeAssets, terrainAsset, activeMapMaterial, activeMapOutsideMaterial;
	const bodies = [];
	function array(bytes, entry) {
		return entry.type === "<u4"
			? new Uint32Array(bytes, entry.offset, entry.count)
			: new Float32Array(bytes, entry.offset, entry.count);
	}
	function geometry(bytes, entry, key) {
		if (geometryCache.has(key)) return geometryCache.get(key);
		const g = new THREE.BufferGeometry();
		g.setAttribute(
			"position",
			new THREE.BufferAttribute(array(bytes, entry.positions), 3),
		);
		if (entry.indices)
			g.setIndex(new THREE.BufferAttribute(array(bytes, entry.indices), 1));
		g.computeVertexNormals();
		g.computeBoundingBox();
		geometryCache.set(key, g);
		return g;
	}
	async function assets(name) {
		if (!assetCache.has(name))
			assetCache.set(
				name,
				Promise.all([
					load(`${name}/meshes.json`),
					load(`${name}/meshes.bin`, "binary"),
					load(`${name}/sections.json`),
					load(`${name}/sections.bin`, "binary"),
				]).then(([meshes, meshBytes, sections, sectionBytes]) => ({
					meshes: meshes.map((e) => ({
						...e,
						source_unit: e.unit,
						unit: e.body ?? e.unit,
					})),
					meshBytes,
					sections: sections.map((axis) =>
						axis.map((slice) =>
							slice.map((e) => ({
								...e,
								source_unit: e.unit,
								unit: e.body ?? e.unit,
							})),
						),
					),
					sectionBytes,
					name,
				})),
			);
		return assetCache.get(name);
	}
	function paint(g, unit) {
		if (!settings.difference || g.userData.differenceReady) return;
		const p = g.attributes.position,
			colors = new Float32Array(p.count * 3),
			base = new THREE.Color(meta.rockBodies[unit - 1].color);
		for (let v = 0; v < p.count; v++) {
			const i = Math.max(
					0,
					Math.min(nx - 1, Math.floor((p.getX(v) * 1000 + cx - xmin) / dx)),
				),
				j = Math.max(
					0,
					Math.min(ny - 1, Math.floor((-p.getZ(v) * 1000 + cy - ymin) / dy)),
				),
				k = Math.max(
					0,
					Math.min(nz - 1, Math.floor((p.getY(v) * 1000 - meta.zmin) / dz)),
				);
			const c = disagreement[index(i, j, k)] ? purple.color : base;
			c.toArray(colors, v * 3);
		}
		g.setAttribute("color", new THREE.BufferAttribute(colors, 3));
		g.userData.differenceReady = true;
	}
	function planes() {
		const ps = [];
		if (settings.volumeCut) {
			const [a, b] = volumeRoute().map(
				(p) => new THREE.Vector3(...xyz([p[0], p[1], 0])),
			);
			const delta = b.clone().sub(a);
			if (delta.lengthSq() >= 1e-10) {
				const normal = new THREE.Vector3(-delta.z, 0, delta.x)
					.normalize()
					.multiplyScalar(settings.cutReversed ? -1 : 1);
				ps.push(new THREE.Plane().setFromNormalAndCoplanarPoint(normal, a));
			}
		}

		const c = settings.cut[2],
			epsilon = 0.0001;
		if (c < nz)
			ps.push(
				new THREE.Plane(
					new THREE.Vector3(0, settings.horizontalReversed ? 1 : -1, 0),
					((meta.zmin + (c - 0.5) * dz) / 1000) *
						settings.exaggeration *
						(settings.horizontalReversed ? -1 : 1) +
						epsilon,
				),
			);
		return ps;
	}
	function materialState(mat, opacity, clip) {
		const vertexColors = settings.difference;
		if (!mat.userData.baseColor) mat.userData.baseColor = mat.color.clone();
		mat.color.copy(
			vertexColors ? new THREE.Color(1, 1, 1) : mat.userData.baseColor,
		);
		if (mat.vertexColors !== vertexColors) {
			mat.vertexColors = vertexColors;
			mat.needsUpdate = true;
		}
		if (
			mat.transparent !== opacity < 1 ||
			(mat.clippingPlanes?.length || 0) !== clip.length
		)
			mat.needsUpdate = true;
		mat.opacity = opacity;
		mat.transparent = opacity < 1;
		mat.depthWrite = opacity >= 1;
		mat.clippingPlanes = clip;
	}
	function rebuild() {
		if (meta)
			grid.position.y = (meta.zmin / 1000) * settings.exaggeration - 0.05;
		if (!activeAssets || !terrainAsset) return;
		clear(geology);
		clear(observation);
		clear(traces);
		clear(marineGroup);
		const clip = planes();
		for (const { id } of meta.rockBodies) {
			materialState(
				materials[id],
				(settings.opacity[id - 1] ?? 100) / 100,
				clip,
			);
			materialState(bodies[id], (settings.opacity[id - 1] ?? 100) / 100, clip);
		}
		if (settings.rocksVisible)
			for (const entry of activeAssets.meshes) {
				if (hidden.has(entry.unit) || settings.opacity[entry.unit - 1] === 0)
					continue;
				const g = geometry(
					activeAssets.meshBytes,
					entry,
					`${activeAssets.name}-body-${entry.unit}`,
				);
				paint(g, entry.unit);
				const m = new THREE.Mesh(g, bodies[entry.unit]);
				m.name = meta.rockBodies[entry.unit - 1].name;
				m.userData = {
					unit: entry.source_unit,
					body: entry.unit,
					cached: true,
				};
				geology.add(m);
			}
		if (settings.volumeCut && settings.rocksVisible) {
			const sliced = smoothSectionMeshes(
				activeAssets.meshes,
				volumeRoute(),
				xyz,
				(entry) =>
					geometry(
						activeAssets.meshBytes,
						entry,
						`${activeAssets.name}-body-${entry.unit}`,
					),
				materials,
				[...hidden],
				settings.opacity,
			);
			for (const mesh of sliced)
				paint(mesh.geometry, mesh.userData.body ?? mesh.userData.unit);
			if (sliced.length) geology.add(...sliced);
		}
		if (settings.rocksVisible)
			for (let axis = 2; axis < 3; axis++) {
				if (settings.cut[axis] >= [nx, ny, nz][axis]) continue;
				const entries = activeAssets.sections[axis][settings.cut[axis] - 1];
				for (const entry of entries) {
					if (hidden.has(entry.unit) || settings.opacity[entry.unit - 1] === 0)
						continue;
					const key = `${activeAssets.name}-section-${axis}-${settings.cut[axis]}-${entry.unit}`;
					const g = geometry(activeAssets.sectionBytes, entry, key);
					paint(g, entry.unit);
					const m = new THREE.Mesh(g, materials[entry.unit]);
					m.userData = {
						unit: entry.source_unit,
						body: entry.unit,
						cached: true,
						section: true,
					};
					m.renderOrder = 3;
					geology.add(m);
				}
			}
		if (settings.showDiagram) {
			const reference = sectionCatalog.sections.find(
				(s) => s.id === settings.referenceSection,
			);
			const route =
				reference?.route_xy ||
				settings.sectionRoute.map(([i, j]) => [xmin + i * dx, ymin + j * dy]);
			const sliced = smoothSectionMeshes(
				activeAssets.meshes,
				route,
				xyz,
				(entry) =>
					geometry(
						activeAssets.meshBytes,
						entry,
						`${activeAssets.name}-body-${entry.unit}`,
					),
				materials,
				[...hidden],
				settings.opacity,
			);
			for (const mesh of sliced)
				paint(mesh.geometry, mesh.userData.body ?? mesh.userData.unit);
			const length = route
				.slice(1)
				.reduce(
					(sum, p, i) =>
						sum + Math.hypot(p[0] - route[i][0], p[1] - route[i][1]),
					0,
				);
			const sectionFaults = [];
			let chain = 0;
			for (let leg = 1; leg < route.length; leg++) {
				const a = route[leg - 1],
					b = route[leg],
					len = Math.hypot(b[0] - a[0], b[1] - a[1]);
				if (len < 1) continue;
				for (const f of faultSurfaces) {
					const source = faultCatalog.faults.find((x) => x.id === f.id);
					if (!settings.faults || !f.triangles.length) continue;
					if (!selectedFaultMatches(f, source)) continue;
					for (const pair of faultSectionSegments(
						f.triangles,
						[a, b],
						meta.zmin,
						meta.zmax,
					)) {
						sectionFaults.push({
							dashed: f.attitude_kind === "spatial_strike_analogue",
							points: pair.map((p) => [
								chain +
									((p[0] - a[0]) * (b[0] - a[0]) +
										(p[1] - a[1]) * (b[1] - a[1])) /
										len,
								p[2],
							]),
						});
					}
				}
				chain += len;
			}
			callbacks.onSection?.({
				stations: [
					0,
					...route
						.slice(1)
						.map((_, i) =>
							route
								.slice(1, i + 2)
								.reduce(
									(sum, p, j) =>
										sum + Math.hypot(p[0] - route[j][0], p[1] - route[j][1]),
									0,
								),
						),
				],
				length,
				bottom: meta.zmin,
				top: meta.zmax,
				meshes: flattenSectionMeshes(sliced, route, xyz),
				faults: sectionFaults,
				reference,
			});
			for (const mesh of sliced) mesh.geometry.dispose();
			if (
				route.length > 1 &&
				Math.hypot(route[1][0] - route[0][0], route[1][1] - route[0][1]) > 10
			) {
				const overlays = sectionMeshes(
					volume,
					meta,
					route,
					{ ...settings, smoothSection: true },
					xyz,
					reference,
					referenceImages.get(reference?.id),
				);
				for (const mesh of overlays) mesh.material.clippingPlanes = planes();
				if (overlays.length) geology.add(...overlays);
			}
		}
		buildObserved();
		buildTraces(settings.cut);
		if (settings.showDiagram) {
			const ref = sectionCatalog.sections.find(
				(s) => s.id === settings.referenceSection,
			);
			const route =
				ref?.route_xy ||
				settings.sectionRoute.map(([i, j]) => [xmin + i * dx, ymin + j * dy]);
			const points = [];
			const point = (a, b, t) => {
				const x = a[0] + (b[0] - a[0]) * t,
					y = a[1] + (b[1] - a[1]) * t,
					i = Math.max(0, Math.min(nx - 1, Math.floor((x - xmin) / dx))),
					j = Math.max(0, Math.min(ny - 1, Math.floor((y - ymin) / dy)));
				return xyz([x, y, Math.max(0, terrain[i * ny + j]) + 15]);
			};
			for (let k = 1; k < route.length; k++) {
				const a = route[k - 1],
					b = route[k],
					n = Math.max(
						1,
						Math.ceil(Math.hypot(b[0] - a[0], b[1] - a[1]) / 150),
					);
				for (let i = 0; i < n; i++)
					points.push(...point(a, b, i / n), ...point(a, b, (i + 1) / n));
			}
			const locator = fatFaultLine(points, "section-locator", false, 0x315c9b);
			if (locator)
				locator.userData = {
					sectionLocator: true,
					fatLinePositions: points,
					disposableMaterial: true,
				};
		}

		if (settings.marine && marineSurface?.positions?.length) {
			const g = new THREE.BufferGeometry();
			g.setAttribute(
				"position",
				new THREE.Float32BufferAttribute(
					marineSurface.positions.flatMap(xyz),
					3,
				),
			);
			g.setIndex(marineSurface.indices.flat());
			g.computeVertexNormals();
			const material = new THREE.MeshBasicMaterial({
				color: 0x477d8d,
				side: THREE.DoubleSide,
				transparent: true,
				opacity: 0.45,
				depthWrite: false,
			});
			const mesh = new THREE.Mesh(g, material);
			mesh.userData = {
				disposableMaterial: true,
				structuralSurface: "marine acoustic basement; not a lithology class",
			};
			marineGroup.add(mesh);
		}
		evidence.visible = settings.points;
		updateFrame(settings.cut);
		callbacks.onRender?.({
			scenario: settings.scenario,
			cuts: [...settings.cut],
			mode: "unified",
			rocksVisible: settings.rocksVisible,
			showDiagram: settings.showDiagram,
			surfaceOpacity: settings.surfaceOpacity,
			surfaceVisible: settings.surface && settings.surfaceOpacity > 0,
			surfaceEnabled: settings.surface,
			horizontalReversed: settings.horizontalReversed,
			opacity: [...settings.opacity],
			unitOpacity: bodies.slice(1).map((m) => m.opacity),
			meshCount: geology.children.length,
			bodyCount: geology.children.filter((m) => !m.userData.section).length,
			sectionCount: geology.children.filter((m) => m.userData.section).length,
			observed: observation.children.length > 0,
			volumeCut: settings.volumeCut,
			cutReversed: settings.cutReversed,
			clippingPlane: planes().map((p) => [...p.normal.toArray(), p.constant]),
			sectionRoute: settings.sectionRoute,
			referenceSection: settings.referenceSection,
			referenceOpacity: settings.referenceOpacity,
			selectedFault: settings.selectedFault,
			faultLayers: ["unified"],
			activeMap: settings.activeMap,
			activeMapOpacity: settings.activeMapOpacity,
			activeMapMaterialOpacity: activeMapMaterial?.opacity,
			pointsVisible: evidence.visible,
			differenceVisible: settings.difference,
			activeMapVisible: settings.activeMap && settings.activeMapOpacity > 0,
			faultCount: new Set(
				traces.children
					.map((x) => x.userData.faultId)
					.filter(Boolean)
					.map((id) =>
						settings.selectedFault !== "all"
							? settings.selectedFault
							: displayCatalog.faults.find((f) => f.id === id)?.id ||
								displayCatalog.faults.find((f) => f.model_aliases.includes(id))
									?.id ||
								id,
					),
			).size,
			faultPlaneCount: traces.children.filter((x) => x.userData.faultSurface)
				.length,
			faultPlanes: settings.faultPlanes,
			faultTraceMaterialTransparent: traces.children
				.filter((x) => x.userData.faultTrace)
				.every((x) => x.material.transparent),
			marineSurface: marineGroup.children.length > 0,
		});
	}
	function buildObserved() {
		if (
			!(settings.surface && settings.surfaceOpacity > 0) &&
			!(settings.activeMap && settings.activeMapOpacity > 0)
		)
			return;
		const { data, bytes } = terrainAsset,
			g = geometry(bytes, data, "terrain");
		if (!g.attributes.color) {
			const ids = array(bytes, data.units),
				color = new Float32Array(ids.length * 3);
			for (let i = 0; i < ids.length; i++)
				new THREE.Color(meta.units[ids[i] - 1].color).toArray(color, i * 3);
			g.setAttribute("color", new THREE.BufferAttribute(color, 3));
			g.setAttribute("unit", new THREE.BufferAttribute(ids, 1));
		}
		observedMaterial.needsUpdate = true;
		observedMaterial.clippingPlanes = planes();
		observedMaterial.opacity = settings.surfaceOpacity / 100;
		observedMaterial.transparent = observedMaterial.opacity < 1;
		observedMaterial.depthWrite = observedMaterial.opacity >= 1;
		for (const mat of [activeMapMaterial, activeMapOutsideMaterial])
			if (mat) {
				mat.depthWrite = false;
				mat.opacity = settings.activeMapOpacity / 100;
				mat.clippingPlanes = planes();
				mat.needsUpdate = true;
			}

		if (!g.attributes.uv) {
			const p = g.attributes.position,
				uv = new Float32Array(p.count * 2);
			for (let i = 0; i < p.count; i++) {
				uv[2 * i] = (p.getX(i) * 1000 + cx - xmin) / (xmax - xmin);
				uv[2 * i + 1] = (-p.getZ(i) * 1000 + cy - ymin) / (ymax - ymin);
			}
			g.setAttribute("uv", new THREE.BufferAttribute(uv, 2));
		}
		if (settings.activeMap && settings.activeMapOpacity > 0) {
			const plane = new THREE.PlaneGeometry(
				(xmax - xmin) / 1000,
				(ymax - ymin) / 1000,
			);
			plane.rotateX(-Math.PI / 2);
			const reference = new THREE.Mesh(plane, activeMapOutsideMaterial);
			reference.renderOrder = -1;
			reference.userData = {
				referenceMap:
					"GSI active fault map; offshore at sea-level datum, not a measured seabed",
			};
			observation.add(reference);
		}
		const m = new THREE.Mesh(g, observedMaterial);
		m.userData = { observed: true, cached: true };
		m.renderOrder = 5;
		if (settings.surface && settings.surfaceOpacity > 0) observation.add(m);
		if (settings.activeMap && settings.activeMapOpacity > 0) {
			const overlay = new THREE.Mesh(g, activeMapMaterial);
			overlay.userData = { cached: true, referenceMap: true };
			overlay.renderOrder = 6;
			observation.add(overlay);
		}
	}
	function buildEvidence() {
		clear(evidence);
		const positions = [],
			colors = [];
		for (const [unit, points] of Object.entries(constraints.contacts))
			for (const p of points) {
				positions.push(...xyz(p));
				colors.push(...materials[unit].color.toArray());
			}
		for (const o of constraints.orientations) {
			positions.push(...xyz(o.xyz));
			colors.push(1, 1, 1);
		}
		const g = new THREE.BufferGeometry();
		g.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
		g.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
		evidence.add(
			new THREE.Points(
				g,
				new THREE.PointsMaterial({
					size: 0.18,
					vertexColors: true,
					depthTest: false,
					transparent: true,
					opacity: 0.9,
				}),
			),
		);
		evidence.visible = settings.points;
	}
	function fatFaultLine(points, id, approximate = false, color = 0x111111) {
		if (!points.length) return;
		const g = new LineSegmentsGeometry();
		g.setPositions(points);
		const m = new LineMaterial({
			color,
			transparent: true,
			opacity: 1,
			linewidth: settings.selectedFault === id ? 4 : 2.8,
			dashed: approximate,
			dashSize: 0.4,
			gapSize: 0.2,
			depthTest: false,
			depthWrite: false,
			clippingPlanes: planes(),
		});
		m.resolution.set(view.clientWidth, view.clientHeight);
		const line = new LineSegments2(g, m);
		line.computeLineDistances();
		line.renderOrder = 22;
		line.userData = {
			faultId: id,
			faultTrace: true,
			fatLinePositions: points,
			disposableMaterial: true,
		};
		traces.add(line);
		return line;
	}
	function selectedFaultMatches(f, source) {
		const selected = displayCatalog.faults.find(
			(x) => x.id === settings.selectedFault,
		);
		return (
			settings.selectedFault === "all" ||
			f.id === settings.selectedFault ||
			source.zone_id === settings.selectedFault ||
			selected?.model_aliases?.includes(f.id)
		);
	}
	function buildTraces(cut) {
		if (!settings.faults) return;
		const routes = [];
		if (settings.volumeCut) routes.push(volumeRoute());
		else if (settings.showDiagram) {
			const ref = sectionCatalog.sections.find(
				(s) => s.id === settings.referenceSection,
			);
			routes.push(
				ref?.route_xy ||
					settings.sectionRoute.map(([i, j]) => [xmin + i * dx, ymin + j * dy]),
			);
		}
		{
			for (const f of displayCatalog.faults) {
				if (!selectedFaultMatches(f, f)) continue;
				for (let ti = 0; ti < f.traces.length; ti++) {
					const trace = f.traces[ti],
						points = [];
					for (let i = 1; i < trace.length; i++)
						for (const p of [trace[i - 1], trace[i]])
							points.push(...xyz([p[0], p[1], p[2] + 5]));
					fatFaultLine(points, f.id, f.trace_styles[ti].dashed, 0x111111);
				}
			}
		}
		for (const f of faultSurfaces) {
			const source = faultCatalog.faults.find((x) => x.id === f.id);
			if (!f.triangles.length) continue;
			if (!selectedFaultMatches(f, source)) continue;
			const approximate = source.dashed;
			const points = [];
			for (const route of routes)
				points.push(
					...faultSectionSegments(
						f.triangles,
						route,
						meta.zmin,
						meta.zmax,
					).flatMap((pair) => pair.flatMap(xyz)),
				);
			if (cut[2] < nz) {
				const height = meta.zmin + (cut[2] - 0.5) * dz;
				for (const tri of f.triangles) {
					const hits = [];
					for (let i = 0; i < 3; i++) {
						const a = tri[i],
							b = tri[(i + 1) % 3],
							da = a[2] - height,
							db = b[2] - height;
						if (da * db > 0 || Math.abs(da - db) < 1e-8) continue;
						const t = da / (da - db);
						hits.push(a.map((v, k) => v + t * (b[k] - v)));
					}
					if (hits.length >= 2) points.push(...xyz(hits[0]), ...xyz(hits[1]));
				}
			}
			const color = 0x111111;
			fatFaultLine(
				points,
				f.id,
				approximate || f.attitude_kind === "spatial_strike_analogue",
				color,
			);
			if (!settings.faultPlanes || !f.triangles.length) continue;
			const g = new THREE.BufferGeometry();
			g.setAttribute(
				"position",
				new THREE.Float32BufferAttribute(
					f.triangles.flatMap((t) => t.flatMap(xyz)),
					3,
				),
			);
			g.computeVertexNormals();
			const m = new THREE.MeshStandardMaterial({
				color: settings.selectedFault === f.id ? 0x8b9eae : 0x71899b,
				side: THREE.DoubleSide,
				roughness: 0.85,
				transparent: true,
				opacity: settings.selectedFault === f.id ? 0.75 : 0.45,
				depthWrite: false,
				clippingPlanes: planes(),
			});
			const mesh = new THREE.Mesh(g, m);
			mesh.userData = {
				faultSurface: true,
				faultId: f.id,
				disposableMaterial: true,
			};
			traces.add(mesh);
		}
	}

	async function selectScenario(name) {
		const request = ++sequence;
		callbacks.onLoading?.(true);
		try {
			const [binary, report, smooth, surfaces, marineData] = await Promise.all([
				load(`${name}/volume.bin`, "binary"),
				load(`${name}/metrics.json`),
				assets(name),
				load(`fault-surfaces-${name}.json`),
				load(`${name}/marine-basement.json`),
			]);
			if (disposed || request !== sequence) return;
			activeAssets = smooth;
			faultSurfaces = surfaces;
			marineSurface = marineData;
			volume = new Uint8Array(binary);
			metrics = report;
			settings.scenario = name;
			if (volume.length !== nx * ny * nz)
				throw new Error("モデルの格子サイズが一致しません");
			problemColumns = new Uint8Array(nx * ny);
			callbacks.onMetrics?.({
				...metrics,
				unknownFraction: metrics.unknown_fraction,
				sectionExtrapolationFraction: metrics.section_extrapolation_fraction,
				ambiguousFraction: metrics.ambiguous_fraction,
			});
			rebuild();
			callbacks.onLoading?.(false);
		} catch (e) {
			if (!disposed) callbacks.onError?.(e.message);
		}
	}
	async function init() {
		meta = await load("model.json");
		meta.rockBodyCatalog = await load("rock-bodies.json");
		meta.rockBodies = meta.rockBodyCatalog.bodies;
		if (disposed) return;
		[nx, ny] = meta.shape;
		nz = meta.nz;
		[xmin, xmax, ymin, ymax] = meta.extent_xy;
		dx = (xmax - xmin) / nx;
		dy = (ymax - ymin) / ny;
		dz = (meta.zmax - meta.zmin) / nz;
		cx = (xmin + xmax) / 2;
		cy = (ymin + ymax) / 2;
		settings.cut = [nx, ny, nz];
		settings.opacity = meta.rockBodies.map((u) =>
			u.kind === "unknown" ? 15 : 90,
		);
		const [obs, dem, con, diff, fc, sc, display] = await Promise.all([
			load("observed.bin", "binary"),
			load("terrain.bin", "binary"),
			load("constraints.json"),
			load("disagreement.bin", "binary"),
			load("faults.json"),
			load("sections.json"),
			load("fault-display.json"),
		]);
		if (disposed) return;
		observed = new Uint8Array(obs);
		terrain = new Float32Array(dem);
		constraints = con;
		faultCatalog = fc;
		displayCatalog = display;
		sectionCatalog = sc;
		await Promise.all(
			sc.sections.map(
				(section) =>
					new Promise((resolve, reject) => {
						const img = new Image();
						img.onload = () => {
							referenceImages.set(section.id, img);
							resolve();
						};
						img.onerror = () =>
							reject(new Error(`断面画像を取得できません: ${section.image}`));
						img.src = dataUrl(section.image);
					}),
			),
		);
		disagreement = new Uint8Array(diff);
		root.userData = {
			crs: meta.crs,
			origin_easting_m: cx,
			origin_northing_m: cy,
			coordinate_mapping: "X=east/1000, Y=elevation/1000, Z=-north/1000",
			status: meta.status,
			input_signature: meta.input_signature,
			structural_model: meta.fault_model,
			depth_policy: meta.depth_policy,
			fault_source_layers: fc.layers,
			sections: sc.sections.map((s) => ({
				id: s.id,
				source_url: s.source_url,
				source_sha256: s.source_sha256,
			})),
			source_units: meta.units.map(({ id, source_symbol, name, color }) => ({
				id,
				source_symbol,
				name,
				color,
			})),
			faults: meta.faults,
			rock_body_catalog: meta.rockBodyCatalog,
		};
		for (const unit of meta.rockBodies)
			materials[unit.id] = new THREE.MeshStandardMaterial({
				color: unit.color,
				side: THREE.DoubleSide,
				roughness: 0.9,
			});
		const [terrainData, terrainBytes] = await Promise.all([
			load("terrain-mesh.json"),
			load("terrain-mesh.bin", "binary"),
		]);
		if (disposed) return;
		terrainAsset = { data: terrainData, bytes: terrainBytes };
		const activeMapTexture = await new THREE.TextureLoader().loadAsync(
			dataUrl("gsi-active-fault-map.png"),
		);
		activeMapTexture.colorSpace = THREE.SRGBColorSpace;
		activeMapMaterial = new THREE.MeshBasicMaterial({
			map: activeMapTexture,
			side: THREE.DoubleSide,
			transparent: true,
			opacity: 1,
		});
		// 半透明の参照地図が、モデル化した陸域で二重に合成されるのを防ぐ。
		const outsideCanvas = document.createElement("canvas");
		outsideCanvas.width = activeMapTexture.image.width;
		outsideCanvas.height = activeMapTexture.image.height;
		const context = outsideCanvas.getContext("2d");
		context.drawImage(activeMapTexture.image, 0, 0);
		const image = context.getImageData(
			0,
			0,
			outsideCanvas.width,
			outsideCanvas.height,
		);
		for (let y = 0; y < outsideCanvas.height; y++) {
			const j =
				ny - 1 - Math.min(ny - 1, Math.floor((y / outsideCanvas.height) * ny));
			for (let x = 0; x < outsideCanvas.width; x++) {
				const i = Math.min(nx - 1, Math.floor((x / outsideCanvas.width) * nx));
				if (observed[i * ny + j] !== 0)
					image.data[(y * outsideCanvas.width + x) * 4 + 3] = 0;
			}
		}
		context.putImageData(image, 0, 0);
		const outsideTexture = new THREE.CanvasTexture(outsideCanvas);
		outsideTexture.colorSpace = THREE.SRGBColorSpace;
		activeMapOutsideMaterial = activeMapMaterial.clone();
		activeMapOutsideMaterial.map = outsideTexture;
		activeMapOutsideMaterial.alphaTest = 0.001;

		for (const { id } of meta.rockBodies) bodies[id] = materials[id].clone();
		buildEvidence();
		callbacks.onReady?.({
			...meta,
			observed,
			terrain,
			faultCatalog: display.faults,
			faultZones: fc.fault_zones || [],
			faultLayers: fc.layers,
			sections: sc.sections,
		});
		await selectScenario("reference");
	}
	const ray = new THREE.Raycaster(),
		pointer = new THREE.Vector2();
	let pointerStart;
	function down(e) {
		pointerStart = [e.clientX, e.clientY];
	}
	function up(e) {
		if (
			!volume ||
			!pointerStart ||
			Math.hypot(e.clientX - pointerStart[0], e.clientY - pointerStart[1]) > 5
		)
			return;
		const r = renderer.domElement.getBoundingClientRect();
		pointer.set(
			((e.clientX - r.left) / r.width) * 2 - 1,
			(-(e.clientY - r.top) / r.height) * 2 + 1,
		);
		ray.setFromCamera(pointer, camera);
		const hits = ray
			.intersectObjects([...geology.children, ...observation.children])
			.filter((hit) =>
				planes().every((p) => p.distanceToPoint(hit.point) >= 0),
			);
		const hit = hits[0];
		if (!hit) {
			callbacks.onProbe?.(null);
			return;
		}
		const p = root.worldToLocal(hit.point.clone()),
			east = p.x * 1000 + cx,
			north = -p.z * 1000 + cy,
			z = p.y * 1000;
		const i = Math.max(0, Math.min(nx - 1, Math.floor((east - xmin) / dx))),
			j = Math.max(0, Math.min(ny - 1, Math.floor((north - ymin) / dy)));
		const unit = hit.object.userData.observed
			? hit.object.geometry.attributes.unit.getX(hit.face.a)
			: hit.object.userData.rasterSection
				? sampleUnit(volume, meta, east, north, z)
				: hit.object.userData.unit;
		if (!unit) return;
		callbacks.onProbe?.({
			unit,
			body: hit.object.userData.body,
			z,
			depth: Math.max(0, terrain[i * ny + j] - z),
			problem: !!problemColumns[i * ny + j],
			observed: !!hit.object.userData.observed,
			east,
			north,
		});
	}
	renderer.domElement.addEventListener("pointerdown", down);
	renderer.domElement.addEventListener("pointerup", up);
	init().catch((e) => {
		if (!disposed) callbacks.onError?.(e.message);
	});
	return {
		update(next) {
			const changedFault =
				next.selectedFault !== settings.selectedFault ||
				next.faultPlanes !== settings.faultPlanes;

			Object.assign(settings, next);
			if (nx && settings.cut) settings.cut = [nx, ny, settings.cut[2]];
			if (next.hidden) hidden = new Set(next.hidden);
			root.scale.y = settings.exaggeration;
			resize();
			if (volume) rebuild();
			if (changedFault && settings.selectedFault === "all") home();
			if (changedFault && settings.selectedFault !== "all") {
				const members = faultCatalog.fault_zones?.find(
					(z) => z.id === settings.selectedFault,
				)?.members ||
					displayCatalog.faults.find((f) => f.id === settings.selectedFault)
						?.model_aliases || [settings.selectedFault];
				const meshes = traces.children.filter(
					(o) =>
						o.userData.faultSurface && members.includes(o.userData.faultId),
				);
				const mesh = meshes[0];
				if (mesh) {
					root.updateMatrixWorld(true);
					const box = new THREE.Box3();
					for (const part of meshes)
						box.union(new THREE.Box3().setFromObject(part));
					const center = box.getCenter(new THREE.Vector3()),
						size = box.getSize(new THREE.Vector3());
					const pos = mesh.geometry.attributes.position;
					const a = new THREE.Vector3().fromBufferAttribute(pos, 0),
						b = new THREE.Vector3().fromBufferAttribute(pos, 1),
						c = new THREE.Vector3().fromBufferAttribute(pos, 2);
					root.localToWorld(a);
					root.localToWorld(b);
					root.localToWorld(c);
					const normal = b.sub(a).cross(c.sub(a)).normalize();
					if (normal.dot(camera.position.clone().sub(center)) < 0)
						normal.negate();
					normal.y = Math.max(0.25, normal.y);
					normal.normalize();
					controls.target.copy(center);
					camera.position
						.copy(center)
						.addScaledVector(
							normal,
							Math.max(12, Math.max(size.x, size.y, size.z) * 1.8),
						);
					controls.update();
				}
			}
		},
		selectScenario,
		home,
		async exportGLB() {
			root.updateMatrixWorld(true);
			const output = root.clone(false),
				temporary = [],
				mats = [];
			const inverse = root.matrixWorld.clone().invert(),
				localPlanes = planes().map((p) => p.clone().applyMatrix4(inverse));
			for (const parent of [
				geology,
				observation,
				evidence,
				traces,
				marineGroup,
			]) {
				const group = parent.clone(true),
					empty = [];
				const fat = [];
				group.traverse((o) => {
					if (o.userData.fatLinePositions) fat.push(o);
				});
				for (const o of fat) {
					const g = new THREE.BufferGeometry();
					g.setAttribute(
						"position",
						new THREE.Float32BufferAttribute(o.userData.fatLinePositions, 3),
					);
					const material = new THREE.LineBasicMaterial({
						color: o.material.color.clone(),
					});
					const replacement = new THREE.LineSegments(g, material);
					replacement.userData = {
						faultId: o.userData.faultId,
						sectionLocator: o.userData.sectionLocator || false,
					};
					replacement.matrix.copy(o.matrix);
					replacement.matrixAutoUpdate = false;
					o.parent.add(replacement);
					o.removeFromParent();
					temporary.push(g);
					mats.push(material);
				}
				group.traverse((o) => {
					if (!o.isMesh && !o.isLineSegments && !o.isPoints) return;
					o.geometry = (
						o.isMesh
							? clipGeometry
							: o.isLineSegments
								? clipLineGeometry
								: clipPointGeometry
					)(o.geometry, localPlanes);
					temporary.push(o.geometry);
					if (!o.geometry.attributes.position.count) {
						empty.push(o);
						return;
					}
					o.material = o.material.clone();
					o.material.clippingPlanes = [];
					mats.push(o.material);
				});
				for (const o of empty) o.removeFromParent();
				output.add(group);
			}
			output.userData = {
				...root.userData,
				display_mode: "unified",
				activeMap: settings.activeMap,
				activeMapOpacity: settings.activeMapOpacity,
				surface: settings.surface,
				rocksVisible: settings.rocksVisible,
				showDiagram: settings.showDiagram,
				surfaceOpacity: settings.surfaceOpacity,
				horizontalReversed: settings.horizontalReversed,
				display_smoothing:
					"categorical Gaussian sigma (0.55,0.55,0.25) cells; source inference unchanged",
			};
			try {
				const bytes = await new GLTFExporter().parseAsync(output, {
					binary: true,
					onlyVisible: true,
				});
				const url = URL.createObjectURL(
					new Blob([bytes], { type: "model/gltf-binary" }),
				);
				const a = document.createElement("a");
				a.href = url;
				a.download = `awaji-${settings.scenario}-unified.glb`;
				a.click();
				setTimeout(() => URL.revokeObjectURL(url), 10000);
			} finally {
				for (const g of temporary) g.dispose();
				for (const m of mats) m.dispose();
			}
		},
		dispose() {
			disposed = true;
			sequence++;
			observer.disconnect();
			renderer.setAnimationLoop(null);
			controls.dispose();
			renderer.domElement.removeEventListener("pointerdown", down);
			renderer.domElement.removeEventListener("pointerup", up);
			for (const group of [geology, observation, evidence, traces, frame]) {
				group.traverse((o) => {
					o.geometry?.dispose();
					if (o.material) {
						for (const m of Array.isArray(o.material)
							? o.material
							: [o.material])
							m.dispose();
					}
				});
			}
			for (const g of geometryCache.values()) g.dispose();
			for (const m of bodies) m?.dispose();
			activeMapOutsideMaterial?.map?.dispose();
			activeMapOutsideMaterial?.dispose();
			activeMapMaterial?.map?.dispose();
			activeMapMaterial?.dispose();
			grid.geometry.dispose();
			renderer.dispose();
			renderer.domElement.remove();
		},
	};
}
