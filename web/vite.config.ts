import { defineConfig } from "vite"
import { tanstackStart } from "@tanstack/react-start/plugin/vite"
import viteReact from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"

// The analysis backend is FastAPI (`uv run rinng web`, port 8000). In dev, Vite proxies /api to it.
// `pnpm build` outputs a static SPA in dist/client that FastAPI serves directly.
const config = defineConfig({
  resolve: { tsconfigPaths: true },
  server: {
    proxy: { "/api": process.env.RINNG_API ?? "http://127.0.0.1:8000" },
  },
  plugins: [tailwindcss(), tanstackStart({ spa: { enabled: true } }), viteReact()],
})

export default config
