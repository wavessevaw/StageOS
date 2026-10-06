import React, {useState} from 'react';
import {tr} from './i18n';

export function ApprovalActions({plan,busy,approve,reject}:{plan:Record<string,any>;busy:boolean;approve:(body:{reason:string;force:boolean})=>void;reject:()=>void}) {
  const [reason,setReason]=useState(plan.request.override_reason || '');
  const [force,setForce]=useState(!!plan.request.force);
  const critical=plan.conflicts.some((c:Record<string,any>)=>c.severity==='CRITICAL');
  const serious=plan.conflicts.some((c:Record<string,any>)=>['ERROR','CRITICAL'].includes(c.severity));
  return <div className="approval-actions">
    {(serious || force) && <label className="field"><span>{tr('Причина согласования конфликтного назначения')}</span><textarea value={reason} onChange={e=>setReason(e.target.value)} maxLength={2000} placeholder={tr('Обязательная причина, не менее 12 символов')}/></label>}
    {critical && <label className="row"><input type="checkbox" checked={force} onChange={e=>setForce(e.target.checked)} disabled={busy}/>{tr('Подтвердить с сохранением критических конфликтов')}</label>}
    <button disabled={busy} onClick={reject}>{tr('Отклонить')}</button>
    <button className="primary" disabled={busy || (critical && !force) || ((serious || force) && reason.trim().length<12)} onClick={()=>approve({reason,force})}>{tr('Согласовать')}</button>
  </div>;
}
