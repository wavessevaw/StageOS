import React,{useState} from 'react';
import {tr} from './i18n';
type Obj=Record<string,any>;
export function Tunnel({state,onUpdate}:{state:Obj,onUpdate:(s:Obj)=>void}){
 const [token,setToken]=useState(''),[remember,setRemember]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const t=state.tunnel||{};
 const labels:Obj={stopped:'Интернет-туннель остановлен',installing:'Загрузка ngrok…',starting:'Проверяем внешний адрес…',connected:'Интернет-туннель подключён',disconnected:'Нет связи через интернет-туннель',error:'Ошибка интернет-туннеля'};
 async function action(action:string){setBusy(true);setError('');const submitted=action==='start'?token:'';if(action==='start')setToken('');try{
  const r=await fetch('/api/connection/tunnel',{method:'POST',headers:{'Content-Type':'application/json','X-StageOS-Token':sessionStorage.getItem('stageos-token')||''},body:JSON.stringify({action,...(action==='start'?{authtoken:submitted,remember}:{})})});
  const value=await r.json();if(!r.ok)throw Error(typeof value.detail==='string'?value.detail:'Проверьте настройки подключения');onUpdate(value);
 }catch(e:any){setError(e.message)}finally{setBusy(false)}}
 const allowed=state.can_manage_tunnel&&!busy&&state.running;
 const active=['starting','connected','disconnected'].includes(t.phase);
 return <div className="server-tunnel"><h3>{tr('Доступ через Интернет')}</h3>
 <p>{tr('ngrok выступает посредником между клиентами и вашим ПК. База остаётся на компьютере сервера. Нужен аккаунт ngrok и его Authtoken.')}</p>
 <p><a href="https://dashboard.ngrok.com/get-started/your-authtoken" target="_blank" rel="noreferrer">{tr('Открыть аккаунт ngrok')}</a></p>
 <strong role="status">{tr(labels[t.phase]||labels.stopped)}</strong>
 {t.checked_at&&<small className="server-checked">{tr('Последняя проверка')}: {new Date(t.checked_at).toLocaleTimeString()}</small>}
 {t.error&&<p className="server-warning">{tr(t.error)}</p>}{error&&<p role="alert" className="error-banner">{tr(error)}</p>}
 {!state.can_manage_tunnel&&<p className="muted">{tr('Управление туннелем: войдите администратором на компьютере сервера.')}</p>}
 {!t.installed?<><p className="muted">{tr('Кнопка загрузит проверенную версию ngrok с официального сайта. Установка выполняется один раз.')}</p><button type="button" disabled={!allowed||!t.can_install} onClick={()=>action('install')}>{tr(busy?'Загрузка ngrok…':'Установить ngrok')}</button></>:<>
 <label className="field"><span>{tr('Authtoken ngrok')}</span><input type="password" autoComplete="new-password" spellCheck={false} value={token} disabled={!allowed||active} onChange={e=>setToken(e.target.value)} placeholder={tr(t.saved_key?'Сохранённый ключ будет использован':'Вставьте ключ из аккаунта ngrok')}/></label>
 <label className="tunnel-remember"><input type="checkbox" checked={remember} disabled={!allowed||active||!state.windows} onChange={e=>setRemember(e.target.checked)}/><span>{tr('Сохранить ключ в Windows для текущего пользователя')}</span></label>
 <div className="server-actions"><button type="button" disabled={!allowed||active||(!token&&!t.saved_key)} onClick={()=>action('start')}>{tr(busy?'Выполняем…':'Запустить интернет-туннель')}</button><button type="button" disabled={!allowed||t.phase==='stopped'} onClick={()=>action('stop')}>{tr('Остановить туннель')}</button>{t.saved_key&&<button type="button" disabled={!allowed} onClick={()=>action('forget')}>{tr('Удалить сохранённый ключ')}</button>}</div>
 </>}
 {t.verified&&t.phase==='connected'&&t.url&&<div className="connection-receipt"><strong>{tr('Проверенный внешний адрес')}</strong><code>{t.url}</code><p>{tr('Передайте этот адрес, код подключения сервера и личный логин пользователям StageOS.')}</p></div>}
 <p className="muted">{tr('После перезапуска приложения запустите туннель снова. Сервер и ПК должны оставаться включёнными. Доступность и лимиты зависят от аккаунта ngrok.')}</p>
 </div>;
}
