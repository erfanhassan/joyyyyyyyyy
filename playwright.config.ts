import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  outputDir: './generated-artifacts/playwright',
  reporter: 'list',
  workers: 1,
  use: {
    baseURL: 'http://localhost:80',
    headless: true,
    launchOptions: {
      executablePath: process.env.CHROMIUM_PATH || '/repl/tools/bin/chromium',
      args: ['--no-sandbox', '--disable-dev-shm-usage'],
    },
  },
});
