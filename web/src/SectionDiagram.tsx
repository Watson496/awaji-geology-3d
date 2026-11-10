import { dataUrl } from "./data-url.js";
import type { CSSProperties } from "react";
export type Diagram = {
	length: number;
	stations: number[];
	bottom: number;
	top: number;
	meshes: { unit: number; triangles: number[] }[];
	faults: { dashed: boolean; points: number[][] }[];
	reference?: { image: string; image_range_m: number[]; name: string };
};
export function SectionDiagram({
	data,
	units,
	exaggeration,
	opacity,
	right,
}: {
	data: Diagram;
	units: { id: number; color: string; kind: string }[];
	exaggeration: number;
	opacity: number;
	right: CSSProperties["right"];
}) {
	const top = data.reference?.image_range_m[3] ?? data.top;
	const bottom = data.reference?.image_range_m[2] ?? data.bottom;
	const verticalExaggeration = data.reference ? 1 : exaggeration;
	const scale = Math.min(
		880 / Math.max(data.length, 1),
		185 / ((top - bottom) * verticalExaggeration),
	);
	const x0 = 62 + (880 - data.length * scale) / 2,
		y0 = 28 + (185 - (top - bottom) * scale * verticalExaggeration) / 2;
	const x = (distance: number) => x0 + distance * scale,
		y = (z: number) => y0 + (top - z) * scale * verticalExaggeration;
	const ref = data.reference;
	return (
		<div className="section-diagram" style={{ right } as CSSProperties}>
			<svg
				viewBox="0 0 1000 265"
				aria-label="距離と標高の地質断面図"
				role="img"
			>
				<defs>
					<pattern
						id="unconstrained-hatch"
						width="7"
						height="7"
						patternUnits="userSpaceOnUse"
					>
						<rect width="7" height="7" fill="#f3f4f5" />
						<path
							d="M-2 2L2 -2M0 7L7 0M5 9L9 5"
							stroke="#d2d7db"
							strokeWidth=".6"
						/>
					</pattern>
				</defs>
				<text x="18" y="16" fill="#647181" fontSize="11">
					標高 m
				</text>
				{[bottom, 0, 500]
					.filter((z) => z >= bottom && z <= top)
					.map((z) => (
						<g key={z}>
							<path
								d={`M${x0 - 5} ${y(z)}H${x(data.length)}`}
								stroke={z === 0 ? "#8e9aa5" : "#e0e5e9"}
								strokeDasharray={z === 0 ? undefined : "3 4"}
							/>
							<text
								x={x0 - 10}
								y={y(z) + 4}
								textAnchor="end"
								fontSize="11"
								fill="#647181"
							>
								{z}
							</text>
						</g>
					))}
				{data.meshes.map((mesh, i) => {
					const unit = units.find((u) => u.id === mesh.unit);
					const paths = [];
					for (let k = 0; k < mesh.triangles.length; k += 6) {
						const p = mesh.triangles;
						paths.push(
							`M${x(p[k]).toFixed(2)} ${y(p[k + 1]).toFixed(2)}L${x(p[k + 2]).toFixed(2)} ${y(p[k + 3]).toFixed(2)}L${x(p[k + 4]).toFixed(2)} ${y(p[k + 5]).toFixed(2)}Z`,
						);
					}
					return (
						<path
							key={i}
							d={paths.join("")}
							fill={
								unit?.kind === "unknown"
									? "url(#unconstrained-hatch)"
									: unit?.color || "#ddd"
							}
						/>
					);
				})}
				{ref && opacity > 0 && (
					<image
						href={dataUrl(ref.image)}
						x={x(0)}
						y={y(ref.image_range_m[3])}
						width={data.length * scale}
						height={
							(ref.image_range_m[3] - ref.image_range_m[2]) *
							scale *
							verticalExaggeration
						}
						preserveAspectRatio="none"
						opacity={opacity / 100}
					/>
				)}
				{data.faults.map((f, i) => (
					<path
						key={i}
						d={`M${x(f.points[0][0])} ${y(f.points[0][1])}L${x(f.points[1][0])} ${y(f.points[1][1])}`}
						stroke="#111"
						strokeWidth="1.8"
						strokeDasharray={f.dashed ? "4 3" : undefined}
						fill="none"
					/>
				))}
				<path
					d={`M${x0} ${y0}V${y(bottom)}H${x(data.length)}`}
					stroke="#8896a3"
					fill="none"
				/>
				{[0, 0.25, 0.5, 0.75, 1].map((t) => (
					<g key={t}>
						<path
							d={`M${x(data.length * t)} ${y(bottom)}v5`}
							stroke="#8896a3"
						/>
						<text
							x={x(data.length * t)}
							y={y(bottom) + 19}
							textAnchor="middle"
							fontSize="11"
							fill="#647181"
						>
							{((data.length * t) / 1000).toFixed(1)}
						</text>
					</g>
				))}

				{ref?.name.match(/[A-Z]/g)?.length === data.stations.length &&
					data.stations.slice(1, -1).map((distance, i) => (
						<g key={i}>
							<path
								d={`M${x(distance)} ${y0}V${y(bottom)}`}
								stroke="#b8c4ce"
								strokeDasharray="2 4"
								fill="none"
							/>
							<text
								x={x(distance)}
								y="15"
								textAnchor="middle"
								fontSize="12"
								fill="#46586c"
							>
								{ref.name.match(/[A-Z]/g)?.[i + 1]}
							</text>
						</g>
					))}
				<text x={x(0)} y="15" fontSize="12" fill="#46586c">
					{ref?.name.match(/[A-Z]/g)?.[0] || "A"}
				</text>
				<text
					x={x(data.length)}
					y="15"
					fontSize="12"
					textAnchor="end"
					fill="#46586c"
				>
					{ref?.name.match(/[A-Z]/g)?.at(-1) || "B"}
				</text>
				<text x="948" y="249" textAnchor="end" fontSize="11" fill="#647181">
					距離 km · 鉛直 {verticalExaggeration}×
				</text>
				<rect
					x="24"
					y="236"
					width="16"
					height="10"
					fill="url(#unconstrained-hatch)"
				/>
				<text x="46" y="246" fontSize="11" fill="#647181">
					地質区分未確定
				</text>
				{ref && (
					<text x="225" y="246" fontSize="11" fill="#647181">
						{ref.name}
					</text>
				)}
			</svg>
		</div>
	);
}
