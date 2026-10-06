import React,{useState,useEffect} from 'react';
import {networkRecovering} from './NetworkFetch';
import {tr} from './i18n';
export function Recovery({children}:{children:React.ReactNode}){
 const [waiting,setWaiting]=useState(networkRecovering);
 useEffect(()=>{const change=(e:Event)=>setWaiting((e as CustomEvent).detail.reconnecting);window.addEventListener('stageos-network-state',change);return()=>window.removeEventListener('stageos-network-state',change)},[]);
 return <><div inert={waiting}>{children}</div>{waiting&&<div className="recovery-overlay" role="alertdialog" aria-modal="true" aria-label={tr('Восстанавливаем связь с сервером')}><section><h2>{tr('Восстанавливаем связь с сервером')}</h2><p>{tr('Повторяем попытки в течение 30 секунд. При восстановлении вы продолжите работу без повторного входа.')}</p><p>{tr('Ответ на последнее действие мог не прийти. После восстановления проверьте, сохранилось ли изменение.')}</p></section></div>}</>;
}
