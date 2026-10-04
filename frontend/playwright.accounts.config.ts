import {defineConfig} from '@playwright/test';
import base from './playwright.config';
import {tmpdir} from 'node:os';import {join} from 'node:path';
export default defineConfig({...base,testDir:'./e2e-accounts',use:{...base.use,baseURL:'http://127.0.0.1:8882'},reporter:[['list'],['json',{outputFile:'../accounts-ui-results.json'}]],webServer:{...(base.webServer as any),command:(base.webServer as any).command.replace('--test-no-auth ','').replace('--port 8877','--port 8882'),url:'http://127.0.0.1:8882/api/auth/theatres',env:{...(base.webServer as any).env,STAGEOS_ENABLE_DEMO:'0',STAGEOS_HOME:join(tmpdir(),'stageos-accounts-ui-'+Date.now())}}});
