import { defineConfig } from '@playwright/test';
export default defineConfig({testDir:'./tests', use:{baseURL:process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:5173', launchOptions:{args:['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream']}, permissions:['camera','microphone']}, workers:1});
