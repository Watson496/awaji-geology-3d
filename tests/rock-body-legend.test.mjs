import test from "node:test";
import assert from "node:assert/strict";
import { bodyAgeRank, groupColors } from "../web/src/rock-body-legend.js";

test("凡例は若い年代から順に並べ、年代不明を最後に置く", () => {
	const expected = [
		"H2_or",
		"H_sad",
		"Q32-33_std",
		"Q31_std",
		"Q1-21_sn",
		"N3_sns",
		"Pg2_sbs",
		"K2-Pg12_mgmpe_lks",
		"K22_soc",
		"K21_pam_a",
		"K12_pbd_a",
		"unconstrained",
	];
	assert.deepEqual(
		[...expected].reverse().sort((a, b) => bodyAgeRank(a) - bodyAgeRank(b)),
		expected,
	);
});

test("グループの配色は岩体をまたぐ同色を統合し、選択したシナリオの体積を使う", () => {
	const members = [
		{
			color: "#ff0000",
			source_symbol: "A",
			cell_counts: { reference: 10, deep: 50 },
		},
		{
			color: "#ff0000",
			source_symbol: "A",
			cell_counts: { reference: 15, deep: 50 },
		},
		{
			color: "#0000ff",
			source_symbol: "B",
			cell_counts: { reference: 30, deep: 10 },
		},
	];
	assert.deepEqual(groupColors(members, "reference"), [
		{ color: "#0000ff", cells: 30, symbols: ["B"] },
		{ color: "#ff0000", cells: 25, symbols: ["A"] },
	]);
	assert.equal(groupColors(members, "deep")[0].color, "#ff0000");
});
