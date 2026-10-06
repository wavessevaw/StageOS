"""Persistent account access history and seven-hour copies next to the program."""
import csv
import io
import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from fastapi import HTTPException, Request

def migrate(registry):
    with registry.db() as db:
        columns={r[1] for r in db.execute('PRAGMA table_info(account_audit)')}
        for name in ['actor_name','actor_login','client']:
            if name not in columns:db.execute(f'ALTER TABLE account_audit ADD COLUMN {name} TEXT')

def rows(registry,tid,before=None,limit=200):
    with registry.db() as db:
        query="SELECT a.id,a.created,a.action,COALESCE(a.actor_name,u.name,'') name,COALESCE(a.actor_login,u.login,'') login,COALESCE(a.client,'Компьютер') client FROM account_audit a LEFT JOIN users u ON a.actor=u.id WHERE a.theatre_id=? AND a.action IN ('Вход в аккаунт','Выход из аккаунта')"
        args=[tid]
        if before:query+=' AND a.id<?';args.append(before)
        query+=' ORDER BY a.id DESC'
        if limit:query+=' LIMIT ?';args.append(limit)
        return [dict(r) for r in db.execute(query,args)]

def export(registry,tid):
    folder=Path(os.environ.get('STAGEOS_INSTALL_DIR',Path(__file__).resolve().parent.parent))/'StageOS-Logs';folder.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now().strftime('%Y-%m-%d_%H-%M-%S_%f');target=folder/f'access-{tid}-{stamp}.csv';temp=target.with_suffix('.tmp')
    stream=io.StringIO();writer=csv.writer(stream,delimiter=';');writer.writerow(['Дата и время','Имя','Логин','Устройство','Действие'])
    for row in reversed(rows(registry,tid,limit=None)):
        values=[row[k] for k in ['created','name','login','client','action']]
        writer.writerow(["'"+v if v.startswith(('=','+','-','@','\t','\r')) else v for v in values])
    temp.write_text(stream.getvalue(),encoding='utf-8-sig');temp.replace(target);return str(target)

class Worker:
    def __init__(self,registry):self.registry=registry;self.stop_event=threading.Event();self.path=registry.home/'access-log-export.json';self.thread=None
    def tick(self,now=None):
        now=time.time() if now is None else now
        try:last=float(json.loads(self.path.read_text(encoding='utf-8'))['last_export'])
        except (OSError,ValueError,KeyError,TypeError):last=now;self.path.write_text(json.dumps({'last_export':last}),encoding='utf-8')
        if now-last<7*3600:return False
        with self.registry.db() as db:ids=[r[0] for r in db.execute('SELECT id FROM theatres')]
        for tid in ids:
            if self.stop_event.is_set():return False
            export(self.registry,tid)
        temp=self.path.with_suffix('.tmp');temp.write_text(json.dumps({'last_export':now}),encoding='utf-8');temp.replace(self.path);return True
    def start(self):self.thread=threading.Thread(target=self.run,daemon=True,name='StageOS-access-log');self.thread.start()
    def stop(self):self.stop_event.set()
    def run(self):
        while not self.stop_event.is_set():
            try:self.tick()
            except OSError:pass  # Retain the database and retry; never advance the export clock after failure.
            self.stop_event.wait(60)

def install(app,registry,controller):
    def admin(req):
        user=registry.current(req)
        if user['role']!='admin' or controller.config['mode']=='client':raise HTTPException(403,'Журнал доступен администратору на компьютере сервера')
        return user
    @app.get('/api/connection/access-log')
    def history(req:Request,before:int|None=None):
        user=admin(req);items=rows(registry,user['theatre_id'],before)
        return {'items':items,'next':items[-1]['id'] if len(items)==200 else None,'folder':'StageOS-Logs','interval_hours':7}
    @app.post('/api/connection/access-log/export')
    def save(req:Request):
        user=admin(req)
        try:return {'saved':True,'path':export(registry,user['theatre_id'])}
        except OSError as e:raise HTTPException(422,'Не удалось записать копию рядом с программой. История остаётся в базе; проверьте права папки.') from e
