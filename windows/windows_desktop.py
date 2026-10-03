"""Packaged Windows entrypoint. No externally installed Python or console needed."""

import os, sys, json, traceback, socket, secrets, threading, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
HOME = Path(os.environ.get("STAGEOS_HOME", Path(os.environ.get("LOCALAPPDATA", Path.home())) / "StageOS-Work"))
HOME.mkdir(parents=True, exist_ok=True)
os.environ["STAGEOS_HOME"] = str(HOME)
os.environ["STAGEOS_TOKEN"] = secrets.token_urlsafe(32)


def self_test():
    from backend.app import create_app
    from backend.models import make_engine,Resource,Production,Event
    from backend.catalog import save_venue
    from backend.production_editor import template,validate_production
    from backend.engine import Request,preview,save_plan
    from sqlalchemy import select,func
    from datetime import datetime
    with tempfile.TemporaryDirectory(prefix='stageos-selftest-') as tmp:
        engine=make_engine('sqlite:///'+str(Path(tmp)/'selftest.db'))
        try:
            app=create_app(engine,demo_enabled=False)
            with app.state.Session.begin() as s:
                assert s.scalar(select(func.count(Resource.id)))==0
                venue=save_venue(s,{'name':'Проверка площадки','data':{}})
                person=Resource(kind='Person',name='Проверка исполнителя',department='Артисты',data={'qualification':['Артисты'],'specialization':'Солист'})
                s.add(person);s.flush()
                data=template()['data'];data['home_venue']=venue.id
                data['roles']=[dict(role='Проверочная роль',A=person.id,B=person.id,eligible=[person.id])]
                p=Production(name='Проверка постановки',data=validate_production(s,data));s.add(p);s.flush()
                r=Request(production_id=p.id,venue_id=venue.id,start=datetime(2026,12,1,18))
                plan=preview(s,r);assert plan['status']=='READY';ev=save_plan(s,r,plan)
                return {'status':'PASS','python':sys.version,'platform':sys.platform,'solver':plan['solver']['status'],'empty_database':'PASS','event_saved':ev.id,'desktop_gui':'NOT_TESTED'}
        finally:
            engine.dispose()


def main():
    if "--self-test" in sys.argv:
        result = self_test()
        (HOME / "selftest.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return
    import uvicorn
    from backend.app import create_app

    # Native WinForms/WebView2 host. Pythonnet loads the .NET Framework shipped with Windows.
    import webview

    preference = HOME / "database-choice.json"
    if preference.exists():
        chosen = json.loads(preference.read_text(encoding="utf-8")).get("path")
        if chosen and Path(chosen).is_file():
            os.environ["STAGEOS_DATABASE_URL"] = "sqlite:///" + chosen.replace(
                "\\", "/"
            )
    app = create_app(demo_enabled=False)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
        log_config=None,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(
        target=server.run, kwargs={"sockets": [listener]}, daemon=True
    )
    thread.start()
    import time

    for _ in range(600):
        if server.started:
            break
        if not thread.is_alive():
            raise RuntimeError("Локальный сервер завершился при запуске")
        time.sleep(0.05)
    else:
        raise RuntimeError("Локальный сервер не запустился за 30 секунд")
    url = f"http://127.0.0.1:{port}/?token=" + os.environ["STAGEOS_TOKEN"]
    window = webview.create_window(
        "StageOS — управление театральным производством",
        url,
        width=1440,
        height=940,
        min_size=(1000, 700),
        background_color="#f6f7f5",
    )
    try:
        webview.start(
            gui="edgechromium",
            debug=False,
            private_mode=False,
            storage_path=str(HOME / "WebView2"),
        )
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        listener.close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        trace = traceback.format_exc()
        (HOME / "startup-error.log").write_text(trace, encoding="utf-8")
        if "--self-test" in sys.argv:
            (HOME / "selftest.json").write_text(
                json.dumps({"status": "FAILED", "traceback": trace}, indent=2),
                encoding="utf-8",
            )
        else:
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                None,
                "Не удалось запустить StageOS.\n\nПричина записана в журнале. Если DLL заблокирована Windows, разблокируйте исходный ZIP перед распаковкой.\n\nПодробности: "
                + str(HOME / "startup-error.log"),
                "StageOS",
                0x10,
            )
        sys.exit(1)
