import {defineConfig} from '@playwright/test';
import base from './playwright.config';
import {tmpdir} from 'node:os';import {join} from 'node:path';
const home=join(tmpdir(),'stageos-network-ui-'+Date.now());
const server=(port:number,suffix:string)=>({...(base.webServer as any),command:(base.webServer as any).command.replace('--test-no-auth ','').replace('--port 8877','--port '+port),url:`http://127.0.0.1:${port}/api/connection`,env:{...(base.webServer as any).env,STAGEOS_ENABLE_DEMO:'0',STAGEOS_HOME:home+'-'+suffix}});
export default defineConfig({...base,testDir:'./e2e-network',use:{...base.use,baseURL:'http://127.0.0.1:8884'},reporter:[['list'],['json',{outputFile:'../network-ui-results.json'}]],webServer:[server(8883,'host'),server(8884,'client')]});
