import { defineConfig } from "vitest/config";

// A separate file rather than a `test` block in vite.config.ts: vitest loads
// vite.config.ts when this is absent, which would pull in the React and PWA
// plugins to test a fetch wrapper. Nothing here renders, so `node`, not jsdom.
export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
