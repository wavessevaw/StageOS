import {defineConfig} from '@playwright/test';
import base from './playwright.config';
export default defineConfig({...base,testDir:'./e2e-release',use:{...base.use,baseURL:'http://127.0.0.1:8881',actionTimeout:10000},reporter:[['list'],['json',{outputFile:'../release-ui-results.json'}]],webServer:{...(base.webServer as any),command:(base.webServer as any).command.replace('--port 8877','--port 8881'),url:'http://127.0.0.1:8881/api/bootstrap',env:{...(base.webServer as any).env,STAGEOS_ENABLE_DEMO:'0'}}});
