import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { MantineProvider, createTheme } from "@mantine/core";
import "@mantine/core/styles.css";
import "./styles.css";
import { App } from "./App";

const theme = createTheme({
	primaryColor: "blue",
	defaultRadius: "sm",
	fontFamily:
		'-apple-system, BlinkMacSystemFont, "Hiragino Kaku Gothic ProN", sans-serif',
	fontSizes: { xs: "11px", sm: "12px", md: "13px", lg: "15px" },
	headings: { fontWeight: "600" },
});
createRoot(document.getElementById("root")!).render(
	<StrictMode>
		<MantineProvider theme={theme} forceColorScheme="light">
			<App />
		</MantineProvider>
	</StrictMode>,
);
