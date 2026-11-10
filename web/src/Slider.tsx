import {
	Slider as MantineSlider,
	type SliderProps,
	Tooltip,
} from "@mantine/core";

// 親要素の重なり順とoverflowに遮られないよう、値ラベルをポータルに描画する。
export function Slider({ label = (value) => value, ...props }: SliderProps) {
	return (
		<MantineSlider
			{...props}
			classNames={{ label: "slider-label-anchor" }}
			label={
				label == null
					? null
					: (value) => {
							const content =
								typeof label === "function" ? label(value) : label;
							return content == null ? null : (
								<Tooltip
									label={content}
									opened
									withinPortal
									position="top"
									transitionProps={{ duration: 0 }}
								>
									<span className="slider-label-target" />
								</Tooltip>
							);
						}
			}
		/>
	);
}
