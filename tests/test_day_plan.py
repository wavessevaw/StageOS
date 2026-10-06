from test_release import clean, setup_clean


def test_default_day_sequence_and_interval_duration(clean):
    c, Session = clean
    _, _, production, request = setup_clean(c)
    request.update(baseline_plan=True, run_through=True, duration=150)
    response = c.post('/api/preview', json=request)
    assert response.status_code == 200, response.text
    plan = response.json()
    tasks = {t['name']:t for t in plan['tasks']}
    expected = {
        'Монтаж сцены':('08:00','10:00'),'Световой монтаж':('08:00','10:00'),
        'Звуковой монтаж':('08:00','10:00'),'Видеомонтаж':('08:00','10:00'),
        'Orchestra setup':('09:00','10:00'),'Technical Check':('10:00','10:40'),
        'Готовность':('10:40','10:55'),'Прогон':('11:00','14:00'),
        'Обед':('14:00','17:00'),'Сбор перед спектаклем':('17:00','18:00'),
        'Спектакль':('18:00','20:30'),'Демонтаж':('21:30','23:00'),'Возврат':('23:00','00:00')}
    for name, (start,end) in expected.items():
        assert (tasks[name]['start'][11:16],tasks[name]['end'][11:16])==(start,end),name
    saved = c.post('/api/events', json={'request':request,'fingerprint':plan['fingerprint']})
    assert saved.status_code == 200, saved.text
    event = saved.json()
    detail = c.get('/api/events/'+str(event['id'])).json()
    edited = {**detail['current']['request'], 'duration':200}
    extended = c.post('/api/preview', json=edited)
    assert extended.status_code == 200, extended.text
    assert extended.json()['end'][11:16]=='21:20'
    assert next(t for t in extended.json()['tasks'] if t['name']=='Демонтаж')['start'][11:16]=='22:20'
    assert c.post('/api/events',json={'request':edited,'fingerprint':extended.json()['fingerprint']}).status_code == 200
    assert c.get('/api/events/'+str(event['id'])).json()['end'][11:16]=='21:20'
    assert c.get('/api/bootstrap').json()['productions'][0]['data']['duration']==production['data']['duration']
