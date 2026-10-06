import React,{lazy,Suspense} from 'react';
import {createRoot} from 'react-dom/client';
import {Recovery} from './Recovery';
import {tr} from './i18n';
import './style.css';
const initialToken = new URLSearchParams(location.search).get("token");
if (initialToken) {
  sessionStorage.setItem("stageos-token", initialToken);
  history.replaceState({}, "", location.pathname);
}

class LoadError extends React.Component<{children:React.ReactNode},{failed:boolean}>{
 state={failed:false};
 static getDerivedStateFromError(){return {failed:true}}
 render(){return this.state.failed?<div className="loading" role="alert"><p>{tr('Не удалось загрузить страницу. Проверьте связь и обновите её.')}</p><button onClick={()=>location.reload()}>{tr('Повторить')}</button></div>:this.props.children}
}
const Desktop=lazy(()=>import('./main'));
const Mobile=lazy(()=>import('./MobileApp').then(module=>({default:module.MobileApp})));
const personalMobile=location.pathname.startsWith('/mobile')||(!sessionStorage.getItem('stageos-token')&&(window.matchMedia('(max-width: 760px)').matches||/Android|iPhone|iPad|iPod/i.test(navigator.userAgent)));
createRoot(document.getElementById('root')!).render(<Recovery><LoadError><Suspense fallback={<div className="loading" role="status">{tr('Загрузка StageOS…')}</div>}>{personalMobile?<Mobile/>:<Desktop/>}</Suspense></LoadError></Recovery>);
