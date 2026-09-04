import {defineConfig,devices} from '@playwright/test'
export default defineConfig({testDir:'./tests/e2e',fullyParallel:true,retries:1,use:{baseURL:'http://127.0.0.1:4173',trace:'retain-on-failure'},webServer:{command:'npm run build && npm run preview -- --host 127.0.0.1 --port 4173',port:4173,reuseExistingServer:!process.env.CI},projects:[{name:'chromium',use:{...devices['Desktop Chrome']}}]})
