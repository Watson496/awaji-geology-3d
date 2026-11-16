// 出典の年代範囲が重なるため、表示順を地層の上下関係として使わない。
const ageOrder = [
	"H2_or",
	"H_sad",
	"Q32-33_std",
	"Q31_std",
	"Q1-21_sn",
	"N3_",
	"Pg2_",
	"K2-Pg12_",
	"K22_",
	"K21_",
	"K12_",
];

export function bodyAgeRank(symbol = "") {
	const rank = ageOrder.findIndex((prefix) => symbol?.startsWith(prefix));
	return rank < 0 ? ageOrder.length : rank;
}

/**
 * @param {{color:string, source_symbol:string|null, cell_counts:Record<string,number>}[]} members
 * @param {string} scenario
 * @returns {{color:string, cells:number, symbols:string[]}[]}
 */
export function groupColors(members, scenario) {
	const colors = new Map();
	for (const body of members) {
		const entry = colors.get(body.color) ?? {
			color: body.color,
			cells: 0,
			symbols: [],
		};
		entry.cells += body.cell_counts[scenario] ?? 0;
		if (body.source_symbol && !entry.symbols.includes(body.source_symbol))
			entry.symbols.push(body.source_symbol);
		colors.set(body.color, entry);
	}
	return [...colors.values()].sort(
		(a, b) => b.cells - a.cells || a.color.localeCompare(b.color),
	);
}
