import { defineConfig } from 'vitest/config';
export default defineConfig({test:{include:['plugins/**/*.test.ts'],environment:'happy-dom',testTimeout:15000}});
