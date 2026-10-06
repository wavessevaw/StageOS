import React from 'react';
import {tr} from './i18n';
type Obj=Record<string,any>;
export function ImportedEvent({plan,resources,onPassport}:{plan:Obj,resources:Obj[],onPassport:(id:number)=>void}){
 const production=plan.production_passport,data=production?.data||{};
 const names=(ids:number[])=>ids.map(id=>resources.find(r=>r.id===id)?.name).filter(Boolean).join(', ');
 return <section className="imported-event"><p className="notice">{tr('Показ добавлен из афиши. Производственный план ещё не заполнен.')}</p>
 {production&&<><h3>{tr('Постановка')}: {production.name}</h3>{data.genre&&<p>{data.genre}</p>}
 <p>{plan.estimated_end?tr('Продолжительность пока не указана. Окончание в календаре условное.'):tr('Продолжительность из паспорта')+': '+plan.duration_minutes+' '+tr('мин')}</p>
 <button onClick={()=>onPassport(production.id)}>{tr('Открыть паспорт постановки')}</button>
 <details open><summary>{tr('Допущенные актёры из паспорта')}</summary><p className="muted">{tr('Это допуск к ролям. Исполнители на эту дату пока не назначены.')}</p>
 {(data.roles||[]).length?<div className="imported-cast">{data.roles.map((role:Obj,i:number)=><div key={i}><b>{role.role}</b><span>{names(role.eligible||[])||tr('Допуск не указан')}</span></div>)}</div>:<p>{tr('Роли в паспорте пока не заполнены.')}</p>}</details>
 <details><summary>{tr('Ответственные и состав постановки')}</summary><div className="imported-cast">{Object.entries(data.responsibles||{}).map(([dept,value])=>{const ids=Array.isArray(value)?value:[value];return names(ids as number[])?<div key={dept}><b>{tr(dept)}</b><span>{names(ids as number[])}</span></div>:null})}{Object.entries(data.groups||{}).map(([dept,ids])=>Array.isArray(ids)&&ids.length?<div key={dept}><b>{tr(dept)}</b><span>{names(ids)}</span></div>:null)}</div></details></>}
 <p>{tr('Нажмите «Заполнить производственный план»: форма использует сохранённый паспорт и допущенный состав этой постановки.')}</p></section>;
}
