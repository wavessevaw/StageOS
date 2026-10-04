from datetime import date
from io import BytesIO
from zipfile import ZipFile
from PIL import Image
from sqlalchemy import select,func
from backend.models import Event,Audit
from backend.schedule_export import wrap,build_pages,render_pdf,export,translated
from test_release import clean,setup_clean
from test_core import confirm


def test_export_pdf_png_read_only_filters_and_notes(clean):
    c,S=clean;venue,person,p,req=setup_clean(c)
    req['notes']='Сбор у входа. Проверить реквизит.'
    assert confirm(c,req).status_code==200
    with S() as s:before=(s.scalar(select(func.count()).select_from(Event)),s.scalar(select(func.count()).select_from(Audit)))
    result=c.get('/api/schedule/export',params={'start':'2026-12-01','end':'2026-12-01','format':'pdf','person':person['id']})
    assert result.status_code==200,result.text
    assert result.content.startswith(b'%PDF-') and result.headers['content-type']=='application/pdf'
    png=c.get('/api/schedule/export',params={'start':'2026-12-01','end':'2026-12-01','format':'png','include_people':False})
    assert png.status_code==200
    if png.headers['content-type']=='application/zip':
        with ZipFile(BytesIO(png.content)) as z:
            assert z.testzip() is None
            for name in z.namelist():
                with Image.open(BytesIO(z.read(name))) as im:assert im.size==(2380,1684)
    else:
        with Image.open(BytesIO(png.content)) as im:assert im.size==(2380,1684)
    with S() as s:assert before==(s.scalar(select(func.count()).select_from(Event)),s.scalar(select(func.count()).select_from(Audit)))


def test_export_validation_and_empty_calendar(clean):
    c,_=clean
    for params in [dict(start='2026-12-31',end='2026-12-01'),dict(start='2026-12-01',end='2027-02-01'),dict(start='bad',end='2026-12-01'),dict(start='2026-12-01',end='2026-12-01',format='html')]:
        assert c.get('/api/schedule/export',params=params).status_code==422
    png=c.get('/api/schedule/export',params={'start':'2026-12-01','end':'2026-12-01','format':'png'})
    assert png.headers['content-type']=='image/png'
    Image.open(BytesIO(png.content)).verify()


def test_export_long_content_paginates_without_losing_text():
    long=''.join(str(i)+'_' for i in range(2000))
    chunks=wrap(long,300)
    assert ''.join(chunks)==long
    from types import SimpleNamespace
    resource=SimpleNamespace(id=1,name='Зал',kind='Venue',data={})
    event=dict(venue_id=1,title='Постановка',kind='Спектакль',start='2026-12-01T18:00:00',end='2026-12-01T20:00:00',health='READY',export_plan={'notes':long,'tasks':[],'assignments':[]})
    pages=build_pages([event],[resource],[],date(2026,12,1),date(2026,12,1))
    assert len(pages)>2
    body=''.join(op[3] for page in pages for op in page if op[0]=='text')
    assert '1999_' in body
    assert translated('Principal','ru')=='Ведущий танцовщик'
    assert translated('Violin I','ru')=='Первые скрипки'
    assert translated('Horn','en')=='Horn'
    assert render_pdf(pages).startswith(b'%PDF-')
    content,mime,ext=export(pages,'png')
    assert mime=='application/zip' and ext=='zip'
    with ZipFile(BytesIO(content)) as z:assert len(z.namelist())==len(pages)


def test_two_rooms_are_independent_and_parent_filter_includes_both(clean):
    c,_=clean;venue,person,p,req=setup_clean(c)
    second=c.post('/api/resources',json={'name':'Второй артист','kind':'Person','department':'Артисты','data':{'qualification':['Артисты']}}).json()
    rooms=[c.post('/api/resources',json={'name':name,'kind':'Room','department':'Площадки','data':{'venue_id':venue['id'],'capacity':10}}).json() for name in ['Хоровой','Балетный']]
    first={**req,'venue_id':rooms[0]['id'],'kind':'Репетиция','rehearsal_people':[person['id']]}
    assert confirm(c,first).status_code==200
    other={**first,'venue_id':rooms[1]['id'],'rehearsal_people':[second['id']]}
    preview=c.post('/api/preview',json=other).json()
    assert preview['status']=='READY',preview['conflicts']
    assert confirm(c,other).status_code==200
    overlap=c.post('/api/preview',json={**other,'venue_id':rooms[0]['id']}).json()
    assert any(x['code']=='overlap' for x in overlap['conflicts'])
    events=c.get('/api/events',params={'venue':venue['id'],'start':'2026-12-01','end':'2026-12-02'}).json()
    assert {e['venue_id'] for e in events}=={r['id'] for r in rooms}
