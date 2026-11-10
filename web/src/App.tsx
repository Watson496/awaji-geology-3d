import { dataUrl } from "./data-url.js";
import { SectionDiagram, type Diagram } from "./SectionDiagram";
import {
	ActionIcon,
	Accordion,
	Badge,
	Button,
	Divider,
	Group,
	Loader,
	Modal,
	NumberInput,
	type NumberInputProps,
	Paper,
	SegmentedControl,
	Select,
	Slider,
	Stack,
	Table,
	Text,
	TextInput,
	Tooltip,
} from "@mantine/core";
import {
	IconArrowsMaximize,
	IconBox,
	IconCube,
	IconDownload,
	IconEye,
	IconEyeOff,
	IconInfoCircle,
	IconLayersIntersect,
	IconMap,
	IconWaveSine,
	IconPointer,
	IconRefresh,
	IconX,
	IconChevronRight,
	IconChevronLeft,
	IconAlertTriangle,
} from "@tabler/icons-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { createViewer } from "./viewer.js";
import { bodyAgeRank, groupColors } from "./rock-body-legend.js";

type Unit = {
	id: number;
	key: string;
	name: string;
	short_name: string;
	color: string;
	source_symbol: string | null;
	kind: string;
};
type RockBody = Unit & {
	source_unit: number;
	identity: string;
	group: string;
	attribution: string;
	cell_counts: Record<string, number>;
};
type Meta = {
	rockBodies: RockBody[];
	shape: [number, number];
	nz: number;
	zmin: number;
	zmax: number;
	extent_xy: number[];
	spacing_m: [number, number];
	units: Unit[];
	mapped_orientation_count: number;
	observed: Uint8Array;
	terrain: Float32Array;
	faultLayers: { id: string; name: string; color: string }[];
	faultZones: { id: string; name: string; members: string[] }[];
	faultCatalog: {
		id: string;
		name: string;
		notes: string;
		trace_kind: string;
		zone_id?: string;
		layer: string;
		used_for_model: boolean;
		model_aliases?: string[];
		color?: string;
		dashed?: boolean;
		traces: number[][][];
		trace_styles?: { dashed: boolean }[];
	}[];
	sections: {
		id: string;
		name: string;
		route_xy: number[][];
		attribution: string;
		source_url: string;
	}[];
};
type Metrics = {
	fault_conditioning?: {
		substrate?: {
			maximum_transfer_distance_m: number;
			under_cover: Record<
				string,
				{ cells: number; unknown_fraction: number | null }
			>;
		};
	};
	scenario: string;
	surface_agreement: number;
	surface_confusion_matrix_actual_rows: number[][];
	voxel_counts: Record<string, number>;
	unknownFraction: number;
	sectionExtrapolationFraction?: number;
	ambiguousFraction: number;
	audit: { source_unit_id: number; depth_prior_m: number }[];
	section_reproduction?: {
		section_id: string;
		boundary_fit: {
			id: string;
			distance_to_matching_model_interface_m: number | null;
		}[];
	}[];
};
type Probe = {
	unit: number;
	body?: number;
	z: number;
	depth: number;
	problem: boolean;
	observed: boolean;
	east: number;
	north: number;
};
type RenderState = {
	scenario: string;
	cuts: number[];
	meshCount: number;
	observed: boolean;
};
const names: Record<string, string> = {
	reference: "採用モデル",
	shallow: "比較 A",
	deep: "比較 B",
};

const axisColors = ["#ce665d", "#3c9b7d", "#4c86c7"];
function Tool({
	label,
	children,
	onClick,
	active = false,
	disabled = false,
}: {
	label: string;
	children: ReactNode;
	onClick?: () => void;
	active?: boolean;
	disabled?: boolean;
}) {
	return (
		<Tooltip label={label} position="left" withArrow>
			<ActionIcon
				aria-label={label}
				size={34}
				variant={active ? "light" : "subtle"}
				color={active ? "blue" : "gray"}
				onClick={onClick}
				disabled={disabled}
			>
				{children}
			</ActionIcon>
		</Tooltip>
	);
}
function Plan({
	stationLabels,
	faultLayers,
	activeMap,
	activeMapOpacity,
	meta,
	cutting,
	arbitrary,
	faults,
	selectedFault,
	onFaultSelect,
	route,
	onRouteChange,
}: {
	stationLabels?: string[];
	faultLayers: string[];
	activeMap: boolean;
	activeMapOpacity: number;
	meta: Meta;
	cutting: boolean;
	arbitrary: boolean;
	faults: boolean;
	selectedFault: string;
	onFaultSelect: (id: string) => void;
	route: number[][];
	onRouteChange: (route: number[][]) => void;
}) {
	const svg = useRef<SVGSVGElement>(null),
		drag = useRef<number | null>(null);
	const [image, setImage] = useState("");
	useEffect(() => {
		const [nx, ny] = meta.shape,
			canvas = document.createElement("canvas");
		canvas.width = nx;
		canvas.height = ny;
		const ctx = canvas.getContext("2d")!,
			im = ctx.createImageData(nx, ny);
		for (let i = 0; i < nx; i++)
			for (let j = 0; j < ny; j++) {
				const id = meta.observed[i * ny + j];
				if (!id) continue;
				const hex = meta.units[id - 1].color;
				const at = ((ny - 1 - j) * nx + i) * 4;
				im.data[at] = parseInt(hex.slice(1, 3), 16);
				im.data[at + 1] = parseInt(hex.slice(3, 5), 16);
				im.data[at + 2] = parseInt(hex.slice(5, 7), 16);
				im.data[at + 3] = 255;
			}
		ctx.putImageData(im, 0, 0);
		setImage(canvas.toDataURL());
	}, [meta]);
	const [nx, ny] = meta.shape;
	function location(e: React.PointerEvent<SVGSVGElement>) {
		return new DOMPoint(e.clientX, e.clientY).matrixTransform(
			svg.current!.getScreenCTM()!.inverse(),
		);
	}
	function move(e: React.PointerEvent<SVGSVGElement>) {
		if (drag.current === null) return;
		const p = location(e);
		if (arbitrary) {
			const next = route.map((v) => [...v]);
			next[drag.current] = [
				Math.max(0, Math.min(nx, p.x)),
				Math.max(0, Math.min(ny, ny - p.y)),
			];
			onRouteChange(next);
			return;
		}
	}
	return (
		<svg
			className="plan"
			ref={svg}
			viewBox={`-9 -9 ${nx + 18} ${ny + 18}`}
			aria-label="平面図で切断位置を変更"
			onPointerDown={(e) => {
				if (!arbitrary) return;
				const p = location(e);
				drag.current = route
					.map(([x, y]) => Math.hypot(p.x - x, p.y - (ny - y)))
					.reduce((best, d, i, ds) => (d < ds[best] ? i : best), 0);
				e.currentTarget.setPointerCapture(e.pointerId);
				move(e);
			}}
			onPointerMove={move}
			onPointerUp={() => (drag.current = null)}
			onPointerCancel={() => (drag.current = null)}
		>
			<image href={image || undefined} width={nx} height={ny} />
			{activeMap && activeMapOpacity > 0 && (
				<image
					href={dataUrl("gsi-active-fault-map.png")}
					width={nx}
					height={ny}
					opacity={activeMapOpacity / 100}
				/>
			)}
			{faults && (
				<g>
					{meta.faultCatalog
						.filter(
							(f) =>
								selectedFault === "all" ||
								f.id === selectedFault ||
								f.zone_id === selectedFault,
						)
						.flatMap((f) =>
							f.traces.map((trace, ti) => (
								<path
									key={`${f.id}-${ti}`}
									d={trace
										.map(
											(p, i) =>
												`${i ? "L" : "M"}${(p[0] - meta.extent_xy[0]) / meta.spacing_m[0]},${ny - (p[1] - meta.extent_xy[2]) / meta.spacing_m[1]}`,
										)
										.join(" ")}
									fill="none"
									stroke="#111111"
									strokeWidth={selectedFault === f.id ? 2 : 1}
									strokeDasharray={
										f.trace_styles?.[ti]?.dashed ? "3 2" : undefined
									}
									onPointerDown={(e) => e.stopPropagation()}
									onClick={() => onFaultSelect(f.id)}
									role="button"
									tabIndex={0}
									aria-label={`${f.name}を選択（平面図）`}
									onKeyDown={(e) => {
										if (e.key === "Enter" || e.key === " ") {
											e.preventDefault();
											onFaultSelect(f.id);
										}
									}}
								/>
							)),
						)}
				</g>
			)}

			<rect
				width={nx}
				height={ny}
				fill="none"
				stroke="#dfe3e8"
				strokeWidth=".6"
			/>

			{cutting && route.length > 2 && (
				<line
					x1={route[0][0]}
					y1={ny - route[0][1]}
					x2={route.at(-1)![0]}
					y2={ny - route.at(-1)![1]}
					stroke="#315c9b"
					strokeWidth="2"
					strokeDasharray="4 2"
				>
					<title>切断面（端点間）</title>
				</line>
			)}
			{arbitrary && (
				<>
					<polyline
						points={route.map(([x, y]) => `${x},${ny - y}`).join(" ")}
						fill="none"
						stroke="#315c9b"
						strokeWidth="2"
					/>
					{route.map(([x, y], i) => (
						<g key={i}>
							<circle
								cx={x}
								cy={ny - y}
								r="5"
								fill="white"
								stroke="#315c9b"
								strokeWidth="1.5"
							/>
							<text x={x + 7} y={ny - y - 5} fontSize="8">
								{i === 0
									? stationLabels?.[0] || "A"
									: i === route.length - 1
										? stationLabels?.at(-1) || "B"
										: stationLabels?.length === route.length
											? stationLabels?.[i]
											: ""}
							</text>
						</g>
					))}
				</>
			)}
			<text x={nx - 2} y={3} textAnchor="end" fontSize="6" fill="#74808d">
				N ↑
			</text>
		</svg>
	);
}
// Keep intermediate empty input while editing a controlled numeric value.
function ModelNumberInput({
	value,
	onNumberChange,
	...props
}: Omit<NumberInputProps, "value" | "onChange"> & {
	value: number;
	onNumberChange: (value: number) => void;
}) {
	const [draft, setDraft] = useState<string | number>(value);
	useEffect(() => setDraft(value), [value]);
	return (
		<NumberInput
			{...props}
			value={draft}
			onChange={(next) => {
				setDraft(next);
				if (typeof next === "number") onNumberChange(next);
			}}
			onInput={(event) => {
				// Keep whole-value edits (including paste after an external slider/batch update)
				// synchronized even when the formatted input retains an older numeric cache.
				const text = event.currentTarget.value.replace(/[%×\s]/g, "");
				if (!/^-?\d+(?:\.\d+)?$/.test(text)) return;
				const parsed = Number(text);
				const bounded = Math.max(
					typeof props.min === "number" ? props.min : -Infinity,
					Math.min(
						typeof props.max === "number" ? props.max : Infinity,
						parsed,
					),
				);
				setDraft(bounded);
				onNumberChange(bounded);
			}}
			onBlur={(event) => {
				const parsed = Number.parseFloat(event.currentTarget.value);
				if (!Number.isFinite(parsed)) {
					setDraft(value);
					return;
				}
				const bounded = Math.max(
					typeof props.min === "number" ? props.min : -Infinity,
					Math.min(
						typeof props.max === "number" ? props.max : Infinity,
						parsed,
					),
				);
				setDraft(bounded);
				onNumberChange(bounded);
			}}
		/>
	);
}
export function App() {
	const canvas = useRef<HTMLDivElement>(null),
		viewer = useRef<ReturnType<typeof createViewer> | null>(null);
	const [meta, setMeta] = useState<Meta | null>(null),
		[metrics, setMetrics] = useState<Metrics | null>(null),
		[probe, setProbe] = useState<Probe | null>(null);
	const [loading, setLoading] = useState(true),
		[error, setError] = useState(""),
		[scenario, setScenario] = useState("reference");
	const [cut, setCut] = useState([100, 144, 52]),
		[hidden, setHidden] = useState<number[]>([]),
		[bearing, setBearing] = useState(0);
	const [surface, setSurface] = useState(true),
		[points, setPoints] = useState(false),
		[faults, setFaults] = useState(true),
		[difference, setDifference] = useState(false);
	const [exaggeration, setExaggeration] = useState(3),
		[info, setInfo] = useState(false),
		[exporting, setExporting] = useState(false),
		[panel, setPanel] = useState(() => window.innerWidth > 650);
	const [showDiagram, setShowDiagram] = useState(false);
	const [rocksVisible, setRocksVisible] = useState(true);
	const [surfaceOpacity, setSurfaceOpacity] = useState(65);
	const [horizontalReversed, setHorizontalReversed] = useState(false);
	const [volumeCut, setVolumeCut] = useState(false);
	const [cutReversed, setCutReversed] = useState(false);
	const [opacity, setOpacity] = useState<number[]>([]);
	const [collapsedGroups, setCollapsedGroups] = useState<string[]>([]);
	const [bulkOpacity, setBulkOpacity] = useState(90);
	const uniformOpacity =
		opacity.length > 0 && opacity.every((a) => a === opacity[0])
			? opacity[0]
			: null;
	function changeBulkOpacity(value: number) {
		setBulkOpacity(value);
		setOpacity((a) => a.map(() => value));
	}

	const [marine, setMarine] = useState(false);
	const [activeMap, setActiveMap] = useState(false);
	const [activeMapOpacity, setActiveMapOpacity] = useState(100);
	const [faultLayers] = useState(["unified"]);
	const [diagram, setDiagram] = useState<Diagram | null>(null);
	const [faultPlanes, setFaultPlanes] = useState(true);
	const [filter, setFilter] = useState("");
	const [selectedFault, setSelectedFault] = useState("all"),
		[sectionRoute, setSectionRoute] = useState<number[][]>([
			[30, 160],
			[170, 130],
		]),
		[referenceSection, setReferenceSection] = useState("free"),
		[referenceOpacity, setReferenceOpacity] = useState(0);
	const [renderState, setRenderState] = useState<RenderState | null>(null);
	useEffect(() => {
		const engine = createViewer(canvas.current!, {
			onReady: (m: Meta) => {
				setMeta(m);
				setCollapsedGroups([...new Set(m.rockBodies.map((b) => b.group))]);
				setOpacity(m.rockBodies.map((u) => (u.kind === "unknown" ? 15 : 90)));
				setCut([...m.shape, m.nz]);
			},
			onMetrics: setMetrics,
			onSection: setDiagram,
			onLoading: setLoading,
			onError: setError,
			onProbe: setProbe,
			onBearing: setBearing,
			onRender: setRenderState,
			onFaultSelect: (id: string) => {
				setSelectedFault(id);
			},
		});
		viewer.current = engine;
		return () => {
			engine.dispose();
			viewer.current = null;
		};
	}, []);
	useEffect(() => {
		viewer.current?.update({
			volumeCut,
			cutReversed,
			cut,
			hidden,
			surface,
			points,
			faults,
			faultPlanes,
			difference,
			exaggeration,
			panel,
			showDiagram,
			rocksVisible,
			surfaceOpacity,
			horizontalReversed,
			opacity,
			marine,
			selectedFault,
			faultLayers,
			activeMap,
			activeMapOpacity,
			sectionRoute,
			referenceSection,
			referenceOpacity,
		});
	}, [
		volumeCut,
		cutReversed,
		cut,
		hidden,
		surface,
		points,
		faults,
		faultPlanes,
		difference,
		exaggeration,
		panel,
		showDiagram,
		rocksVisible,
		surfaceOpacity,
		horizontalReversed,
		opacity,
		marine,
		selectedFault,
		faultLayers,
		activeMap,
		activeMapOpacity,
		sectionRoute,
		referenceSection,
		referenceOpacity,
	]);
	useEffect(() => {
		(window as unknown as { __awaji: unknown }).__awaji = renderState
			? {
					ready: true,
					...renderState,
					surfaceAgreement: metrics?.surface_agreement,
				}
			: null;
	}, [renderState, metrics]);
	function select(value: string) {
		setScenario(value);
		viewer.current?.selectScenario(value);
	}
	function reset() {
		setVolumeCut(false);
		setCutReversed(false);
		setHorizontalReversed(false);
		if (meta) setCut([...meta.shape, meta.nz]);
		setProbe(null);
	}

	async function download() {
		setExporting(true);
		try {
			await viewer.current?.exportGLB();
		} catch (e) {
			setError(String(e));
		} finally {
			setExporting(false);
		}
	}
	const max = meta ? [...meta.shape, meta.nz] : [100, 144, 52];
	function changeAxis(axis: number, value: number) {
		setCut((v) => v.map((n, i) => (i === axis ? value : n)));
	}

	const selected = meta?.units.find((u) => u.id === probe?.unit);
	const selectedBody = meta?.rockBodies.find((b) => b.id === probe?.body);
	return (
		<div className="app-shell">
			<header className="app-header">
				<Group gap={9}>
					<IconCube size={20} stroke={1.5} color="#647386" />
					<Text fw={600} size="md">
						淡路島
					</Text>
					<Divider orientation="vertical" h={17} />
					<Text size="xs" c="dimmed">
						地質モデル
					</Text>
				</Group>

				<Group gap={3}>
					<Tooltip label="出典・推定条件">
						<ActionIcon
							aria-label="出典・推定条件"
							variant="subtle"
							color="gray"
							onClick={() => setInfo(true)}
						>
							<IconInfoCircle size={19} />
						</ActionIcon>
					</Tooltip>
					<Button
						size="xs"
						variant="default"
						leftSection={<IconDownload size={15} />}
						loading={exporting}
						disabled={loading || !!error}
						onClick={download}
					>
						GLB
					</Button>
				</Group>
			</header>
			<main
				className={`workspace ${showDiagram ? "has-section-diagram" : ""} ${panel ? "panels-open" : ""}`}
			>
				<div className="scene" ref={canvas} aria-label="地下地質モデル" />
				<aside className="model-note" aria-label="モデルの注意事項">
					※ 地下構造は、個人が試作した仮説的なモデルです。学術的な正確さを裏付けるものではありません。
				</aside>
				{showDiagram && diagram && meta && (
					<SectionDiagram
						data={diagram}
						units={meta.rockBodies}
						exaggeration={exaggeration}
						opacity={referenceOpacity}
						right="var(--diagram-right, 14px)"
					/>
				)}
				<div className="view-tools">
					<Paper withBorder shadow="xs" p={3} radius="md">
						<Stack gap={2}>
							<Tool
								label="斜めから"
								onClick={() => viewer.current?.home("iso")}
							>
								<IconCube size={19} />
							</Tool>
							<Tool
								label="真上から"
								onClick={() => viewer.current?.home("top")}
							>
								<IconMap size={19} />
							</Tool>
							<Tool
								label="南から"
								onClick={() => viewer.current?.home("south")}
							>
								<span className="view-letter">S</span>
							</Tool>
							<Tool label="東から" onClick={() => viewer.current?.home("east")}>
								<span className="view-letter">E</span>
							</Tool>
							<Divider my={3} />
							<Tool
								label="全体を表示"
								onClick={() => {
									reset();
									viewer.current?.home();
								}}
							>
								<IconArrowsMaximize size={19} />
							</Tool>
						</Stack>
					</Paper>
				</div>
				<div className="scene-badges">
					{scenario !== "reference" && (
						<Badge variant="white" color="gray" size="sm" radius="sm">
							検証用：{names[scenario]}
						</Badge>
					)}
					{difference && (
						<Badge color="grape" variant="light" size="sm" radius="sm">
							シナリオ差
						</Badge>
					)}
				</div>
				<div
					className="compass"
					style={{ right: "calc(var(--scene-inset, 0px) + 18px)" }}
				>
					<svg width="42" height="55" viewBox="0 0 42 55" aria-label="北方向">
						<g transform={`translate(21 29) rotate(${bearing})`}>
							<path d="M0 -17L-5 10L0 6L5 10Z" fill="#6d7c8e" />
							<path d="M0 -17L0 6L5 10Z" fill="#b1bcc7" />
						</g>
						<text x="21" y="9" textAnchor="middle" fontSize="10" fill="#6d7c8e">
							N
						</text>
					</svg>
				</div>
				<aside
					className={`inspector ${panel ? "" : "panel-closed"}`}
					aria-label="モデル操作"
				>
					<Paper withBorder shadow="xs" className="inspector-shell">
						<div className="panel-heading inspector-heading">
							<Text size="sm" fw={600}>
								モデル操作
							</Text>
							<Tool label="操作パネルを閉じる" onClick={() => setPanel(false)}>
								<IconChevronRight size={17} />
							</Tool>
						</div>
						<div className="inspector-scroll">
							<Accordion
								multiple
								defaultValue={["rocks", "layers"]}
								transitionDuration={0}
								className="inspector-accordion"
							>
								<Accordion.Item value="rocks">
									<Accordion.Control
										aria-label="岩体の操作"
										icon={<IconLayersIntersect size={15} />}
									>
										岩体
									</Accordion.Control>
									<Accordion.Panel>
										<div className="rocks-panel">
											<div className="panel-heading">
												<div className="rock-bulk-controls">
													<Button
														size="compact-xs"
														variant={rocksVisible ? "light" : "default"}
														aria-label="岩体を一括表示"
														aria-pressed={rocksVisible}
														leftSection={
															rocksVisible ? (
																<IconEye size={13} />
															) : (
																<IconEyeOff size={13} />
															)
														}
														onClick={() => setRocksVisible(!rocksVisible)}
													>
														表示
													</Button>
													<Slider
														className="rock-bulk-slider"
														thumbLabel="岩体全体の不透明度"
														min={0}
														max={100}
														value={uniformOpacity ?? bulkOpacity}
														onChange={changeBulkOpacity}
														disabled={opacity.length === 0}
														size={3}
														label={(v) => `${v}%`}
													/>
													<Tooltip
														label={
															uniformOpacity === null
																? "個別設定が混在しています。スライダーで全岩体を同じ不透明度に設定できます。"
																: "全岩体の不透明度"
														}
														multiline
														w={220}
													>
														<Text
															className="rock-bulk-value"
															aria-label="岩体全体の不透明度の値"
															size="xs"
															c="dimmed"
														>
															{uniformOpacity === null
																? "個別"
																: `${uniformOpacity}%`}
														</Text>
													</Tooltip>
												</div>
											</div>

											<div className="unit-search">
												<TextInput
													aria-label="凡例を検索"
													placeholder="地層・岩体・記号を検索"
													value={filter}
													onChange={(e) => setFilter(e.currentTarget.value)}
													size="xs"
												/>
											</div>
											<div className="unit-list">
												<div className="alpha-heading">
													<span>地層・岩体／原記号</span>
													<span>不透明度</span>
												</div>
												{meta &&
													[...new Set(meta.rockBodies.map((b) => b.group))]
														.sort((a, b) => {
															const rank = (group: string) =>
																Math.min(
																	...meta.rockBodies
																		.filter((u) => u.group === group)
																		.map((u) =>
																			bodyAgeRank(u.source_symbol ?? ""),
																		),
																);
															return rank(a) - rank(b);
														})
														.map((group) => {
															const members = meta.rockBodies
																.filter(
																	(b) =>
																		b.group === group &&
																		Object.values(b.cell_counts).some(
																			(n) => n > 0,
																		),
																)
																.sort(
																	(a, b) =>
																		bodyAgeRank(a.source_symbol ?? "") -
																			bodyAgeRank(b.source_symbol ?? "") ||
																		Number(a.attribution === "unassigned") -
																			Number(b.attribution === "unassigned") ||
																		a.short_name.localeCompare(
																			b.short_name,
																			"ja",
																		),
																);
															const matches = members.filter((b) =>
																`${b.group} ${b.key} ${b.source_symbol} ${b.name} ${b.short_name}`
																	.toLowerCase()
																	.includes(filter.toLowerCase()),
															);
															if (!matches.length) return null;
															const colors = groupColors(members, scenario);
															const collapsed =
																!filter && collapsedGroups.includes(group);
															const visible = members.some(
																(b) => !hidden.includes(b.id),
															);
															const value = opacity[members[0].id - 1] ?? 90;
															const mixed = members.some(
																(b) => opacity[b.id - 1] !== value,
															);
															return (
																<div className="rock-group" key={group}>
																	<div className="rock-group-heading">
																		<button
																			className="rock-group-name"
																			aria-label={`${group}を${collapsed ? "展開" : "折りたたむ"}`}
																			aria-expanded={!collapsed}
																			onClick={() =>
																				setCollapsedGroups((v) =>
																					collapsed
																						? v.filter((g) => g !== group)
																						: [...v, group],
																				)
																			}
																		>
																			<span className="rock-group-chevron">
																				{collapsed ? "▸" : "▾"}
																			</span>
																			<span>{group}</span>
																			<small>{members.length}</small>
																			<span
																				className="rock-group-swatches"
																				aria-label="含まれる地質区分の色"
																			>
																				{colors.slice(0, 4).map((entry) => (
																					<Tooltip
																						key={entry.color}
																						label={`${entry.symbols.join(" / ") || "未拘束"} · 推定格子の体積順`}
																					>
																						<span
																							className="rock-group-swatch"
																							style={{
																								background: entry.color,
																							}}
																						/>
																					</Tooltip>
																				))}
																				{colors.length > 4 && (
																					<small className="rock-group-more">
																						+{colors.length - 4}
																					</small>
																				)}
																			</span>
																		</button>
																		<button
																			className="rock-group-eye"
																			aria-label={`${group}を一括${visible ? "非表示" : "表示"}`}
																			aria-pressed={visible}
																			onClick={() =>
																				setHidden((v) => {
																					const ids = new Set(
																						members.map((b) => b.id),
																					);
																					return visible
																						? [...new Set([...v, ...ids])]
																						: v.filter((id) => !ids.has(id));
																				})
																			}
																		>
																			{visible ? (
																				<IconEye size={14} />
																			) : (
																				<IconEyeOff size={14} />
																			)}
																		</button>
																		<Slider
																			thumbLabel={`${group}全体の不透明度`}
																			min={0}
																			max={100}
																			value={value}
																			onChange={(n) => {
																				const ids = new Set(
																					members.map((b) => b.id),
																				);
																				setOpacity((v) =>
																					v.map((a, i) =>
																						ids.has(i + 1) ? n : a,
																					),
																				);
																			}}
																			size={3}
																			thumbSize={8}
																			label={(v) => `${v}%`}
																		/>
																		<span className="rock-group-opacity">
																			{mixed ? "個別" : `${value}%`}
																		</span>
																	</div>
																	{!collapsed &&
																		matches.map((unit) => {
																			const i = unit.id - 1;
																			const visible = !hidden.includes(unit.id);
																			function change(value: number) {
																				setOpacity((v) =>
																					v[i] === value
																						? v
																						: v.map((a, n) =>
																								n === i ? value : a,
																							),
																				);
																			}
																			return (
																				<div
																					className={`unit-card ${visible ? "" : "is-hidden"}`}
																					key={unit.id}
																				>
																					<Tooltip
																						label={`${unit.name}${unit.attribution === "interpreted" ? " — 図幅との対応に基づく帰属推定" : ""}`}
																						position="left"
																						multiline
																						w={320}
																						openDelay={250}
																					>
																						<button
																							className="unit-row"
																							aria-label={`${unit.name}を${visible ? "非表示" : "表示"}`}
																							aria-pressed={visible}
																							onClick={() =>
																								setHidden((v) =>
																									visible
																										? [...v, unit.id]
																										: v.filter(
																												(id) => id !== unit.id,
																											),
																								)
																							}
																						>
																							<span
																								className="unit-swatch"
																								style={{
																									background: unit.color,
																								}}
																							/>
																							<span className="unit-label">
																								<code>
																									{unit.source_symbol ||
																										"未拘束"}
																								</code>
																								<span>
																									{unit.short_name}
																									{unit.attribution ===
																										"unassigned" &&
																									meta.rockBodies.some(
																										(b) =>
																											b.source_unit ===
																												unit.source_unit &&
																											b.attribution ===
																												"interpreted",
																									)
																										? "（未区分）"
																										: ""}
																								</span>
																							</span>
																							<span className="unit-space" />
																							{visible ? (
																								<IconEye size={15} />
																							) : (
																								<IconEyeOff size={15} />
																							)}
																						</button>
																					</Tooltip>
																					<div className="unit-alpha">
																						<Slider
																							thumbLabel={`${unit.name}の不透明度`}
																							min={0}
																							max={100}
																							value={opacity[i]}
																							onChange={change}
																							disabled={!visible}
																							size={3}
																							thumbSize={8}
																							color={unit.color}
																							label={(v) => `${v}%`}
																						/>
																						<ModelNumberInput
																							aria-label={`${unit.name}の不透明度（数値）`}
																							min={0}
																							max={100}
																							value={opacity[i]}
																							onNumberChange={change}
																							disabled={!visible}
																							size="xs"
																							suffix="%"
																							hideControls
																							w={50}
																						/>
																					</div>
																				</div>
																			);
																		})}
																</div>
															);
														})}
											</div>
										</div>
									</Accordion.Panel>
								</Accordion.Item>
								<Accordion.Item value="layers">
									<Accordion.Control
										aria-label="レイヤーの操作"
										icon={<IconLayersIntersect size={15} />}
									>
										レイヤー
									</Accordion.Control>
									<Accordion.Panel>
										<section
											className="control-section layer-section"
											aria-label="表示レイヤー"
										>
											{[
												{
													name: "地表地質図",
													visible: surface,
													toggle: () => setSurface(!surface),
													opacity: surfaceOpacity,
													setOpacity: setSurfaceOpacity,
												},
												{
													name: "都市圏活断層図",
													visible: activeMap,
													toggle: () => setActiveMap(!activeMap),
													opacity: activeMapOpacity,
													setOpacity: setActiveMapOpacity,
												},
											].map((layer) => (
												<div className="map-layer-row" key={layer.name}>
													<Button
														size="compact-xs"
														variant={layer.visible ? "light" : "default"}
														aria-pressed={layer.visible}
														onClick={layer.toggle}
													>
														{layer.name}
													</Button>
													<Slider
														thumbLabel={`${layer.name}の不透明度`}
														min={0}
														max={100}
														value={layer.opacity}
														onChange={layer.setOpacity}
														label={(v) => `${v}%`}
														size={3}
													/>
													<Text size="xs" c="dimmed">
														{layer.opacity}%
													</Text>
												</div>
											))}
											<div className="fault-layer-row">
												<Button
													size="compact-xs"
													variant={faults ? "light" : "default"}
													aria-pressed={faults}
													onClick={() => setFaults(!faults)}
												>
													断層線
												</Button>
												{faults && (
													<Button
														size="compact-xs"
														variant={faultPlanes ? "light" : "default"}
														disabled={
															selectedFault !== "all" &&
															!meta?.faultCatalog.find(
																(f) => f.id === selectedFault,
															)?.used_for_model &&
															!meta?.faultCatalog.find(
																(f) => f.id === selectedFault,
															)?.model_aliases?.length
														}
														title="姿勢制約・姿勢推定のある断層の地下モデルを表示"
														aria-pressed={faultPlanes}
														onClick={() => {
															setFaultPlanes((v) => !v);
														}}
													>
														地下の推定面
													</Button>
												)}
											</div>

											{faults && (
												<>
													<Select
														mx="sm"
														my={6}
														size="xs"
														aria-label="表示する断層"
														value={selectedFault}
														onChange={(v) => {
															setSelectedFault(v || "all");
														}}
														searchable
														data={[
															{ value: "all", label: "すべての断層" },
															...(meta?.faultZones || []).map((f) => ({
																value: f.id,
																label: f.name + "（全トレース）",
															})),
															...(meta?.faultCatalog || []).map((f) => ({
																value: f.id,
																label: f.name,
															})),
														]}
													/>
												</>
											)}
										</section>
									</Accordion.Panel>
								</Accordion.Item>
								<Accordion.Item value="cut">
									<Accordion.Control
										aria-label="切断・断面図の操作"
										icon={<IconBox size={15} />}
									>
										切断・断面図
									</Accordion.Control>
									<Accordion.Panel>
										<section
											className="control-section cut-section"
											aria-label="切断と断面図"
										>
											<div className="cut-toolbar">
												<Button
													size="compact-xs"
													variant={volumeCut ? "light" : "default"}
													aria-pressed={volumeCut}
													onClick={() => setVolumeCut(!volumeCut)}
												>
													鉛直切断
												</Button>
												<Button
													size="compact-xs"
													variant="default"
													aria-label="鉛直切断の側を反転"
													disabled={!volumeCut}
													onClick={() => setCutReversed(!cutReversed)}
												>
													反転
												</Button>
												<Button
													size="compact-xs"
													variant={showDiagram ? "light" : "default"}
													aria-pressed={showDiagram}
													onClick={() => setShowDiagram(!showDiagram)}
												>
													断面図
												</Button>
												<Tool label="切断をリセット" onClick={reset}>
													<IconRefresh size={15} />
												</Tool>
											</div>

											<div className="section-position">
												{(showDiagram || volumeCut) && (
													<Stack gap={6} className="reference-controls">
														<>
															<Select
																size="xs"
																aria-label="比較断面"
																value={referenceSection}
																data={[
																	{ value: "free", label: "自由断面" },
																	...(meta?.sections || []).map((s) => ({
																		value: s.id,
																		label: s.name,
																	})),
																]}
																onChange={(v) => {
																	const id = v || "free";
																	setReferenceSection(id);
																	const sec = meta?.sections.find(
																		(s) => s.id === id,
																	);
																	if (sec && meta) {
																		const [x0, x1, y0, y1] = meta.extent_xy;
																		setSectionRoute(
																			sec.route_xy.map(([x, y]) => [
																				((x - x0) / (x1 - x0)) * meta.shape[0],
																				((y - y0) / (y1 - y0)) * meta.shape[1],
																			]),
																		);
																		setReferenceOpacity(45);
																	}
																}}
															/>
															{showDiagram && referenceSection !== "free" && (
																<Group gap={9} wrap="nowrap">
																	<Text
																		size="xs"
																		style={{ whiteSpace: "nowrap" }}
																	>
																		原図
																	</Text>
																	<Slider
																		style={{ flex: 1 }}
																		thumbLabel="原断面図の不透明度"
																		min={0}
																		max={100}
																		value={referenceOpacity}
																		onChange={setReferenceOpacity}
																		size={3}
																	/>
																	<Text size="xs">{referenceOpacity}%</Text>
																</Group>
															)}
														</>
													</Stack>
												)}
												{meta && (showDiagram || volumeCut) && (
													<Plan
														stationLabels={
															meta.sections
																.find((s) => s.id === referenceSection)
																?.name.match(/[A-Z]/g) || undefined
														}
														meta={meta}
														faultLayers={faultLayers}
														activeMap={activeMap}
														activeMapOpacity={activeMapOpacity}
														faults={faults}
														selectedFault={selectedFault}
														onFaultSelect={(id) => {
															setSelectedFault(id);
														}}
														cutting={volumeCut}
														arbitrary={showDiagram || volumeCut}
														route={sectionRoute}
														onRouteChange={(route) => {
															setReferenceSection("free");
															setReferenceOpacity(0);
															setSectionRoute(route);
														}}
													/>
												)}
											</div>

											<div className="section-controls">
												<Group justify="space-between" mb={5}>
													<Text size="xs">水平切断</Text>
													<SegmentedControl
														size="xs"
														aria-label="水平切断で残す側"
														value={horizontalReversed ? "above" : "below"}
														onChange={(v) =>
															setHorizontalReversed(v === "above")
														}
														data={[
															{ value: "below", label: "下側" },
															{ value: "above", label: "上側" },
														]}
													/>
												</Group>
												<div className="axis-control">
													<span
														className="axis-letter"
														style={{ color: axisColors[2] }}
													>
														標高
													</span>
													<Slider
														thumbLabel="水平の切断位置"
														min={1}
														max={max[2]}
														value={cut[2]}
														onChange={(v) => changeAxis(2, v)}
														color="blue"
														size={3}
														thumbSize={11}
														label={(v) =>
															`${Math.round((meta?.zmin ?? -500) + ((v - 0.5) * ((meta?.zmax ?? 700) - (meta?.zmin ?? -500))) / max[2])} m`
														}
													/>
													<span className="axis-value">
														{cut[2] === max[2]
															? "全体"
															: `${Math.round((meta?.zmin ?? -500) + ((cut[2] - 0.5) * ((meta?.zmax ?? 700) - (meta?.zmin ?? -500))) / max[2])}m`}
													</span>
												</div>
											</div>
										</section>
									</Accordion.Panel>
								</Accordion.Item>
							</Accordion>
						</div>
						<div className="control-footer">
							<Divider />
							<Group px="sm" py={9} justify="space-between">
								<Text size="xs" c="dimmed">
									鉛直倍率
								</Text>
								<ModelNumberInput
									aria-label="鉛直倍率"
									size="xs"
									w={85}
									min={1}
									max={8}
									step={0.5}
									value={exaggeration}
									onNumberChange={setExaggeration}
									suffix=" ×"
								/>
							</Group>
						</div>
					</Paper>
				</aside>
				{!panel && (
					<Paper className="show-panel" withBorder shadow="xs">
						<Tool label="操作パネルを開く" onClick={() => setPanel(true)}>
							<IconChevronLeft size={20} />
						</Tool>
					</Paper>
				)}
				{probe && (
					<Paper withBorder shadow="sm" className="probe-card" p="sm">
						<Group justify="space-between" gap="xl">
							<Group gap={7}>
								<span
									className="unit-swatch"
									style={{ background: selected?.color || "#a271c6" }}
								/>
								<Text size="sm" fw={600}>
									{(selectedBody?.attribution === "interpreted"
										? selectedBody.name
										: selected?.name) ||
										(probe.observed ? "地表地質図" : "シナリオ差")}
								</Text>
							</Group>
							<ActionIcon
								size="xs"
								color="gray"
								variant="subtle"
								aria-label="照会を閉じる"
								onClick={() => setProbe(null)}
							>
								<IconX size={13} />
							</ActionIcon>
						</Group>
						<div className="probe-values">
							<div>
								<small>標高</small>
								<strong>
									{Math.round(probe.z).toLocaleString()}
									<small> m</small>
								</strong>
							</div>
							<div>
								<small>地表下</small>
								<strong>
									{Math.round(probe.depth).toLocaleString()}
									<small> m</small>
								</strong>
							</div>
						</div>
						{probe.problem && (
							<Text size="xs" c="orange" mt={7}>
								上下関係が未解決の列
							</Text>
						)}
					</Paper>
				)}
				{(loading || error) && (
					<div className="scene-status">
						<Paper withBorder shadow="sm" p="md">
							<Group gap="sm">
								{error ? (
									<IconAlertTriangle size={18} color="#c66a39" />
								) : (
									<Loader size="sm" />
								)}
								<Text size="sm">{error || "モデルを読込中"}</Text>
							</Group>
						</Paper>
					</div>
				)}
			</main>
			<footer className="statusbar">
				<Group gap={15}>
					<Text size="xs">EPSG:32653</Text>
					<Text size="xs">
						{meta
							? `${Math.round(meta.spacing_m[0])} × ${Math.round(meta.spacing_m[1])} × ${Math.round((meta.zmax - meta.zmin) / meta.nz)} m`
							: "—"}
					</Text>
					<Text size="xs">現在地質 · GemPy / 構造制約</Text>
				</Group>
				<Tooltip label="推定条件と未解決箇所を確認">
					<button onClick={() => setInfo(true)} className="quality-link">
						<IconAlertTriangle size={12} />
						構造仮説
						<Text span size="xs" c="dimmed">
							{metrics
								? ` · 区分未確定 ${(metrics.unknownFraction * 100).toFixed(1)}%`
								: ""}
						</Text>
					</button>
				</Tooltip>
			</footer>
			<Modal
				opened={info}
				onClose={() => setInfo(false)}
				title="出典・推定条件"
				closeButtonProps={{ "aria-label": "出典を閉じる" }}
				size="lg"
				centered
			>
				<Stack gap="md">
					<Stack gap="xs">
						<Text size="sm">
							産総研地質調査総合センター・国土地理院・地震調査研究推進本部・海上保安庁の資料をもとに、Watson496が加工・推定したモデルです。各機関の公式モデルではありません。
						</Text>
						<a href={dataUrl("ATTRIBUTION.md")} target="_blank" rel="noreferrer">データの出典・加工内容・利用条件</a>
						<a href={dataUrl("LICENSE-SOFTWARE.txt")} target="_blank" rel="noreferrer">ソフトウェアのライセンス（MIT）</a>
						<a href={dataUrl("THIRD_PARTY_NOTICES.txt")} target="_blank" rel="noreferrer">依存ライブラリのライセンス</a>
					</Stack>
					<div>
						<Text size="sm" fw={600} mb={6}>
							岩体名の帰属
						</Text>
						<Text size="sm" c="dimmed">
							原凡例と岩体のIDを分離しています。岩体名は5万分の1図幅との対応に基づく推定です。
							一致する露頭から同じ地質区分の内部をたどり、断層を横切らない経路で2km以内を対象にします。
							別の岩体への経路との差が200m以下、または支持が届かない部分は「未区分」です。
							距離は便宜的な仮定で、帰属の境界は実測された地質境界ではありません。
							「未区分」は岩体名の未確定、「未拘束」は地質区分自体の未確定を表します。
						</Text>
					</div>
					<div>
						<Text size="sm" fw={600} mb={6}>
							検証用表示
						</Text>
						<Select
							label="検証用モデル"
							aria-label="検証用モデル"
							size="xs"
							value={scenario}
							onChange={(value) => {
								if (value) select(value);
							}}
							allowDeselect={false}
							data={[
								{ value: "reference", label: "採用モデル（通常表示）" },
								{ value: "shallow", label: "比較 A" },
								{ value: "deep", label: "比較 B" },
							]}
						/>
						<Text size="xs" c="dimmed" mt={6} mb={10}>
							同じ資料に対して推定上の仮定を変えた比較です。表示深度の切り替えではありません。
							比較A／採用モデル／比較Bの仮想基底深度は0.65／1／1.4倍、
							下位構造を制約から広げる距離の上限は1／2／3kmです。
							被覆層の厚さと、資料で決めきれない断層の姿勢候補も変えています。
							比較モデルとの違いは信頼区間や精度を表しません。
						</Text>
						<Group gap={6}>
							{[
								{
									name: "入力点",
									on: points,
									toggle: () => setPoints(!points),
								},
								{
									name: "海域基盤面",
									on: marine,
									toggle: () => setMarine(!marine),
								},
								{
									name: "シナリオ差",
									on: difference,
									toggle: () => setDifference(!difference),
								},
							].map((item) => (
								<Button
									key={item.name}
									size="compact-xs"
									variant={item.on ? "light" : "default"}
									aria-pressed={item.on}
									onClick={item.toggle}
								>
									{item.name}
								</Button>
							))}
						</Group>
					</div>
					<Text size="sm">
						シームレス地質図V2の原記号・岩相・色を保持した地下モデルです。断層を横切る補間を遮断し、堆積体の共通境界とその内部の岩相を分けて推定しています。同年代の岩相を上下の層序へ並べてはいません。
					</Text>
					<Text size="sm">
						地表の接触点・既知の単元ラベルを入力し、堆積層の接触では位置照合した走向傾斜を使います。基底深度・側方境界の傾斜・地下の内部点は事前仮定です。明石・洲本の原断面から座標化した岩相点と地質境界点を制約に使用します。陸域の計算下端は標高−500mですが、岩体は地表から連続して推定し、断面の読み取り点から離れた部分は外挿として区別します。沖積層・段丘堆積物・盛土と下位構造を分けて推定し、下位構造に有限厚さの被覆層を重ねています。被覆地点の地表ラベルを古い岩相の否定証拠にはしません。露出・断面制約から断層を越えずに移送できる範囲と候補の競合を評価し、距離や閾値は推定上の仮定として扱います。鉛直50m格子では数m厚の層を解像できず、地表の薄層は最上セルで表現されます。ボーリング柱状図は未導入です。現在の地質を推定し、地震一回分の変位や任意の累積変位は加えません。
					</Text>
					{metrics?.section_reproduction?.map((section) => (
						<div key={section.section_id}>
							<Text size="sm" fw={500}>
								原断面の境界との距離（制約再現）
							</Text>
							<Text size="xs" c="dimmed">
								{section.section_id}:{" "}
								{section.boundary_fit
									.map((p) =>
										p.distance_to_matching_model_interface_m === null
											? "境界なし"
											: `${Math.round(p.distance_to_matching_model_interface_m)} m`,
									)
									.join(" / ")}
								。独立検証ではありません。
							</Text>
						</div>
					))}
					<Table fz="xs">
						<Table.Thead>
							<Table.Tr>
								<Table.Th>原記号</Table.Th>
								<Table.Th>基底深度の仮定</Table.Th>
								<Table.Th>境界条件の再現</Table.Th>
							</Table.Tr>
						</Table.Thead>
						<Table.Tbody>
							{meta?.units
								.filter((u) => u.kind === "geological")
								.map((u) => {
									const i = u.id - 1,
										row = metrics?.surface_confusion_matrix_actual_rows[i],
										n = row?.reduce((a, b) => a + b, 0) || 0,
										prior = metrics?.audit.find(
											(a) => a.source_unit_id === u.id,
										)?.depth_prior_m;
									return (
										<Table.Tr key={u.id}>
											<Table.Td>
												<Tooltip label={u.name}>
													<span>{u.key}</span>
												</Tooltip>
											</Table.Td>
											<Table.Td>{prior?.toLocaleString()} m</Table.Td>
											<Table.Td>
												{row && n ? `${((row[i] / n) * 100).toFixed(1)}%` : "—"}
											</Table.Td>
										</Table.Tr>
									);
								})}
						</Table.Tbody>
					</Table>
					<Text size="sm">
						地表ラベルは既知の境界条件として課しており、その再現性は独立した検証ではありません。
					</Text>
					{metrics && (
						<Text size="sm" c="dimmed">
							区分未確定の領域：{(metrics.unknownFraction * 100).toFixed(1)}
							%。断面の近傍窓（水平500m・入力標高幅）の外にある割合は
							{((metrics.sectionExtrapolationFraction ?? 0) * 100).toFixed(1)}
							%です。この窓は信頼度ではなく、岩体を切り落とすためには使いません。対応する原単元の制約に到達できない場所や、距離・候補の競合で採用条件を満たさない被覆下は、灰色の区分未確定域として残します。
						</Text>
					)}

					{metrics?.fault_conditioning?.substrate && (
						<div>
							<Text size="sm" fw={500}>
								被覆層下の区分未確定
							</Text>
							<Table fz="xs">
								<Table.Thead>
									<Table.Tr>
										<Table.Th>地表の原区分</Table.Th>
										<Table.Th>下位の未確定率</Table.Th>
									</Table.Tr>
								</Table.Thead>
								<Table.Tbody>
									{Object.entries(
										metrics.fault_conditioning.substrate.under_cover,
									).map(([symbol, row]) => (
										<Table.Tr key={symbol}>
											<Table.Td>{symbol}</Table.Td>
											<Table.Td>
												{row.unknown_fraction === null
													? "—"
													: `${(row.unknown_fraction * 100).toFixed(1)}%`}
											</Table.Td>
										</Table.Tr>
									))}
								</Table.Tbody>
							</Table>
							<Text size="xs" c="dimmed">
								被覆層の下位から計算下端まで。分類できた領域も構造の外挿であり、観測済みを意味しません。
							</Text>
						</div>
					)}
					<Text size="sm">
						地表・地下・凡例の色と原記号は同じ対応です。地表の原区分と地下の推定分布は一致しない箇所があります。地形・岩体の表示補間は推定精度を上げるものではありません。
					</Text>
					<Divider />
					<Stack gap={6}>
						<Text size="sm">
							断層線は出典をまたいで重複区間を整理し、詳細な線を優先して黒線に統一しています。地下断面の破線は近隣資料からの姿勢推定を含みます。姿勢が未解決の断層を鉛直面にはしません。都市圏活断層図は国土地理院の原タイルを地表に重ねます。「地下の推定面」は断層線を傾斜方向に延長した仮定を含み、実測された地下形状ではありません。どちらも深部の外挿を含みます。海域の音響基盤深度等深線を構造制約に使用しています。海域の岩相モデルは未拘束で、断層面の範囲と陸域の岩相推定範囲は異なります。
						</Text>
						<a
							href="https://www.jishin.go.jp/evaluation/long_term_evaluation/regional_evaluation/kinki-detail/"
							target="_blank"
							rel="noreferrer"
						>
							地震本部・近畿地域の活断層評価（2026）
						</a>
						<a
							href="https://www.jishin.go.jp/main/chousa/17dec_chi_shikoku/shikoku_01_mtl.pdf"
							target="_blank"
							rel="noreferrer"
						>
							中央構造線断層帯評価（2017）
						</a>
						<Text size="xs" c="dimmed">
							原資料
						</Text>
						<a
							href="https://www.gsj.jp/Map/JP/docs/5man_doc/13/13_011.htm"
							target="_blank"
							rel="noreferrer"
						>
							高橋ほか（1992）洲本地域の地質・GSJベクトル v01
						</a>
						<a
							href="https://www.gsj.jp/data/50KGM/PDF/GSJ_MAP_G050_12083_1990_D.pdf"
							target="_blank"
							rel="noreferrer"
						>
							水野ほか（1990）明石地域の地質・GSJベクトル v01
						</a>
						<a
							href="https://gbank.gsj.jp/seamless/v2/api/1.3.1/"
							target="_blank"
							rel="noreferrer"
						>
							産総研 シームレス地質図V2
						</a>
						<a
							href="https://maps.gsi.go.jp/development/ichiran.html"
							target="_blank"
							rel="noreferrer"
						>
							国土地理院 地理院タイル DEM10B
						</a>
						<a href={dataUrl(`${scenario}/metrics.json`)} target="_blank">
							計算・仮定の記録（JSON）
						</a>
						<a href={dataUrl("quality.json")} target="_blank">
							原凡例・推定範囲の検査（JSON）
						</a>
					</Stack>
				</Stack>
			</Modal>
		</div>
	);
}
