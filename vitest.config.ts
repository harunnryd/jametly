import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./app/src", import.meta.url)),
    },
  },
  test: {
    globals: true,
    environment: "happy-dom",
    setupFiles: ["./app/src/__tests__/setup.ts"],
    include: ["app/src/**/*.test.{ts,tsx}", "tests/e2e/**/*.test.{ts,tsx}"],
    coverage: {
      provider: "v8",
      include: ["app/src/**/*.{ts,tsx}"],
      exclude: ["app/src/__tests__/**", "app/src/main.tsx"],
    },
  },
});
