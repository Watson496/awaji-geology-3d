import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { cpSync } from "node:fs";
import { resolve } from "node:path";

export default defineConfig({
	root: "web",
	base: process.env.BASE_PATH || "/",
	publicDir: false,
	plugins: [
		react(),
		{
			name: "model-data",
			writeBundle() {
				cpSync(resolve("web/data"), resolve("dist/data"), { recursive: true });
			},
		},
	],
	server: { host: "127.0.0.1", port: 4173, strictPort: true },
	preview: { host: "127.0.0.1", port: 4173, strictPort: true },
	build: { outDir: "../dist", emptyOutDir: true, chunkSizeWarningLimit: 1200 },
});
