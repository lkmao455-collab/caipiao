/// <reference types="vitest/config" />
import { defineConfig } from "vitest/config";
import vue from "@vitejs/plugin-vue";

// 开发时前端运行在 5173，后端在 8000；用 proxy 避免 CORS 配置。
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      "/auth": "http://localhost:8000",
      "/profiles": "http://localhost:8000",
      "/generate": "http://localhost:8000",
      "/backtest": "http://localhost:8000",
      "/me": "http://localhost:8000",
      "/ws": { target: "ws://localhost:8000", ws: true },
      "/health": "http://localhost:8000",
      "/stats": "http://localhost:8000",
      "/filters": "http://localhost:8000",
    },
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.ts"],
    coverage: {
      provider: "v8",
      reporter: ["text", "html"],
      exclude: [
        "node_modules",
        "dist",
        "vite.config.ts",
        "src/main.ts",
        "src/vite-env.d.ts",
        "**/*.test.ts",
      ],
      thresholds: {
        statements: 90,
        lines: 90,
        functions: 90,
        branches: 90,
      },
    },
  },
});
