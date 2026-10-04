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
                from backend.schedule_export import build_pages,export
                from datetime import date
                pages=build_pages([],[],[],date(2026,12,1),date(2026,12,1))
                assert export(pages,'pdf')[0].startswith(b'%PDF-')
                assert export(pages,'png')[0].startswith(b'\x89PNG')
                # Real TCP round-trip using the packaged runtime and dependencies.
                from backend.network import create_desktop_app
                from fastapi.testclient import TestClient
                import httpx,socket
                gateway=create_desktop_app(Path(tmp)/'network');client=TestClient(gateway,headers={"X-StageOS-Token":os.environ.get("STAGEOS_TOKEN","")})
                response=client.post('/api/auth/theatres',json={'theatre_name':'Проверка сети','name':'Проверка администратора','login':'network-test','password':'network-test-password'})
                assert response.status_code==200
                tid=response.json()['id']
                with socket.socket() as probe:probe.bind(('127.0.0.1',0));network_port=probe.getsockname()[1]
                try:
                    gateway.state.network.start_server(network_port)
                    address=f'http://127.0.0.1:{network_port}'
                    with httpx.Client(trust_env=False,headers={'X-StageOS-Code':gateway.state.network.config['code']}) as remote:
                        assert remote.get(address+'/api/network/hello').json()['product']=='StageOS Server'
                        assert remote.post(address+'/api/auth/login',json={'theatre_id':tid,'login':'network-test','password':'network-test-password'}).status_code==200
                        assert remote.get(address+'/api/bootstrap').status_code==200
                finally:
                    gateway.state.network.stop_server()
                    gateway.state.network.workspace.state.registry.close()
                return {'network_server':'PASS','status':'PASS' ,'python':sys.version,'platform':sys.platform,'solver':plan['solver']['status'],'empty_database':'PASS','event_saved':ev.id,'desktop_gui':'NOT_TESTED','pdf_export':'PASS','png_export':'PASS'}
        finally:
            engine.dispose()


def main():
    if "--self-test" in sys.argv:
        result = self_test()
        (HOME / "selftest.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return
    # One running desktop/server per data directory, including two different EXEs.
    import ctypes,hashlib
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateMutexW.argtypes=[ctypes.c_void_p,ctypes.c_bool,ctypes.c_wchar_p]
    kernel.CreateMutexW.restype=ctypes.c_void_p
    mutex=kernel.CreateMutexW(None,False,'Local\\StageOS-'+hashlib.sha256(str(HOME.resolve()).casefold().encode()).hexdigest()[:24])
    if not mutex:raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error()==183:
        ctypes.windll.user32.MessageBoxW(None,'StageOS уже запущен для этой базы. Используйте открытое окно или закройте его перед запуском другого режима.','StageOS',0x40)
        return
    import uvicorn
    from backend.app import create_app

    # Native WinForms/WebView2 host. Pythonnet loads the .NET Framework shipped with Windows.
    import webview
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("StageOS.Desktop")

    from backend.network import create_desktop_app
    profile = ROOT.parent / "bootstrap-accounts.json"
    app = create_desktop_app(bootstrap_file=profile if profile.is_file() else None)
    if "--server" in sys.argv and app.state.network.config["mode"] != "server":
        app.state.network.start_server(8765)
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
    gui_test = "--gui-test" in sys.argv
    gui_result = {}
    def verify_window():
        try:
            if not window.events.loaded.wait(45):
                raise RuntimeError("Окно не загрузилось за 45 секунд")
            deadline=time.monotonic()+30
            while time.monotonic()<deadline:
                if window.evaluate_js("document.body.innerText.includes('Выберите театр')"):break
                time.sleep(0.1)
            else:raise RuntimeError("Стартовый интерфейс не появился")
            assert window.evaluate_js("Boolean(sessionStorage.getItem('stageos-token'))")
            assert window.evaluate_js("location.search === ''")
            assert window.native.Icon is not None
            if "--server" in sys.argv:assert app.state.network.status()["running"]
            gui_result.update(status="PASS",window="WebView2",react="PASS",token="PASS",icon="PASS",platform=sys.platform,network_server="PASS" if "--server" in sys.argv else "NOT_REQUESTED")
        except Exception:
            gui_result.update(status="FAILED",traceback=traceback.format_exc())
        finally:
            (HOME / "gui-selftest.json").write_text(json.dumps(gui_result,ensure_ascii=False,indent=2),encoding="utf-8")
            window.destroy()
    try:
        webview.start(
            func=verify_window if gui_test else None,
            gui="edgechromium",
            icon=str(ROOT.parent / "StageOS.ico"),
            debug=False,
            private_mode=False,
            storage_path=str(HOME / "WebView2"),
        )
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        app.state.network.stop_server()
        app.state.network.workspace.state.registry.close()
        listener.close()
    if gui_test and (gui_result.get("status")!="PASS" or thread.is_alive()):
        raise RuntimeError("Проверка окна или завершения сервера не пройдена")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        trace = traceback.format_exc()
        (HOME / "startup-error.log").write_text(trace, encoding="utf-8")
        if "--self-test" in sys.argv or "--gui-test" in sys.argv:
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
