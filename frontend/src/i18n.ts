import {useSyncExternalStore} from 'react';
import {english} from './en';
export type Language='ru'|'en';
let language:Language=localStorage.getItem('stageos-language')==='en'?'en':'ru';
const listeners=new Set<()=>void>();
export const getLanguage=()=>language;
export function setLanguage(value:Language){language=value;localStorage.setItem('stageos-language',value);document.documentElement.lang=value;for(const listener of listeners)listener();}
export function useLanguage(){return useSyncExternalStore(callback=>{listeners.add(callback);return()=>listeners.delete(callback)},getLanguage);}
export function tr<T>(value:T):T {
 if(language==='ru'||typeof value!=='string')return value;
 if(english[value])return english[value] as T;
 const trimmed=value.trim();if(english[trimmed])return value.replace(trimmed,english[trimmed]) as T;
 return value;
}
export function message(value:string):string {
 if(language==='ru')return value;
 const exact=tr(value);if(exact!==value)return exact;
 let out=value;
 for(const [source,target] of Object.entries(english).filter(([s])=>s.length>=5).sort((a,b)=>b[0].length-a[0].length))
   out=out.split(source).join(target);
 return out;
}
