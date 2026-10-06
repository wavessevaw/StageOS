// Keep the server connection code in this tab, never in links or external requests.
export async function apiFetch(input:RequestInfo|URL,init?:RequestInit):Promise<Response> {
  const url=new URL(input instanceof Request?input.url:String(input),location.href);
  if(url.origin!==location.origin || !url.pathname.startsWith('/api/'))return fetch(input,init);
  const code=sessionStorage.getItem('stageos-web-code');
  const headers=new Headers(input instanceof Request?input.headers:undefined);
  new Headers(init?.headers).forEach((value,key)=>headers.set(key,value));
  if(code)headers.set('X-StageOS-Code',code);
  headers.set('ngrok-skip-browser-warning','stageos');
  const disconnected=(codeRequired=false)=>{
    sessionStorage.setItem('stageos-relogin-required','1');
    if(codeRequired)sessionStorage.removeItem('stageos-web-code');
    window.dispatchEvent(new CustomEvent('stageos-server-disconnected',{detail:{codeRequired}}));
  };
  const timeout=code && url.pathname==='/api/auth/session'?AbortSignal.timeout(8000):undefined;
  try {
    const response=await fetch(input,{...init,headers,...(timeout?{signal:init?.signal?AbortSignal.any([init.signal,timeout]):timeout}:{})});
    if(response.headers.get('X-StageOS-Disconnected')==='1' || (code && [502,503,504].includes(response.status))) {
      disconnected(response.status===403);
      // A tunnel's error page may be HTML; return a consistent API error.
      if(code && [502,503,504].includes(response.status))return new Response(JSON.stringify({detail:'Связь с сервером потеряна. Переподключитесь и войдите снова.'}),{status:503,headers:{'Content-Type':'application/json','X-StageOS-Disconnected':'1'}});
    }
    return response;
  } catch(error) {
    if(code)disconnected();
    if(code && error instanceof Error)Object.assign(error,{disconnected:true});
    throw error;
  }
}
