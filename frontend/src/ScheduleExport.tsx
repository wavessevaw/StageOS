import {apiFetch} from "./NetworkFetch";
import { tr } from "./i18n";
import React, {useState} from 'react';
import { saveFile } from './saveFile';
export default function ScheduleExport({date,filters,onClose,locale='ru'}:{date:string;filters:Record<string,any>;onClose:()=>void;locale?:string}){
  const [start,setStart]=useState(date),[end,setEnd]=useState(date),[format,setFormat]=useState('pdf'),[people,setPeople]=useState(true),[tasks,setTasks]=useState(true),[notes,setNotes]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState(''),[result,setResult]=useState('');
  return <div className="overlay" onClick={onClose}><section className="modal" role="dialog" aria-label={tr("Экспорт расписания")} onClick={e=>e.stopPropagation()}>
    <div className="modal-head"><h2>{tr("Экспорт расписания")}</h2><button onClick={onClose}>{tr("Закрыть")}</button></div>
    <div className="modal-body"><p>{tr("Таблица по датам, площадкам и помещениям. Используются текущие фильтры календаря.")}</p>
      <div className="check-grid"><label className="field"><span>{tr("Начало периода")}</span><input type="date" value={start} onChange={e=>setStart(e.target.value)}/></label>
      <label className="field"><span>{tr("Конец периода")}</span><input type="date" value={end} onChange={e=>setEnd(e.target.value)}/></label>
      <label className="field"><span>{tr("Формат файла")}</span><select aria-label={tr("Формат файла")} value={format} onChange={e=>setFormat(e.target.value)}><option value="pdf">{tr("PDF")}</option><option value="png">{tr("PNG")}</option></select></label></div>
      <p className="muted">{tr("До 31 дня. Многостраничный PNG сохраняется архивом изображений. PDF содержит все страницы в одном файле.")}</p>
      <div className="toolbar"><label><input type="checkbox" checked={people} onChange={e=>setPeople(e.target.checked)}/>{tr(" Вызовы сотрудников")}</label><label><input type="checkbox" checked={tasks} onChange={e=>setTasks(e.target.checked)}/>{tr(" Производственный план")}</label><label><input type="checkbox" checked={notes} onChange={e=>setNotes(e.target.checked)}/>{tr(" Примечания")}</label></div>
      {tr(error && <p role="alert">{tr(error)}</p>)}
      {result && <p role="status">{result}</p>}
      <button className="primary" disabled={busy || !start || !end || end<start} onClick={async()=>{
        setBusy(true);setError('');setResult('');try{
          const params=new URLSearchParams(Object.entries({...filters,start,end,format,locale,include_people:people,include_tasks:tasks,include_notes:notes}).filter(([,v])=>v!=='' && v!=null).map(([k,v])=>[k,String(v)]));
          const response=await apiFetch('/api/schedule/export?'+params,{headers:{'X-StageOS-Token':sessionStorage.getItem('stageos-token') || ''}});
          if(!response.ok){const data=await response.json();throw new Error(typeof data.detail==='string'?data.detail:'Не удалось экспортировать расписание');}
          const filename=response.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)?.[1] || `StageOS-schedule.${format}`;
          setResult(await saveFile(await response.blob(), filename));
        }catch(e:any){setError(e.message);}finally{setBusy(false);}
      }}>{tr("Скачать расписание")}</button>
    </div>
  </section></div>;
}
