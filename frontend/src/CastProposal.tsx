import React, {useState} from 'react';
import {tr} from './i18n';
type Obj = Record<string, any>;
export function CastProposal({production, api, onSaved}:{production:Obj; api:(path:string,method?:string,body?:any)=>Promise<any>; onSaved:(p:Obj)=>void}) {
  const [open,setOpen]=useState(false), [department,setDepartment]=useState('Артисты'),
    [proposal,setProposal]=useState<Obj|null>(null), [busy,setBusy]=useState(false), [error,setError]=useState('');
  const departments=[...new Set(['Артисты',...Object.keys(production.data.groups||{}),...Object.keys(production.data.crew||{}),...Object.keys(production.data.groups_casts||{}),...Object.keys(production.data.crew_casts||{})])];
  async function generate() {
    setBusy(true);setError('');setProposal(null);
    try {setProposal(await api(`/productions/${production.id}/cast-proposal`,'POST',{department}));}
    catch(e){setError((e as Error).message);}finally{setBusy(false);}
  }
  function edit(key:string,people:number[]) {setProposal(p=>p?{...p,rows:p.rows.map((r:Obj)=>r.key===key?{...r,proposed:people}:r)}:p);}
  async function save() {
    if(!proposal)return;
    setBusy(true);setError('');
    try {
      const p=await api(`/productions/${production.id}/cast-proposal/confirm`,'POST',{
        version:proposal.version,choices:proposal.rows.filter((r:Obj)=>!r.current.length).map((r:Obj)=>({key:r.key,people:r.proposed}))});
      setProposal(null);setOpen(false);onSaved(p);
    }catch(e){setError((e as Error).message);}finally{setBusy(false);}
  }
  return <section className="panel cast-proposal">
    <button onClick={()=>setOpen(!open)} disabled={busy}>{tr('Предложить составы с помощью модели')}</button>
    {open&&<>
      <h3>{tr('Первый и второй состав · предложение')}</h3>
      <p className="muted">{tr('Модель использует только допуски роли и людей, уже включённых в подразделение постановки. Заполненные составы и события календаря не меняются.')}</p>
      <label>{tr('Подразделение')}<select value={department} disabled={busy} onChange={e=>{setDepartment(e.target.value);setProposal(null);setError('');}}>{departments.map(d=><option key={d} value={d}>{tr(d)}</option>)}</select></label>
      <button onClick={generate} disabled={busy}>{tr(busy?'Модель готовит предложение…':'Получить предложение')}</button>
      {error&&<p role="alert" className="error">{tr(error)}</p>}
      {proposal&&<>
        <p className="muted">{tr('Предложение не сохранено. Занятость проверяется при назначении события.')}</p>
        {!proposal.rows.length&&<p>{tr('В этом разделе нет ролей или подразделений для заполнения.')}</p>}
        {proposal.rows.map((r:Obj)=><div key={r.key} className="cast-proposal-row">
          <h4>{r.section==='roles'?r.label:tr(r.label)} · {tr(r.cast==='A'?'Первый состав':'Второй состав')}</h4>
          {r.issue&&<p className="muted">{tr(r.issue)}</p>}
          {r.current.length?<p>{tr('Уже назначены')}: {r.current.map((id:number)=>r.candidates.find((c:Obj)=>c.id===id)?.name||String(id)).join(', ')}</p>:<>
            {r.section==='roles'?<select aria-label={`${r.label} ${r.cast}`} value={r.proposed[0]||''} disabled={busy} onChange={e=>edit(r.key,e.target.value?[Number(e.target.value)]:[])}>
              <option value="">{tr('Не назначен')}</option>{r.candidates.map((c:Obj)=><option key={c.id} value={c.id}>{c.name}</option>)}
            </select>:<><small>{tr('Количество мест')}: {r.count}</small><div className="cast-candidates">{r.candidates.map((c:Obj)=><label key={c.id}><input type="checkbox" checked={r.proposed.includes(c.id)} disabled={busy||(!r.proposed.includes(c.id)&&r.proposed.length>=r.count)} onChange={e=>edit(r.key,e.target.checked?[...r.proposed,c.id]:r.proposed.filter((id:number)=>id!==c.id))}/>{c.name}</label>)}</div></>}
          </>}
        </div>)}
        <button className="primary" disabled={busy||!proposal.rows.some((r:Obj)=>!r.current.length&&r.proposed.length)} onClick={save}>{tr('Подтвердить и сохранить составы')}</button>
        <button disabled={busy} onClick={()=>{setProposal(null);setError('');}}>{tr('Отклонить предложение')}</button>
      </>}
    </>}
  </section>;
}
