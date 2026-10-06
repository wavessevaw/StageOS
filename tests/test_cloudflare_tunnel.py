import io
import json
from unittest.mock import Mock
import httpx
import pytest
from backend.cloudflare_tunnel import CloudflareTunnel, InternetTunnelController, public_address
from test_tunnel import controller
from test_network import network  # noqa: F401

@pytest.mark.parametrize('value',['http://a.trycloudflare.com','https://trycloudflare.com','https://a.trycloudflare.com.evil.org','https://a.trycloudflare.com/path','https://user:pass@a.trycloudflare.com','https://a.trycloudflare.com?key=x','https://a.trycloudflare.com:444',None])
def test_invalid_public_url(value):
 with pytest.raises(ValueError):public_address(value)

def make(tmp_path):
 host=Mock();host.status.return_value={'running':True};host.config={'port':8765,'code':'private-code'};host.server_id='owned-id'
 t=CloudflareTunnel(tmp_path,host);t.home.mkdir(parents=True);t.exe.write_bytes(b'fake agent');return t

def test_launch_isolated_config_tcp_and_owned_shutdown(tmp_path,monkeypatch):
 t=make(tmp_path);p=Mock();p.poll.return_value=None;p.stderr=io.StringIO('');launch=Mock(return_value=p)
 monkeypatch.setattr('backend.cloudflare_tunnel.subprocess.Popen',launch)
 thread=Mock();thread.is_alive.return_value=False
 monkeypatch.setattr('backend.cloudflare_tunnel.threading.Thread',Mock(return_value=thread))
 monkeypatch.setenv('TUNNEL_TOKEN','must-not-leak');monkeypatch.setenv('CLOUDFLARED_CONFIG','bad.yml')
 t.start();args,kw=launch.call_args
 assert '--protocol' in args[0] and 'http2' in args[0]
 assert '--no-autoupdate' in args[0] and '--config' in args[0]
 assert 'http://127.0.0.1:8765' in args[0]
 assert 'TUNNEL_TOKEN' not in kw['env'] and 'CLOUDFLARED_CONFIG' not in kw['env']
 assert t.config_file.read_text().strip()=='{}'
 assert not t.status()['verified']
 with pytest.raises(ValueError,match='уже запущен'):t.start()
 t.stop();p.terminate.assert_called_once();assert not t.config_file.exists();assert not t.status()['url']
 with pytest.raises(ValueError):t.start(protocol='anything')

def test_reader_extracts_only_quick_tunnel_host(tmp_path):
 t=make(tmp_path);p=Mock();p.stderr=io.StringIO('ignore https://evil.org\nCreated https://good-host.trycloudflare.com\n')
 t.read_output(p,t.stop_event);assert t.candidate=='https://good-host.trycloudflare.com'
 assert public_address(t.candidate)==t.candidate

def test_identity_before_connection_code(tmp_path,monkeypatch):
 t=make(tmp_path);calls=[];correct=False
 def respond(req):
  calls.append(req)
  if req.url.path.endswith('/hello'):return httpx.Response(200,json={'product':'StageOS Server','protocol':1,'server_id':'owned-id' if correct else 'another'})
  return httpx.Response(200,json={'theatres':[]})
 client=httpx.Client(transport=httpx.MockTransport(respond))
 monkeypatch.setattr('backend.tunnel.httpx.Client',lambda **kw:client)
 assert not t.verify('https://owned.trycloudflare.com');assert len(calls)==1;assert 'X-StageOS-Code' not in calls[0].headers


def test_monitor_disconnect_and_recovery_without_changed_address(tmp_path,monkeypatch):
 t=make(tmp_path);t.candidate='https://owned.trycloudflare.com';p=Mock();p.poll.return_value=None
 clock=[0];monkeypatch.setattr('backend.cloudflare_tunnel.time.monotonic',lambda:clock[0]);results=iter([True,False,True]);t.verify=Mock(side_effect=lambda url:next(results));snapshots=[]
 class Event:
  def is_set(self):return False
  def wait(self,seconds):
   snapshots.append(t.status());clock[0]+=65;return len(snapshots)==3
 t.monitor_cloudflare(p,Event())
 assert [s['phase'] for s in snapshots]==['connected','disconnected','connected']
 assert not snapshots[1]['url'] and not snapshots[1]['verified']
 assert snapshots[0]['url']==snapshots[2]['url']

def test_process_exit_is_not_connected(tmp_path):
 t=make(tmp_path);p=Mock();p.poll.return_value=1;t.update(verified=True,url='https://owned.trycloudflare.com');t.monitor_cloudflare(p,t.stop_event)
 assert t.status()['phase']=='error' and not t.status()['verified'] and not t.status()['url']

def test_default_provider_switch_stops_agent_and_persists(tmp_path):
 host=Mock();t=InternetTunnelController(tmp_path,host);assert t.status()['provider']=='cloudflare'
 t.providers['cloudflare'].stop=Mock();t.select('ngrok');t.providers['cloudflare'].stop.assert_called_once()
 assert InternetTunnelController(tmp_path,host).status()['provider']=='ngrok'
 with pytest.raises(ValueError):t.select('unknown')
 assert t.status()['provider']=='ngrok'

def test_cloudflare_checksum_failure_preserves_executable(tmp_path,monkeypatch):
 t=make(tmp_path);response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False);response.iter_bytes.return_value=[b'wrong']
 monkeypatch.setattr('backend.cloudflare_tunnel.os.name','nt');monkeypatch.setattr('backend.cloudflare_tunnel.httpx.stream',Mock(return_value=response))
 with pytest.raises(ValueError):t.install()
 assert t.exe.read_bytes()==b'fake agent';assert not t.exe.with_suffix('.tmp').exists()

def test_local_select_and_remote_management_denied(network):
 host,local,clients,tid,address,code=network
 r=local.post('/api/connection/tunnel',json={'action':'select','provider':'cloudflare'});assert r.status_code==200;assert r.json()['tunnel']['provider']=='cloudflare'
 assert httpx.post(address+'/api/connection/tunnel',headers={'X-StageOS-Code':code},json={'action':'select','provider':'ngrok'}).status_code==403


def test_cloudflare_origin_validation_preserves_login(network):
 host,local,clients,tid,address,code=network
 agent=host.state.network.tunnel.providers['cloudflare'];agent.update(url='https://owned.trycloudflare.com',phase='connected',verified=True)
 headers={'X-StageOS-Code':code,'Origin':'https://owned.trycloudflare.com'}
 response=httpx.post(address+'/api/auth/login',headers=headers,json={'theatre_id':tid,'login':'Админ','password':'test-password'})
 assert response.status_code==200
 headers['Origin']='https://evil.example';assert httpx.post(address+'/api/auth/login',headers=headers,json={}).status_code==403

@pytest.mark.parametrize('identity,addresses,expected', [('owned-id',['104.16.230.132'],True),('other',['104.16.230.132'],False),('owned-id',['127.0.0.1'],False)])
def test_quic_protected_dns_preserves_tls_identity(tmp_path,monkeypatch,identity,addresses,expected):
 t=make(tmp_path);t.protocol='quic';calls=[]
 monkeypatch.setattr('backend.cloudflare_tunnel.NgrokTunnel.verify',Mock(side_effect=httpx.ConnectError('DNS failure')))
 def resolve(*args,**kwargs):
  assert args[0]=='https://cloudflare-dns.com/dns-query'
  return httpx.Response(200,request=httpx.Request('GET',args[0]),json={'Answer':[{'type':1,'data':a} for a in addresses]})
 monkeypatch.setattr('backend.cloudflare_tunnel.httpx.get',resolve)
 class Client:
  def __enter__(self):return self
  def __exit__(self,*args):pass
  def get(self,url,**kwargs):
   assert kwargs['extensions']['sni_hostname']=='owned.trycloudflare.com'
   assert kwargs['headers']['Host']=='owned.trycloudflare.com'
   calls.append((url,dict(kwargs['headers'])))
   value={'product':'StageOS Server','protocol':1,'server_id':identity} if url.endswith('/hello') else {'theatres':[]}
   return httpx.Response(200,request=httpx.Request('GET',url),json=value)
 def factory(**kwargs):
  assert kwargs.get('verify',True) is True
  return Client()
 monkeypatch.setattr('backend.cloudflare_tunnel.httpx.Client',factory)
 assert t.verify('https://owned.trycloudflare.com') is expected
 if calls:assert 'X-StageOS-Code' not in calls[0][1]
 assert len(calls)==(2 if expected else (0 if addresses==['127.0.0.1'] else 1))
