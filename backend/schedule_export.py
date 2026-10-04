"""Offline, read-only schedule matrix. PDF and PNG share the same layout."""
from io import BytesIO
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from zipfile import ZipFile, ZIP_DEFLATED
from threading import RLock
from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

ASSETS=Path(__file__).parent/'assets'/'fonts'
WIDTH,HEIGHT=1190,842
FONT_LOCK=RLock()
GREEN='#285640'; INK='#203D33'; MUTED='#65746D'; LIGHT='#EFF4F0'
WORDS={
    'ru':dict(title='Расписание производства',morning='Утро / день',evening='Вечер',empty='Нет событий',page='Страница',generated='Сформировано',people='Вызовы сотрудников',notes='Примечание',tasks='Производственный план',continued='Продолжение',ready='Готово',warning='Внимание',conflict='Конфликт'),
    'en':dict(title='Production schedule',morning='Morning / afternoon',evening='Evening',empty='No events',page='Page',generated='Generated',people='Staff calls',notes='Notes',tasks='Production plan',continued='Continued',ready='Ready',warning='Warning',conflict='Conflict'),
}

CANONICAL={
 'Technical Check':('Техническая проверка','Technical check'), 'Orchestra setup':('Подготовка оркестра','Orchestra setup'),
 'RF check':('Проверка радиочастот','RF check'), 'Спектакль':('Спектакль','Performance'), 'Репетиция':('Репетиция','Rehearsal'),
 'Погрузка':('Погрузка','Loading'), 'Разгрузка':('Разгрузка','Unloading'), 'Выезд':('Выезд','Departure'), 'Возврат':('Возврат','Return'),
 'Световой монтаж':('Световой монтаж','Lighting setup'), 'Звуковой монтаж':('Звуковой монтаж','Sound setup'),
 'Видеомонтаж':('Видеомонтаж','Video setup'), 'Монтаж сцены':('Монтаж сцены','Stage setup'), 'Готовность':('Готовность','Ready call'),
 'Демонтаж':('Демонтаж','Teardown'),'Прогон':('Прогон','Run-through'),'Обед':('Обед','Lunch'),'Сбор перед спектаклем':('Сбор перед спектаклем','Pre-show call'),
 'Режиссёр':('Режиссёр','Director'),'Дирижёр':('Дирижёр','Conductor'),'Помреж':('Помреж','Stage manager'),
 'Техдир':('Техдир','Technical director'),'Звук':('Звук','Sound'),'Свет':('Свет','Lighting'),'Видео':('Видео','Video'),
 'Сцена':('Сцена','Stage'),'Хор':('Хор','Choir'),'Балет':('Балет','Ballet'),'Оркестр':('Оркестр','Orchestra'),
 'Грим':('Грим','Makeup'),'Костюм':('Костюм','Wardrobe'),'Soprano':('Сопрано','Soprano'),'Alto':('Альт','Alto'),'Tenor':('Тенор','Tenor'),'Bass':('Бас','Bass'),
}
def translated(value,locale):return CANONICAL.get(value,(value,value))[locale=='en']

def fonts():
    with FONT_LOCK:
        for name,file in [('StageRegular','DejaVuSans.ttf'),('StageBold','DejaVuSans-Bold.ttf')]:
            if name not in pdfmetrics.getRegisteredFontNames():pdfmetrics.registerFont(TTFont(name,str(ASSETS/file)))


def wrap(text,width,size=11,bold=False):
    fonts();name='StageBold' if bold else 'StageRegular'
    # Break long unspaced notes, not only words. Preserve explicit paragraphs.
    result=[]
    for paragraph in str(text).split('\n'):
        line=''
        for char in paragraph:
            if line and pdfmetrics.stringWidth(line+char,name,size)>width-4:
                split=line.rfind(' ')
                if split>0:
                    result.append(line[:split]);line=line[split+1:]+char
                else:result.append(line);line=char
            else:line+=char
        result.append(line)
    return result


def stamp(value):return datetime.fromisoformat(value) if isinstance(value,str) else value

def interval(a,b):
    a,b=stamp(a),stamp(b)
    return a.strftime('%H:%M')+' - '+b.strftime('%H:%M')+(f' ({b:%d.%m})' if b.date()!=a.date() else '')


def build_pages(events,resources,blocks,start,end,*,locale='ru',include_people=True,include_tasks=True,include_notes=True):
    words=WORDS[locale];index={r.id:r for r in resources}
    lanes={}
    def lane(rid):
        r=index[rid]
        parent=index.get(r.data.get('venue_id')) if r.kind=='Room' else None
        label=(parent.name+' / ' if parent else '')+r.name
        lanes[rid]=label
        return rid
    records=[]
    for event in events:
        rid=lane(event['venue_id'])
        plan=event['export_plan']
        lines=[(f"{interval(event['start'],event['end'])} · {event['title']}",True),
               (f"{translated(event['kind'],locale)} · {words[{'READY':'ready','WARNING':'warning','CONFLICT':'conflict'}[event['health']]]}",False)]
        if include_notes and plan.get('notes'):lines.append((words['notes']+': '+plan['notes'],False))
        if include_tasks:
            lines.append((words['tasks'],True))
            for task in sorted(plan['tasks'],key=lambda t:stamp(t['start'])):
                lines.append((interval(task['start'],task['end'])+' · '+translated(task['name'],locale),False))
        if include_people:
            lines.append((words['people'],True))
            for a in plan['assignments']:
                lines.append((stamp(a['call']).strftime('%H:%M')+' · '+a['actual']+' · '+translated(a['role'],locale),False))
        times=[stamp(event['start']),stamp(event['end'])]+[stamp(t[k]) for t in plan['tasks'] for k in ['start','end']]
        records.append((rid,min(times),max(times),lines,event))
    for block in blocks:
        r=index.get(block['resource_id'])
        if r is None:continue
        if r.kind in ['Room','Venue']:rid=lane(r.id)
        else:
            rid=-1;lanes[-1]='Отсутствия и обслуживание' if locale=='ru' else 'Absences and maintenance'
        records.append((rid,stamp(block['start']),stamp(block['end']),[(interval(block['start'],block['end'])+' · '+r.name,True),(block['label'],False)],None))
    if not lanes:lanes[0]=words['empty']
    ordered=sorted(lanes,key=lambda k:lanes[k]);pages=[]
    day=start
    generated=datetime.now(ZoneInfo('Asia/Vladivostok')).strftime('%d.%m.%Y %H:%M')
    while day<=end:
        for chunk in range(0,len(ordered),3):
            ids=ordered[chunk:chunk+3];cw=(WIDTH-48)/len(ids)
            headers=[wrap(lanes[rid],cw-24,12,True) for rid in ids]
            header_height=max(46,max(len(h) for h in headers)*15+16)
            content_top=148+header_height
            page_rows=int((771-content_top-20)/13.2)
            if page_rows<4:raise ValueError("Слишком длинное название площадки или помещения")
            for evening in [False,True]:
                lower=datetime.combine(day,datetime.min.time())+timedelta(hours=14 if evening else 0)
                upper=datetime.combine(day,datetime.min.time())+timedelta(hours=24 if evening else 14)
                columns=[]
                for rid in ids:
                    data=[]
                    for rr,a,b,lines,event in sorted(records,key=lambda r:r[1]):
                        if rr!=rid or a>=upper or b<=lower:continue
                        # The same chain may span morning and evening. Mark the repeated portion clearly.
                        if event:
                            plan=event['export_plan']
                            lines=[(f"{interval(event['start'],event['end'])} · {event['title']}",True),
                                   (translated(event['kind'],locale)+' · '+words[{'READY':'ready','WARNING':'warning','CONFLICT':'conflict'}[event['health']]],False)]
                            if stamp(event['start'])>=upper or stamp(event['end'])<=lower:lines.append(('Подготовка / производство' if locale=='ru' else 'Preparation / production',False))
                            if include_notes and plan.get('notes'):lines.append((words['notes']+': '+plan['notes'],False))
                            tasks=[t for t in plan['tasks'] if stamp(t['start'])<upper and stamp(t['end'])>lower]
                            if include_tasks and tasks:
                                lines.append((words['tasks'],True))
                                for task in sorted(tasks,key=lambda t:stamp(t['start'])):lines.append((interval(task['start'],task['end'])+' · '+translated(task['name'],locale),False))
                            staff=[p for p in plan['assignments'] if lower<=stamp(p['call'])<upper]
                            if include_people and staff:
                                lines.append((words['people'],True))
                                for person in sorted(staff,key=lambda p:stamp(p['call'])):lines.append((stamp(person['call']).strftime('%H:%M')+' · '+person['actual']+' · '+translated(person['role'],locale),False))
                        elif a<lower:data.append((words['continued'],False))
                        for text,bold in lines:
                            data.extend((piece,bold) for piece in wrap(text,cw-28,bold=bold))
                        data.append(('',False))
                    columns.append(data)
                if not any(columns) and evening:continue
                count=max([len(c) for c in columns]+[1])
                for offset in range(0,count,page_rows):
                    ops=[('rect',0,0,WIDTH,HEIGHT,'#FFFFFF'),('rect',0,0,WIDTH,100,LIGHT),
                         ('text',24,30,'StageOS',20,True,GREEN),('text',24,65,words['title'],23,True,INK),
                         ('text',WIDTH-305,37,f'{start:%d.%m.%Y} - {end:%d.%m.%Y}',14,True,INK),
                         ('text',WIDTH-305,64,words['generated']+': '+generated,10,False,MUTED),
                         ('text',24,127,day.strftime('%d.%m.%Y')+' · '+words['evening' if evening else 'morning']+((' · '+words['continued']) if offset else ''),15,True,GREEN)]
                    for col,rid in enumerate(ids):
                        x=24+col*cw
                        ops.append(('rect',x,143,cw-8,header_height,GREEN))
                        for row,label in enumerate(headers[col]):ops.append(('text',x+12,161+row*15,label,12,True,'#FFFFFF'))
                        ops.append(('rect',x,content_top,cw-8,771-content_top,LIGHT))
                        content=columns[col][offset:offset+page_rows]
                        if not content and offset==0:content=[(words['empty'],False)]
                        for row,(text,bold) in enumerate(content):ops.append(('text',x+12,content_top+17+row*13.2,text,11,bold,INK))
                    ops.append(('text',24,815,'StageOS · '+words['page']+f' {len(pages)+1}',10,False,MUTED))
                    pages.append(ops)
                    if len(pages)>200:raise ValueError('Слишком подробное расписание: сократите период или отключите список сотрудников')
        day+=timedelta(days=1)
    return pages


def render_pdf(pages):
    fonts();out=BytesIO();c=canvas.Canvas(out,pagesize=(WIDTH,HEIGHT),pageCompression=1)
    c.setTitle('StageOS - Production schedule');c.setAuthor('StageOS')
    for ops in pages:
        for op in ops:
            if op[0]=='rect':
                _,x,y,w,h,color=op;c.setFillColor(color);c.rect(x,HEIGHT-y-h,w,h,fill=1,stroke=0)
            else:
                _,x,y,text,size,bold,color=op;c.setFont('StageBold' if bold else 'StageRegular',size);c.setFillColor(color);c.drawString(x,HEIGHT-y,text)
        c.showPage()
    c.save();return out.getvalue()


def render_png(ops):
    scale=2;im=Image.new('RGB',(WIDTH*scale,HEIGHT*scale),'white');draw=ImageDraw.Draw(im);cache={}
    for op in ops:
        if op[0]=='rect':
            _,x,y,w,h,color=op;draw.rectangle((round(x*scale),round(y*scale),round((x+w)*scale),round((y+h)*scale)),fill=color)
        else:
            _,x,y,text,size,bold,color=op
            key=(size,bold)
            if key not in cache:cache[key]=ImageFont.truetype(str(ASSETS/('DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf')),round(size*scale))
            draw.text((round(x*scale),round(y*scale)),text,font=cache[key],fill=color,anchor='ls')
    out=BytesIO();im.save(out,format='PNG');return out.getvalue()


def export(pages,format):
    if format=='pdf':return render_pdf(pages),'application/pdf','pdf'
    if len(pages)==1:return render_png(pages[0]),'image/png','png'
    out=BytesIO()
    with ZipFile(out,'w',ZIP_DEFLATED) as z:
        for i,page in enumerate(pages):z.writestr(f'StageOS-{i+1:03d}.png',render_png(page))
    return out.getvalue(),'application/zip','zip'
