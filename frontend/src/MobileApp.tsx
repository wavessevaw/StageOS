import React,{useEffect,useState} from 'react';
import {apiFetch} from './NetworkFetch';
import {tr,useLanguage,setLanguage} from './i18n';
import {ru} from './ru';
type Obj=Record<string,any>;
const dayKey=(d:Date)=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
function monday(){const d=new Date();d.setHours(0,0,0,0);d.setDate(d.getDate()-(d.getDay()+6)%7);return dayKey(d)}
async function mobileApi(path:string,method='GET',body?:Obj){
  const response=await apiFetch('/api/mobile'+path,{method,signal:AbortSignal.timeout(10000),headers:{'Content-Type':'application/json','X-StageOS-Token':sessionStorage.getItem('stageos-token')||''},body:body?JSON.stringify(body):undefined});
  let data:Obj;try{data=await response.json()}catch{throw Object.assign(Error(tr('Связь с сервером потеряна. Войдите снова после восстановления подключения.')),{status:response.status})}
  if(!response.ok)throw Object.assign(Error(tr(typeof data.detail==='string'?data.detail:'Проверьте поля формы')),{status:response.status});
  return data;
}
export function MobileApp(){
  const language=useLanguage();const locale=language==='en'?'en-GB':'ru-RU';
  const [session,setSession]=useState<Obj|null>(null),[schedule,setSchedule]=useState<Obj|null>(null),[start,setStart]=useState(monday),[form,setForm]=useState({login:'',password:''}),[error,setError]=useState(''),[busy,setBusy]=useState(false),[ready,setReady]=useState(false);
  function disconnect(message=tr('Связь с сервером потеряна. Войдите снова после восстановления подключения.')){sessionStorage.setItem('stageos-mobile-relogin','1');setSession(null);setSchedule(null);setForm(f=>({...f,password:''}));setError(message);setReady(true)}
  useEffect(()=>{let active=true;(async()=>{try{if(!sessionStorage.getItem('stageos-mobile-relogin')){const s=await mobileApi('/session');if(active)setSession(s)}}catch(e:any){if(active&&e.status!==401)setError(e.message)}finally{if(active)setReady(true)}})();return()=>{active=false}},[]);
  useEffect(()=>{if(!session)return;let active=true,pending=false;const poll=async()=>{if(pending||document.hidden)return;pending=true;try{const data=await mobileApi('/schedule?start='+start);if(active){setSchedule(data);setError('')}}catch(e:any){if(active&&!e.transient)disconnect(e.status===401?tr('Сеанс завершён. Войдите снова.'):e.message)}finally{pending=false}};void poll();const resumed=()=>{if(!document.hidden)void poll()};document.addEventListener("visibilitychange",resumed);const id=setInterval(poll,30000);return()=>{active=false;clearInterval(id);document.removeEventListener("visibilitychange",resumed)}},[session,start]);
  useEffect(()=>{const lost=()=>disconnect();window.addEventListener('stageos-server-disconnected',lost);return()=>window.removeEventListener('stageos-server-disconnected',lost)},[]);
  async function login(e:React.FormEvent){e.preventDefault();setBusy(true);setError('');try{await mobileApi('/login','POST',form);const s=await mobileApi('/session');sessionStorage.removeItem('stageos-mobile-relogin');setSession(s);setForm(f=>({...f,password:''}));setStart(monday())}catch(e:any){setError(e.message)}finally{setBusy(false)}}
  async function logout(){setBusy(true);try{await mobileApi('/logout','POST')}catch{}finally{disconnect('');setBusy(false)}}
  const label=(d:Date)=>d.toLocaleDateString(locale,{day:'numeric',month:'long'});
  const clock=(d:Date)=>d.toLocaleTimeString(locale,{hour:'2-digit',minute:'2-digit'});
  const week=new Date(start+'T00:00:00');const days=Array.from({length:7},(_,i)=>{const d=new Date(week);d.setDate(d.getDate()+i);return d});
  const shift=(offset:number)=>{const next=new Date(week);next.setDate(next.getDate()+offset);setSchedule(null);setStart(dayKey(next))};
  return <div className="mobile-app"><header className="mobile-brand"><img src="/stageos-icon.svg" alt=""/><strong>StageOS</strong><span>{tr('Личное расписание')}</span><select aria-label={tr('Язык приложения')} value={language} onChange={e=>setLanguage(e.target.value as 'ru'|'en')}><option value="ru">RU</option><option value="en">EN</option></select></header>
    {!session?<main className="mobile-login"><h1>{tr('Вход в личное расписание')}</h1><p>{tr('Войдите своим логином и паролем. Здесь показана только ваша занятость.')}</p>{error&&<p className="error-banner" role="alert">{error}</p>}{!ready?<p>{tr('Проверяем подключение…')}</p>:<form onSubmit={login}><label className="field"><span>{tr('Логин')}</span><input required maxLength={120} autoComplete="username" value={form.login} onChange={e=>setForm({...form,login:e.target.value})}/></label><label className="field"><span>{tr('Пароль')}</span><input type="password" required maxLength={256} autoComplete="current-password" value={form.password} onChange={e=>setForm({...form,password:e.target.value})}/></label><button className="primary" disabled={busy}>{tr(busy?'Выполняем…':'Войти')}</button></form>}</main>:<main>
      <section className="mobile-person"><div><h1>{schedule?.employee?.name||session.employee?.name||session.name}</h1><p>{session.theatre}</p></div><button disabled={busy} onClick={logout}>{tr('Выйти')}</button></section>
      {(session.link_error||schedule?.link_error)?<p className="notice" role="status">{tr(schedule?.link_error||session.link_error)}</p>:<>
      <section className="mobile-week"><button aria-label={tr('Предыдущая неделя')} onClick={()=>shift(-7)}>‹</button><div><strong>{label(days[0])} — {label(days[6])}</strong><button onClick={()=>setStart(monday())}>{tr('Текущая неделя')}</button></div><button aria-label={tr('Следующая неделя')} onClick={()=>shift(7)}>›</button></section>
      {!schedule?<p role="status">{tr('Загружаем вашу занятость…')}</p>:<div className="mobile-days">{days.map(day=>{const next=new Date(day);next.setDate(next.getDate()+1);const items=schedule.items.filter((item:Obj)=>new Date(item.start)<next&&new Date(item.end)>day);return <section className={'mobile-day '+(dayKey(day)===dayKey(new Date())?'today':'')} key={dayKey(day)}><h2>{day.toLocaleDateString(locale,{weekday:'long',day:'numeric',month:'short'})}{dayKey(day)===dayKey(new Date())&&<small>{tr('Сегодня')}</small>}</h2>{!items.length?<p className="mobile-free">{tr('Нет назначений')}</p>:items.map((item:Obj)=><article className="mobile-event" key={item.id}><div className="mobile-time">{clock(new Date(Math.max(+day,+new Date(item.start))))} — {+new Date(item.end)>=+next?'24:00':clock(new Date(item.end))}</div><h3>{item.title}</h3><p>{tr(ru(item.kind))}{item.venue&&' · '+item.venue}</p>{item.role&&<p>{tr('Ваша роль')}: {item.role}</p>}{item.event_start&&<p className="mobile-curtain">{tr('Начало события')}: {clock(new Date(item.event_start))} · {tr('Окончание')}: {clock(new Date(item.event_end))}</p>}<small>{tr(ru(item.status))}</small></article>)}</section>})}</div>}
      <p className="mobile-note">{tr('Показана ваша занятость по назначениям сервера. Обед и другие перерывы могут входить в общий интервал вызова.')}</p></>}
    </main>}<footer>{tr('База на сервере')} · StageOS 1.0.15</footer></div>;
}

