import React,{useState,useEffect} from 'react';
import {connectionRequest} from './Connection';
import {tr} from './i18n';
type Obj=Record<string,any>;
export function AccessLog(){
 const [data,setData]=useState<Obj>({items:[]}),[error,setError]=useState(''),[notice,setNotice]=useState('');
 async function load(before?:number){try{const response=await connectionRequest('/access-log'+(before?'?before='+before:''));setData(before?{...response,items:[...data.items,...response.items]}:response);setError('')}catch(e:any){if(!e.transient)setError(e.message)}}
 useEffect(()=>{void load();const id=setInterval(()=>load(),30000);return()=>clearInterval(id)},[]);
 return <section className="access-log"><h3>{tr('История входов')}</h3><p>{tr('История сохраняется постоянно. Копия каждые 7 часов — в папке StageOS-Logs рядом с программой сервера.')}</p>{error&&<p role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}<button onClick={()=>load()}>{tr('Обновить историю')}</button><button onClick={async()=>{try{const r=await connectionRequest('/access-log/export','POST',{});setNotice(tr('Копия сохранена')+': '+r.path)}catch(e:any){setError(e.message)}}}>{tr('Сохранить копию сейчас')}</button><div className="server-users-table"><table><thead><tr>{['Дата и время','Имя','Логин','Устройство','Действие'].map(s=><th key={s}>{tr(s)}</th>)}</tr></thead><tbody>{data.items.map((row:Obj)=><tr key={row.id}><td>{new Date(row.created).toLocaleString()}</td><td>{row.name}</td><td>{row.login}</td><td>{tr(row.client)}</td><td>{tr(row.action)}</td></tr>)}</tbody></table></div>{!data.items.length&&<p>{tr('Записей пока нет')}</p>}{data.next&&<button onClick={()=>load(data.next)}>{tr('Показать более ранние записи')}</button>}</section>;
}
