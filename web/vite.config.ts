import { defineConfig } from "vite"
import { tanstackStart } from "@tanstack/react-start/plugin/vite"
import viteReact from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"

// Backend phân tích là FastAPI (`uv run rinng web`, cổng 8000). Khi dev, Vite chuyển /api sang đó.
// `pnpm build` ra bản SPA tĩnh trong dist/client để FastAPI phục vụ luôn.
const config = defineConfig({
  resolve: { tsconfigPaths: true },
  server: {
    proxy: { "/api": process.env.RINNG_API ?? "http://127.0.0.1:8000" },
  },
  plugins: [tailwindcss(), tanstackStart({ spa: { enabled: true } }), viteReact()],
})

export default config
