// Never replay writes: a missing response does not prove a failed save.
let authenticated=false,mobile=false,recovering=false,generation=0;
const message='Связь с сервером временно потеряна. Пробуем восстановить подключение.';
function state(value:boolean){recovering=value;window.dispatchEvent(new CustomEvent('stageos-network-state',{detail:{reconnecting:value}}))}
export const networkRecovering=()=>recovering;
function finish(codeRequired=false){authenticated=false;generation++;state(false);sessionStorage.setItem(mobile?'stageos-mobile-relogin':'stageos-relogin-required','1');if(codeRequired)sessionStorage.removeItem('stageos-web-code');window.dispatchEvent(new CustomEvent('stageos-server-disconnected',{detail:{codeRequired}}))}
function headersFor(input?:HeadersInit){const headers=new Headers(input);const code=sessionStorage.getItem('stageos-web-code');if(code)headers.set('X-StageOS-Code',code);headers.set('ngrok-skip-browser-warning','stageos');headers.set('X-StageOS-Token',sessionStorage.getItem('stageos-token')||'');return headers}
function transient(){return Object.assign(Error(message),{transient:true})}
function recover(){
 if(recovering||!authenticated)return;
 state(true);const current=++generation,deadline=Date.now()+30000;
 void(async()=>{
  while(current===generation&&Date.now()<deadline){
   try{
    const response=await fetch(mobile?'/api/mobile/session':'/api/auth/session',{headers:headersFor(),signal:AbortSignal.timeout(Math.min(5000,Math.max(1,deadline-Date.now())))});
    if(current!==generation)return;
    if(response.status===401){finish();return}
    if(response.headers.get('X-StageOS-Disconnected')==='1'&&response.status===403){finish(true);return}
    if(response.ok){const data=await response.json();if(mobile?!!data.login:!!data.user){generation++;state(false);return}}
   }catch{}
   await new Promise(r=>setTimeout(r,Math.min(3000,Math.max(0,deadline-Date.now()))));
  }
  if(current===generation)finish();
 })();
}
export async function apiFetch(input:RequestInfo|URL,init?:RequestInit):Promise<Response>{
 const url=new URL(input instanceof Request?input.url:String(input),location.href);
 if(url.origin!==location.origin||!url.pathname.startsWith('/api/'))return fetch(input,init);
 const headers=headersFor(input instanceof Request?input.headers:undefined);new Headers(init?.headers).forEach((value,key)=>headers.set(key,value));
 const timeout=AbortSignal.timeout(url.pathname.endsWith('/session')?8000:120000),signal=init?.signal?AbortSignal.any([init.signal,timeout]):timeout;
 if(recovering&&!url.pathname.endsWith('/logout'))throw transient();
 let response:Response;
 try{response=await fetch(input,{...init,headers,signal})}catch{recover();throw transient()}
 if(response.status===403&&response.headers.get('X-StageOS-Disconnected')==='1'){finish(true);return response}
 if(([502,503,504].includes(response.status)&&!url.pathname.startsWith('/api/settings/llm/'))||response.headers.get('X-StageOS-Reconnecting')==='1'){recover();throw transient()}
 if(authenticated&&response.status===401)finish();
 if(response.ok&&['/api/auth/login','/api/auth/session','/api/mobile/login','/api/mobile/session'].includes(url.pathname)){authenticated=true;mobile=url.pathname.startsWith('/api/mobile/')}
 if(response.ok&&url.pathname.endsWith('/logout')){authenticated=false;generation++;state(false)}
 return response;
}
