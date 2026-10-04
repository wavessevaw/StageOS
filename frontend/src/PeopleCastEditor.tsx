import { tr } from "./i18n";
import React, { useState } from "react";
type O = Record<string, any>;
export default function PeopleCastEditor({department, casts, resources, onChange}: {
  department:string; casts:Record<string,number[]>; resources:O[];
  onChange:(casts:Record<string,number[]>)=>void;
}) {
  const [pending,setPending]=useState<Record<string,boolean>>({});
  const people=resources.filter(r=>r.kind==="Person" && !r.data?.retired && (r.data?.qualification || []).includes(department));
  return <section className="panel"><h3>{tr(department)}</h3><div className="check-grid">
    {(["A","B"] as const).map(cast=><section key={cast} aria-label={`${department} · ${cast === "A" ? "Первый" : "Второй"} состав`}>
      <h4>{tr(cast === "A" ? "Первый состав" : "Второй состав")}</h4>
      {(casts[cast] || []).map((id,index)=><div className="toolbar" key={index}>
        <label className="field"><span>{tr("Сотрудник ")}{tr(index+1)}</span><select aria-label={`${department} ${cast} сотрудник ${index+1}`} value={id} onChange={e=>onChange({...casts,[cast]:casts[cast].map((v,i)=>i===index?+e.target.value:v)})}>
          {people.filter(r=>r.id===id || !casts[cast].includes(r.id)).map(r=><option key={r.id} value={r.id}>{r.name}{tr(r.data?.specialization ? ` · ${r.data.specialization}` : "")}</option>)}
        </select></label>
        <button type="button" onClick={()=>onChange({...casts,[cast]:casts[cast].filter((_,i)=>i!==index)})}>{tr("Убрать")}</button>
      </div>)}
      {pending[cast] && <label className="field"><span>{tr("Добавить сотрудника")}</span><select aria-label={`${department} ${cast} добавить сотрудника`} value="" onChange={e=>{if(e.target.value){onChange({...casts,[cast]:[...(casts[cast] || []),+e.target.value]});setPending({...pending,[cast]:false});}}}>
        <option value="">{tr("Выберите сотрудника")}</option>
        {people.filter(r=>!(casts[cast] || []).includes(r.id)).map(r=><option key={r.id} value={r.id}>{r.name}{tr(r.data?.specialization ? ` · ${r.data.specialization}` : "")}</option>)}
      </select></label>}
      <button type="button" disabled={people.every(r=>(casts[cast] || []).includes(r.id))} onClick={()=>setPending({...pending,[cast]:true})}>{tr("Добавить сотрудника")}</button>
      {tr(!people.length && <p className="muted">{tr("Сначала добавьте сотрудников подразделения в разделе «Сотрудники».")}</p>)}
    </section>)}
  </div></section>;
}
