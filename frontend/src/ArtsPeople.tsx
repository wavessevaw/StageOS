import React from 'react';
import {tr} from './i18n';
type Obj=Record<string,any>;
const groups=['Артисты','Балет','Хор','Оркестр'];
export function ArtsPeople({resources,selected,onChange}:{resources:Obj[],selected:number[],onChange:(ids:number[])=>void}){
 const people=resources.filter(p=>p.kind==='Person'&&!p.data?.retired&&groups.some(g=>(p.data.qualification||[]).includes(g)));
 return <section className="arts-people"><div className="arts-head"><div><h3>{tr('Общий вызов артистов')}</h3><p>{groups.map(g=>tr(g)+' '+people.filter(p=>(p.data.qualification||[]).includes(g)).length).join(' · ')}</p></div><button disabled={!people.length} onClick={()=>onChange([...new Set([...selected,...people.map(p=>p.id)])])}>{tr('Добавить всех')}</button></div><p>{tr('Все актёры, балет, хор и оркестр. Технические службы этой кнопкой не добавляются.')}</p><details><summary>{tr('Выбрано')}: {people.filter(p=>selected.includes(p.id)).length} · {tr('Посмотреть и изменить')}</summary><div className="arts-grid">{people.map(p=><label key={p.id}><input type="checkbox" checked={selected.includes(p.id)} onChange={e=>onChange(e.target.checked?[...selected,p.id]:selected.filter(id=>id!==p.id))}/><span>{p.name}<small>{p.data.qualification.filter((g:string)=>groups.includes(g)).map(tr).join(', ')}</small></span></label>)}</div><button onClick={()=>onChange(selected.filter(id=>!people.some(p=>p.id===id)))}>{tr('Убрать общий вызов')}</button></details></section>;
}
