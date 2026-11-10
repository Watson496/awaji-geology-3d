import {
	Slider as MantineSlider,
	type SliderProps,
	Tooltip,
} from "@mantine/core";

// Keep Mantine's hover, drag and keyboard visibility handling, but render the
// value outside the inspector's stacking contexts and overflow boundaries.
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
