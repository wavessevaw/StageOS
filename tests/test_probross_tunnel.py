import io
from unittest.mock import Mock

import pytest

from backend.probross_tunnel import ProbrossTunnel, public_address, validate_token


@pytest.mark.parametrize("value", [
    "http://demo.probross.ru",
    "https://probross.ru",
    "https://demo.probross.ru.evil.org",
    "https://demo.probross.ru/path",
    "https://user:pass@demo.probross.ru",
    "https://demo.probross.ru:444",
    None,
])
def test_invalid_public_url(value):
    with pytest.raises(ValueError):
        public_address(value)


def make(tmp_path):
    host = Mock()
    host.status.return_value = {"running": True}
    host.config = {"port": 8765, "code": "private-code"}
    host.server_id = "owned-id"
    tunnel = ProbrossTunnel(tmp_path, host)
    tunnel.home.mkdir(parents=True)
    tunnel.exe.write_bytes(b"fake agent")
    return tunnel


def test_token_validation():
    assert validate_token("probross_tunnel_token_123456") == "probross_tunnel_token_123456"
    with pytest.raises(ValueError):
        validate_token("short")
    with pytest.raises(ValueError):
        validate_token("valid-looking-token\nleak")


def test_reader_extracts_probross_address(tmp_path):
    tunnel = make(tmp_path)
    process = Mock()
    process.stdout = io.StringIO("connected\npublic: https://stageos-demo.probross.ru\n")
    tunnel.read_output(process, tunnel.stop_event)
    assert tunnel.candidate == "https://stageos-demo.probross.ru"
    assert public_address(tunnel.candidate) == tunnel.candidate


def test_start_uses_local_stageos_and_never_logs_raw_output(tmp_path, monkeypatch):
    tunnel = make(tmp_path)
    process = Mock()
    process.poll.return_value = None
    process.stdout = io.StringIO("")
    launch = Mock(return_value=process)
    monkeypatch.setattr("backend.probross_tunnel.subprocess.Popen", launch)
    thread = Mock()
    thread.is_alive.return_value = False
    monkeypatch.setattr("backend.probross_tunnel.threading.Thread", Mock(return_value=thread))

    tunnel.start("probross_tunnel_token_123456")
    args, kwargs = launch.call_args
    assert args[0][1:3] == ["tunnel", "--local"]
    assert "http://127.0.0.1:8765" in args[0]
    assert "--token" in args[0]
    assert "PROBROSS_TOKEN" not in kwargs["env"]
    assert not tunnel.status()["verified"]

    tunnel.stop()
    process.terminate.assert_called_once()


def test_monitor_only_exposes_verified_address(tmp_path, monkeypatch):
    tunnel = make(tmp_path)
    tunnel.candidate = "https://stageos-demo.probross.ru"
    process = Mock()
    process.poll.return_value = None
    tunnel.verify = Mock(return_value=True)
    clock = [0.0]
    monkeypatch.setattr("backend.probross_tunnel.time.monotonic", lambda: clock[0])

    snapshots = []
    class Event:
        def is_set(self):
            return False
        def wait(self, seconds):
            snapshots.append(tunnel.status())
            return True

    tunnel.monitor_probross(process, Event())
    assert snapshots[0]["phase"] == "connected"
    assert snapshots[0]["verified"] is True
    assert snapshots[0]["url"] == "https://stageos-demo.probross.ru"
