import { defineConfig } from 'vitest/config';
import { resolve } from 'path';

export default defineConfig({
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['tests/frontend/**/*.test.js'],
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, './src/evenezer/presentation/web/static/js'),
    },
  },
});
