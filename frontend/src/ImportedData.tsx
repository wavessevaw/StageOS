import React from 'react';
import {tr} from './i18n';
import {ru} from './ru';
type Obj=Record<string,any>;
const labels:Record<string,string>={evidence:'Участие в постановках',source_urls:'Источники',source_positions:'Должности по источникам',source_date:'Дата сбора сведений',team_listing:'Указан в разделе команды',employment_status:'Сведения о занятости',production:'Постановка',position:'Должность / участие',section:'Раздел',url:'Источник',captured_at:'Дата сбора сведений',duration_text:'Продолжительность по источнику',age:'Возрастное ограничение',premiere:'Премьера',technical_passport_complete:'Технический паспорт заполнен',qualification:'Квалификации',specialization:'Специализация',notes:'Примечания',people:'Участники',source_text:'Сведения по источнику',source_metadata:'Сведения об источнике',production_credits:'Постановочная команда',team_listing_status:'Статус команды'};
export const importedLabel=(key:string)=>tr(labels[key]||ru(key));
const referenceKeys=new Set(['items','members','eligible','people_ids']);
export function DataValue({value,field='',resource,depth=0}:{value:any;field?:string;resource:(id:any)=>Obj|undefined;depth?:number}){
 if(value==null||value==='')return <span className="muted">—</span>;
 if(typeof value==='boolean')return <span>{tr(value?'Да':'Нет')}</span>;
 if(Array.isArray(value))return value.length?<ul className="data-list">{value.map((v,i)=><li key={i}><DataValue value={v} field={field} resource={resource} depth={depth+1}/></li>)}</ul>:<span className="muted">—</span>;
 if(typeof value==='object'&&field==='evidence')return <article className="source-entry"><strong>{value.production||tr('Постановка')}</strong>{value.position&&<p>{value.position}</p>}{value.url&&<DataValue value={value.url} resource={resource}/>}</article>;
 if(typeof value==='object'&&field==='production_credits')return <article className="source-entry"><strong>{value.position||tr('Постановочная команда')}</strong>{Array.isArray(value.people)&&value.people.length?<DataValue value={value.people} resource={resource}/>:<DataValue value={value.source_text} resource={resource}/>}</article>;
 if(typeof value==='object')return depth>=8?<pre>{JSON.stringify(value,null,2)}</pre>:<dl className="data-fields">{Object.entries(value).map(([k,v])=><div key={k}><dt>{importedLabel(k)}</dt><dd><DataValue value={v} field={k} resource={resource} depth={depth+1}/></dd></div>)}</dl>;
 if(typeof value==='number')return <span>{referenceKeys.has(field)?(resource(value)?.name||value):value}</span>;
 if(typeof value==='string'&&/^https?:\/\//i.test(value))return <a href={value} target="_blank" rel="noopener noreferrer">{value}</a>;
 return <span className="data-text">{tr(value==='credits'?'Постановочная команда':value==='roles'?'Исполнители':ru(value))}</span>;
}
const metadata=new Set(['evidence','source_urls','source_positions','source_date','team_listing','employment_status','source_metadata','production_credits']);
export const isImportedMetadata=(key:string)=>metadata.has(key);
export function ImportedData({data,resource}:{data:Obj;resource:(id:any)=>Obj|undefined}){
 const present=Object.entries(data).filter(([k,v])=>metadata.has(k)&&v!=null&&(!Array.isArray(v)||v.length));
 if(!present.length)return null;
 return <section className="panel imported-data" aria-label={tr('Сведения из источников')}><h3>{tr('Сведения из источников')}</h3>{data.team_listing===false&&<p className="import-notice">{tr('Участие в спектакле не подтверждает текущую работу в театре. Проверьте сведения о сотруднике.')}</p>}{data.source_metadata?.technical_passport_complete===false&&<p className="import-notice">{tr('Составы и технический паспорт требуют заполнения. Время подготовки и технические требования пока не определены.')}</p>}{present.map(([k,v])=>k==='evidence'||k==='production_credits'?<details key={k}><summary>{importedLabel(k)} <span>{Array.isArray(v)?v.length:''}</span></summary><DataValue value={v} field={k} resource={resource}/></details>:<div className="import-field" key={k}><small>{importedLabel(k)}</small><DataValue value={v} field={k} resource={resource}/></div>)}</section>;
}
