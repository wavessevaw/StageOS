from test_release import clean


def test_language_saved_before_initialization_and_reloaded(clean):
    c,_=clean
    assert c.put('/api/settings/interface',json={'language':'en'}).status_code==200
    boot=c.get('/api/bootstrap').json()
    assert boot['language']=='en' and not boot['initialized']
    assert c.put('/api/settings/interface',json={'language':'fr'}).status_code==422
    assert c.get('/api/bootstrap').json()['language']=='en'
    assert c.put('/api/settings/interface',json={'language':'ru'}).status_code==200


def test_assistant_disabled_returns_requested_language(clean):
    c,_=clean
    answer=c.post('/api/assistant',json={'text':'What happens today?','language':'en'}).json()['answer']
    assert 'disabled' in answer and 'Scheduling' in answer
    assert 'отключён' in c.post('/api/assistant',json={'text':'Что сегодня?'}).json()['answer']
    assert c.post('/api/assistant',json={'text':'Question','language':'unknown'}).status_code==422
