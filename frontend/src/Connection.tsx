import {apiFetch} from "./NetworkFetch";
import React,{useEffect,useRef,useState} from 'react';
import {tr,message} from './i18n';
import {Tunnel} from './Tunnel';
type Obj=Record<string,any>;
const headers=()=>({'Content-Type':'application/json','X-StageOS-Token':sessionStorage.getItem('stageos-token')||''});
async function request(path:string,method='GET',body?:Obj){
 const r=await apiFetch('/api/connection'+path,{method,headers:headers(),body:body?JSON.stringify(body):undefined});
 if(r.status===404)return null;
 if(r.status===403 && r.headers.get('X-StageOS-Web')==='1' && method==='GET' && path==='')return {mode:'web',enabled:true,running:true,address:location.origin};
 const value=await r.json();if(!r.ok)throw Error(typeof value.detail==='string'?value.detail:tr('Проверьте настройки подключения'));return value;
}
export async function connectionApi(method='GET',body?:Obj){return request('',method,body)}
export function DatabaseLocation(){
 const [mode,setMode]=useState('unknown');
 useEffect(()=>{let active=true;const poll=async()=>{try{const s=await connectionApi();if(active)setMode(s?.mode||'local')}catch{if(active)setMode('unavailable')}};void poll();const id=setInterval(poll,3000);return()=>{active=false;clearInterval(id)}},[]);
 const labels:Obj={local:'Локальная база данных',client:'База на сервере',web:'База на сервере',server:'Общая база · этот сервер',unknown:'Проверяем подключение…',unavailable:'Нет связи с ядром'};
 return <><span className={'online'+(['unknown','unavailable'].includes(mode)?' connection-unknown':'')}/><span className="database-location">{tr(labels[mode]||labels.unknown)}</span></>;
}
export function ServerIndicator(){
 const [state,setState]=useState<Obj|null>(null),[offline,setOffline]=useState(false);
 useEffect(()=>{let active=true;const poll=async()=>{try{const s=await connectionApi();if(active){setState(s);setOffline(false)}}catch{if(active)setOffline(true)}};poll();const id=setInterval(poll,3000);return()=>{active=false;clearInterval(id)}},[]);
 if(!state||(state.mode!=='server'&&state.phase!=='error'))return null;
 return <button className={'server-indicator '+(!offline&&state.running?'good':'bad')} onClick={()=>window.dispatchEvent(new Event('stageos-connection'))}><span className="server-dot"/>{tr(offline?'Нет связи с ядром':state.running?'Сервер работает':'Сервер остановлен')} · {state.port}</button>;
}
export function Connection({initial,onClose}:{initial:Obj,onClose:()=>void}){
 const [state,setState]=useState(initial),[mode,setMode]=useState(initial.phase==='error'?'server':initial.mode),[address,setAddress]=useState(initial.address||''),[code,setCode]=useState(initial.mode==='client'?initial.code:''),[port,setPort]=useState(String(initial.port||8765));
 const [changed,setChanged]=useState(false),[busy,setBusy]=useState(''),[error,setError]=useState(''),[notice,setNotice]=useState(''),[offline,setOffline]=useState(false),[checking,setChecking]=useState(false),[networkIndex,setNetworkIndex]=useState('0');
 const [localLogs,setLocalLogs]=useState<Obj[]>([]);
 const record=(message:string,level='info')=>setLocalLogs(items=>[...items.slice(-19),{time:new Date().toISOString(),message,level}]);
 async function refresh(){const s=await connectionApi();if(s){setState(s);setOffline(false)}return s}
 async function inspect(){setChecking(true);try{await request('/diagnostics');await refresh()}catch(e:any){setError(e.message)}finally{setChecking(false)}}
 useEffect(()=>{let active=true;const poll=async()=>{try{const s=await connectionApi();if(active&&s){setState(s);setOffline(false)}}catch{if(active)setOffline(true)}};const id=setInterval(poll,2000);return()=>{active=false;clearInterval(id)}},[]);
 useEffect(()=>{if(initial.mode==='server')void inspect()},[]);
 const d=state.diagnostics||{},profiles:Obj[]=d.profiles||[];
 useEffect(()=>{if(profiles.length===1&&networkIndex==='0')setNetworkIndex(String(profiles[0].index))},[JSON.stringify(profiles)]);
 async function windowsSetup(){setBusy('Подтвердите запрос Windows…');setError('');setNotice('');record('Начата настройка Windows. Ожидается подтверждение администратора.');try{
  const r=await request('/firewall','POST',{interface_index:Number(networkIndex)});setNotice(r.message);record('Настройка Windows завершена','success');await refresh();
 }catch(e:any){setError(e.message);record(e.message,'error')}finally{setBusy('')}}
 async function apply(e:React.FormEvent){e.preventDefault();setBusy(mode==='server'?'Запускаем сервер…':'Сохраняем подключение…');setError('');setNotice('');record(mode==='server'?'Запрошен запуск сервера':'Изменение подключения');try{
  const result=await connectionApi('POST',{mode,address,code,port:Number(port)});setState(result);setChanged(true);
  if(mode==='server'){setNotice(tr('Сервер запущен. Теперь проверьте настройки Windows.'));await inspect()}else location.reload();
 }catch(e:any){setError(e.message);record(e.message,'error')}finally{setBusy('')}}
 const running=!offline&&state.running;
 const status=offline?'Нет связи с ядром':state.phase==='starting'?'Запускаем сервер…':running?'Сервер работает':'Сервер остановлен';
 const selected=profiles.find(p=>String(p.index)===networkIndex);
 const fw=d.firewall==='allowed'?'Правило разрешает подключения':d.firewall==='missing'?'Правило не создано':d.firewall==='mismatch'?'Правило требует исправления':'Не проверено';
 const terminal=useRef<HTMLDivElement>(null);
 const logs=[...(state.logs||[]),...localLogs].sort((a,b)=>a.time.localeCompare(b.time)).slice(-50);
 useEffect(()=>{if(terminal.current)terminal.current.scrollTop=terminal.current.scrollHeight},[logs.length,logs.at(-1)?.time]);
 return <section className="account-panel connection-panel"><span className="eyebrow">StageOS Server</span><h1>{tr('Подключение к общей базе')}</h1>
 <div className="connection-options">{[['local','Только этот компьютер'],['server','Сервер на этом компьютере'],['client','Подключиться к серверу']].map(([key,label])=><button disabled={!!busy} key={key} className={mode===key?'active':''} onClick={()=>setMode(key)}>{tr(label)}</button>)}</div>
 {mode==='server'&&<div className={'server-live '+(running?'good':'bad')} role="status"><span className="server-dot"/><div><strong>{tr(status)}</strong><small>{tr('Порт сервера')}: {state.port} · {tr('Статус обновляется каждые 2 секунды')}</small></div></div>}
 {busy&&<p className="server-progress" role="status"><span className="server-spinner"/>{tr(busy)}</p>}
 {error&&<p role="alert" className="error-banner">{tr(error)}</p>}{state.error&&<p role="alert" className="error-banner">{state.error}</p>}
 {notice&&<p role="status" className="server-notice">{tr(notice)}</p>}
 <form onSubmit={apply}>
 {mode==='client'&&<><label className="field"><span>{tr('Адрес сервера')}</span><input required placeholder="192.168.1.10:8765" value={address} onChange={e=>setAddress(e.target.value)}/></label><label className="field"><span>{tr('Код подключения')}</span><input required autoComplete="off" value={code} onChange={e=>setCode(e.target.value)}/></label><p className="muted">{tr('Получите адрес и код у администратора. Затем войдите своим логином и паролем.')}</p><p className="muted">{tr("Адрес 192.168… работает только в одной локальной сети. Для хотспота или другой сети используйте внешний HTTPS-адрес из окна туннеля на сервере.")}</p></>}
 {mode==='server'&&<>
 <div className="server-checks"><div><small>{tr('Ответ сервера')}</small><strong>{tr(d.http_ok===true?'HTTP: отвечает':d.http_ok===false?'HTTP: нет ответа':'Не проверено')}</strong></div><div><small>{tr('Брандмауэр Windows')}</small><strong>{tr(state.firewall_state==='pending'?'Настройка выполняется…':fw)}</strong></div><div><small>{tr('Тип сети Windows')}</small><strong>{profiles.length?profiles.map(p=>`${p.interface}: ${tr(p.category==='Private'?'Частная':p.category==='Public'?'Общедоступная':'Доменная')}`).join(' · '):tr('Не проверено')}</strong></div></div>
 <button type="button" disabled={checking||!!busy} onClick={inspect}>{tr(checking?'Проверяем…':'Проверить состояние')}</button>
 {d.checked_at&&<small className="server-checked">{tr('Последняя проверка')}: {new Date(d.checked_at).toLocaleTimeString()}</small>}
 {d.detail&&<p className="muted">{tr(d.detail)}</p>}
 <label className="field"><span>{tr('Порт сервера')}</span><input type="number" required min={1024} max={65535} disabled={!!busy} value={port} onChange={e=>setPort(e.target.value)}/></label>
 {state.windows&&<div className="server-windows"><h3>{tr('Автоматическая настройка Windows')}</h3><label className="field"><span>{tr('Доверенная локальная сеть')}</span><select value={networkIndex} disabled={!!busy} onChange={e=>setNetworkIndex(e.target.value)}><option value="0">{tr('Только правило брандмауэра')}</option>{profiles.filter(p=>p.category!=='DomainAuthenticated').map(p=><option key={p.index} value={p.index}>{p.interface} — {p.name}</option>)}</select></label>
 <p className="muted">{tr('Кнопка создаст правило для StageOS. Выбранная сеть будет переведена в частную. Подтвердите запрос администратора Windows.')}</p>
 <button type="button" disabled={!!busy||!running} onClick={windowsSetup}>{tr('Настроить Windows')}</button>
 {selected?.category==='Public'&&<p className="server-warning">{tr('Сейчас выбранная сеть общедоступная: правило для частной сети в ней не действует.')}</p>}</div>}
 {running&&<div className="connection-receipt"><strong>{tr('Подключение других компьютеров')}</strong><p>{tr('Адреса подключения')}:</p>{(state.addresses||[]).filter((a:string)=>!a.includes('127.0.0.1')).map((a:string)=><code key={a}>{a}</code>)}{(state.addresses||[]).every((a:string)=>a.includes('127.0.0.1'))&&<p>{tr('Адрес локальной сети не найден. Проверьте Wi-Fi или кабель.')}</p>}<p>{tr('Код подключения')}:</p><code>{state.code}</code><small>{tr('Сетевых запросов с верным кодом')}: {state.remote_requests||0}</small>{state.last_remote&&<p>{state.last_remote.address} · {new Date(state.last_remote.time).toLocaleTimeString()}</p>}<p className="muted">{tr('Доступ с другого компьютера подтверждается только его подключением. Локальная проверка не проверяет роутер и сторонний антивирус.')}</p></div>}
 <p className="muted">{tr('Разрешите входящие подключения в брандмауэре для частной сети. Сервер работает, пока приложение открыто и компьютер не спит.')}</p>
 </>}
 {mode==='local'&&<p className="muted">{tr('Локальная база сохранена. Другие компьютеры не подключаются.')}</p>}
 <div className="server-actions"><button className="primary" disabled={!!busy}>{tr(mode==='server'?(running&&Number(port)===state.port?'Сервер запущен · проверить':'Запустить сервер'):mode==='client'?'Проверить и подключиться':'Использовать локальную базу')}</button><button type="button" disabled={!!busy} onClick={()=>changed?location.reload():onClose()}>{tr('Продолжить')}</button></div>
 </form>
 {mode==='server'&&<Tunnel state={state} onUpdate={setState}/>}
 {mode==='server'&&state.users&&<section className="server-users"><h3>{tr('Активные пользователи этого театра')}</h3><p>{tr('Пользователей')}: <strong>{state.users.online}</strong> · {tr('Сеансов')}: <strong>{state.users.sessions}</strong></p><p className="muted">{tr('Показаны сетевые сеансы с обращениями за последние 90 секунд. Выход из аккаунта завершает сеанс; закрытый клиент исчезает после периода неактивности.')}</p>{state.users.items.length?<div className="server-users-table"><table><thead><tr>{['Имя','Логин','Роль','Сеансов','Последнее обращение'].map(label=><th key={label}>{tr(label)}</th>)}</tr></thead><tbody>{state.users.items.map((user:Obj)=><tr key={user.id}><td>{user.name}</td><td>{user.login}</td><td>{tr(({admin:'Администратор',artistic_director:'Художественный руководитель',editor:'Планировщик',viewer:'Наблюдатель'} as Obj)[user.role])}</td><td>{user.sessions}</td><td>{new Date(user.last_seen).toLocaleTimeString()}</td></tr>)}</tbody></table></div>:<p>{tr('Активных сетевых пользователей нет')}</p>}</section>}
 {mode==='server'&&<div className="server-journal"><h3>{tr('Журнал сервера')}</h3><div className="server-terminal" ref={terminal} role="log" aria-label={tr('Журнал сервера')} aria-live="polite">{logs.length?logs.map((line,i)=><div key={line.time+i} className={line.level}><time>{new Date(line.time).toLocaleTimeString()}</time><span>{message(line.message)}</span></div>):<p>{tr('Ожидание действий…')}</p>}</div></div>}
 </section>;
}
