import React,{useState,useEffect} from 'react';
import {tr} from './i18n';
type Row={name:string;usage:{people:string[];productions:string[];events:string[]}};
export default function QualificationManager({api,onClose}:{api:(path:string,method?:string,body?:any)=>Promise<any>;onClose:()=>void}){
 const [rows,setRows]=useState<Row[]>([]),[name,setName]=useState(''),[busy,setBusy]=useState(true),[error,setError]=useState('');
 const reload=()=>api('/settings/qualifications').then(setRows);
 useEffect(()=>{reload().catch(e=>setError(e.message)).finally(()=>setBusy(false));},[]);
 async function save(names:string[]){setBusy(true);setError('');try{await api('/settings/qualifications','PUT',{names});await reload();setName('');}catch(e:any){setError(e.message);}finally{setBusy(false);}}
 return <div className="overlay" style={{zIndex:200}}><section className="modal" role="dialog" aria-modal="true" aria-label={tr('Управление квалификациями')}>
 <div className="modal-head"><h2>{tr('Управление квалификациями')}</h2><button disabled={busy} onClick={onClose}>{tr('Закрыть')}</button></div>
 <div className="modal-body"><p>{tr('Квалификации определяют, на какие обязанности можно назначить сотрудника.')}</p>
 {error&&<p role="alert">{error}</p>}
 <form className="row" onSubmit={e=>{e.preventDefault();save([...rows.map(r=>r.name),name.trim()]);}}><label className="field"><span>{tr('Новая квалификация')}</span><input required maxLength={80} value={name} onChange={e=>setName(e.target.value)}/></label><button className="primary" disabled={busy||!name.trim()}>{tr('Добавить')}</button></form>
 {rows.map(row=>{const used=Object.values(row.usage).some(x=>x.length);return <div className="personline" key={row.name}><span><b>{tr(row.name)}</b><small>{tr('Сотрудников')}: {row.usage.people.length} · {tr('Постановок')}: {row.usage.productions.length} · {tr('Событий')}: {row.usage.events.length}</small>{used&&<details><summary>{tr('Где используется')}</summary>{Object.values(row.usage).flat().join(', ')}</details>}</span><button disabled={busy||used} title={used?tr('Сначала измените назначения этой квалификации'):''} onClick={()=>save(rows.filter(r=>r.name!==row.name).map(r=>r.name))}>{tr('Удалить')}</button></div>})}
 </div></section></div>;
}
