"""Lifecycle, secrets, public identity and host-only management of Internet access."""
import json
import os
import subprocess
from unittest.mock import Mock

import httpx
import pytest
from backend.tunnel import TunnelController, public_address, validate_token, protect
from test_network import network  # noqa: F401

TOKEN = 'test_fake_authtoken_0123456789'


def controller(tmp_path):
    host = Mock()
    host.status.return_value = {'running': True}
    host.config = {'port': 8765, 'code': 'private-connection-code'}
    host.server_id = 'server-instance-id'
    t = TunnelController(tmp_path, host)
    t.home.mkdir(parents=True)
    t.exe.write_bytes(b'fake executable')
    return t


@pytest.mark.parametrize('value', ['http://test.ngrok.app', 'https://ngrok.app.evil.org',
                                 'https://127.0.0.1', 'https://a.ngrok.app/path',
                                 'https://user:pass@a.ngrok.app', 'https://a.ngrok.app?key=x'])
def test_untrusted_agent_url_rejected(value):
    with pytest.raises(ValueError):
        public_address(value)


def test_start_owns_process_and_never_persists_plaintext(tmp_path, monkeypatch):
    t = controller(tmp_path)
    process = Mock()
    process.poll.return_value = None
    popen = Mock(return_value=process)
    monkeypatch.setattr('backend.tunnel.subprocess.Popen', popen)
    worker = Mock()
    worker.is_alive.return_value = False
    monkeypatch.setattr('backend.tunnel.threading.Thread', Mock(return_value=worker))
    t.start(TOKEN)
    args, kw = popen.call_args
    assert TOKEN not in str(args)
    assert kw['env']['NGROK_AUTHTOKEN'] == TOKEN
    assert kw['stdout'] == subprocess.DEVNULL and kw['stderr'] == subprocess.DEVNULL
    assert not t.key_file.exists()
    assert TOKEN not in t.config_file.read_text()
    assert json.loads(t.config_file.read_text())['agent']['remote_management'] is False
    assert t.status()['phase'] == 'starting' and not t.status()['verified']
    with pytest.raises(ValueError, match='уже запущен'):
        t.start(TOKEN)
    t.stop()
    process.terminate.assert_called_once()
    assert not t.config_file.exists()
    assert t.status()['phase'] == 'stopped' and not t.status()['url']
    assert TOKEN not in str(t.network.record.call_args_list)


def test_bad_token_and_missing_server_cannot_launch(tmp_path, monkeypatch):
    t = controller(tmp_path)
    popen = Mock()
    monkeypatch.setattr('backend.tunnel.subprocess.Popen', popen)
    for token in ['short', 'x' * 300, TOKEN + '\n', None]:
        with pytest.raises(ValueError):
            validate_token(token)
    with pytest.raises(ValueError):
        t.start('wrong')
    t.network.status.return_value = {'running': False}
    with pytest.raises(ValueError, match='запустите сервер'):
        t.start(TOKEN)
    popen.assert_not_called()


def test_windows_dpapi_round_trip_and_forget(tmp_path):
    t = controller(tmp_path)
    if os.name != 'nt':
        with pytest.raises(ValueError):
            t.save_key(TOKEN)
        assert not t.key_file.exists()
        return
    t.save_key(TOKEN)
    assert TOKEN.encode() not in t.key_file.read_bytes()
    assert t.read_key() == TOKEN
    assert protect(protect(b'windows-test'), True) == b'windows-test'
    assert t.status()['saved_key']
    t.forget_key()
    assert not t.key_file.exists()


def test_identity_checked_before_code_is_sent(tmp_path, monkeypatch):
    t = controller(tmp_path)
    calls = []
    correct = False

    def respond(request):
        calls.append(request)
        if request.url.path.endswith('/hello'):
            return httpx.Response(200, json={'product': 'StageOS Server', 'protocol': 1,
                                          'server_id': t.network.server_id if correct else 'other-server'})
        return httpx.Response(200, json={'theatres': []})

    original = httpx.Client
    monkeypatch.setattr('backend.tunnel.httpx.Client', lambda **kw: original(transport=httpx.MockTransport(respond), **kw))
    assert not t.verify('https://test.ngrok.app')
    assert len(calls) == 1 and 'x-stageos-code' not in calls[0].headers
    correct = True
    assert t.verify('https://test.ngrok.app')
    assert calls[-1].headers['x-stageos-code'] == 'private-connection-code'
    assert calls[-1].headers['ngrok-skip-browser-warning'] == 'StageOS'


def test_disconnect_recovery_and_verified_url(tmp_path, monkeypatch):
    t = controller(tmp_path)
    clock = iter(range(0, 3000, 61))
    monkeypatch.setattr('backend.tunnel.time.monotonic', lambda: next(clock))
    process = Mock()
    process.poll.return_value = None
    response = httpx.Response(200, request=httpx.Request('GET', 'http://localhost/api/tunnels'),
                             json={'tunnels': [{'proto': 'https', 'public_url': 'https://test.ngrok.app',
                                                'config': {'addr': 'http://127.0.0.1:8765'}}]})
    monkeypatch.setattr('backend.tunnel.httpx.get', lambda *a, **k: response)
    results = iter([False] * 6 + [True, False])
    monkeypatch.setattr(t, 'verify', lambda url: next(results))
    snapshots = []

    class Event:
        def is_set(self):
            return False

        def wait(self, timeout):
            snapshots.append(t.status())
            return len(snapshots) == 8

    t.monitor(process, Event(), 1234, 8765)
    assert snapshots[5]['phase'] == 'disconnected'
    assert snapshots[6]['phase'] == 'connected' and snapshots[6]['verified']
    assert snapshots[6]['url'] == 'https://test.ngrok.app'
    assert snapshots[7]['phase'] == 'disconnected' and not snapshots[7]['url']


def test_agent_exit_never_looks_connected(tmp_path):
    t = controller(tmp_path)
    t.update(phase='connected', verified=True, url='https://test.ngrok.app')
    process = Mock()
    process.poll.return_value = 1
    t.monitor(process, t.stop_event, 1234, 8765)
    assert t.status()['phase'] == 'error' and not t.status()['url'] and not t.status()['verified']


def test_real_host_identity_and_remote_management_denied(network, monkeypatch):
    host, local, (a, b), tid, address, code = network
    hello = httpx.get(address + '/api/network/hello').json()
    assert hello['server_id'] == host.state.network.server_id
    stop = Mock()
    monkeypatch.setattr(host.state.network.tunnel, 'stop', stop)
    assert local.get('/api/connection').json()['can_manage_tunnel']
    assert local.post('/api/connection/tunnel', json={'action': 'stop'}).status_code == 200
    assert stop.call_count == 1
    for path in ['/api/connection', '/api/connection/tunnel', '/api/connection/tunnel/extra']:
        result = httpx.post(address + path, headers={'X-StageOS-Code': code}, json={'action': 'stop'})
        assert result.status_code == 403
    assert a.post('/api/connection/tunnel', json={'action': 'stop'}).status_code == 401
    assert stop.call_count == 1
    local.post('/api/auth/users', json={'name': 'Viewer', 'login': 'viewer', 'password': 'test-password', 'role': 'viewer'})
    local.post('/api/auth/logout')
    from test_accounts import login
    assert login(local, tid, 'viewer').status_code == 200
    assert not local.get('/api/connection').json()['can_manage_tunnel']
    assert local.post('/api/connection/tunnel', json={'action': 'stop'}).status_code == 403


def test_server_shutdown_also_stops_tunnel(network, monkeypatch):
    host, local, clients, tid, address, code = network
    stop = Mock()
    monkeypatch.setattr(host.state.network.tunnel, 'stop', stop)
    host.state.network.stop_server()
    stop.assert_called_once()
    assert not host.state.network.status()['running']


def test_checksum_mismatch_leaves_existing_agent(tmp_path, monkeypatch):
    t = controller(tmp_path)
    if os.name != 'nt':
        pytest.skip('Windows download installer')
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.iter_bytes.return_value = [b'corrupt-archive']
    monkeypatch.setattr('backend.tunnel.httpx.stream', Mock(return_value=response))
    with pytest.raises(ValueError):
        t.install()
    assert t.exe.read_bytes() == b'fake executable'
    assert t.status()['phase'] == 'error'
