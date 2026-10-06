const palette=['#286f67','#77518b','#a55836','#3e668d','#816c2d','#974966','#446e4c','#585fa0','#996425','#486f79','#795747','#6b687b'];
export function productionColor(id:number){return palette[Math.abs(Number(id)||0)%palette.length]}
