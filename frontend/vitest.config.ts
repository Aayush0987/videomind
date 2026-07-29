import { defineConfig } from "vitest/config";

// Vitest owns the pure lib/ unit tests; Playwright owns *.spec.ts. Keeping the
// globs disjoint stops each runner from picking up the other's files.
export default defineConfig({
  test: {
    include: ["tests/**/*.test.ts"],
    environment: "node",
  },
  resolve: {
    alias: { "@": new URL("./", import.meta.url).pathname },
  },
});
