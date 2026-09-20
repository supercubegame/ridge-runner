"""Bounded diagnostics: no request headers, paths, credentials or bodies logged."""
import json,subprocess,sys,socket,time,urllib.request
REMOTE=r'''import datetime,http.server,json,signal,threading,time,urllib.request
PORT=__PORT__
LIFETIME=__LIFETIME__
MARKER=__MARKER__.encode()
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
class Expired(BaseException):pass
def expire(*a):raise Expired()
def counts():
 out={'tcp4':0,'tcp6':0}
 for family,path in [('tcp4','/proc/net/tcp'),('tcp6','/proc/net/tcp6')]:
  with open(path) as f:lines=f.read().splitlines()[1:]
  for line in lines:
   fields=line.split()
   if fields[3]=='0A' and int(fields[1].rsplit(':',1)[1],16)==PORT:out[family]+=1
 return out
hits={'local_selfcheck':0,'probe':0,'root':0,'other':0}
class Server(http.server.ThreadingHTTPServer):
 allow_reuse_address=False
 daemon_threads=True
 def get_request(self):
  sock,address=super().get_request();sock.settimeout(1);return sock,address
 def handle_error(self,*a):pass
class Handler(http.server.BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def do_GET(self):
  kind='local_selfcheck' if self.path=='/local-selfcheck' and self.client_address[0]=='127.0.0.1' else 'probe' if self.path=='/probe' else 'root' if self.path=='/' else 'other'
  hits[kind]+=1
  if kind not in ('local_selfcheck','probe'):
   self.send_response(404);self.send_header('Content-Length','0');self.end_headers();return
  self.send_response(200);self.send_header('Content-Type','application/json')
  self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(MARKER)))
  self.end_headers();self.wfile.write(MARKER)
server=None;thread=None;start=time.monotonic();exit_code=2
report={'status':'FAIL','bound':False,'lifetime_seconds':LIFETIME,'diagnostics':{'started_at_utc':now(),'local_http_ok':False}}
signal.signal(signal.SIGALRM,expire);signal.alarm(LIFETIME)
try:
 report['before']=counts()
 if any(report['before'].values()):raise RuntimeError('PORT_OCCUPIED')
 server=Server(('0.0.0.0',PORT),Handler);report['bound']=True
 thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.1},daemon=True);thread.start()
 report['diagnostics']['listening_at_utc']=now()
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 with opener.open('http://127.0.0.1:'+str(PORT)+'/local-selfcheck',timeout=2) as response:
  report['diagnostics']['local_http_status']=response.status
  report['diagnostics']['local_http_ok']=response.status==200 and response.read(4097)==MARKER
 report['diagnostics']['local_checked_at_utc']=now()
 if not report['diagnostics']['local_http_ok']:raise RuntimeError('LOCAL_HTTP_FAILED')
 while True:time.sleep(.2)
except Expired:
 report['status']='EXPIRED_CLOSED' if report['bound'] else 'EXPIRED_BEFORE_BIND';exit_code=0 if report['bound'] and report['diagnostics']['local_http_ok'] else 2
except BaseException as e:report['error_type']=type(e).__name__
finally:
 signal.alarm(0)
 if server:
  if thread:server.shutdown();thread.join(timeout=2)
  server.server_close()
 report['after']=counts();report['elapsed_seconds']=round(time.monotonic()-start,3)
 report['diagnostics']['request_counts']=dict(hits);report['diagnostics']['finished_at_utc']=now()
 print(json.dumps(report,sort_keys=True),flush=True)
raise SystemExit(exit_code)
'''
def remote_source(port=8061,lifetime=120,marker='{"probe":"fixture"}'):
 assert type(port) is int and 1<=port<=65535 and type(lifetime) is int and 1<=lifetime<=150
 return REMOTE.replace('__PORT__',str(port)).replace('__LIFETIME__',str(lifetime)).replace('__MARKER__',repr(marker))
def test():
 with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
 child=subprocess.Popen([sys.executable,'-c',remote_source(port,3)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 try:
  time.sleep(.5)
  opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
  req=urllib.request.Request('http://127.0.0.1:'+str(port)+'/probe',headers={'Authorization':'Basic sentinel-SECRET'})
  with opener.open(req,timeout=1) as response:assert response.status==200 and response.read()==b'{"probe":"fixture"}'
  slow=socket.create_connection(('127.0.0.1',port));slow.sendall(b'GET /probe HTTP/1.1\r\n')
  out,err=child.communicate(timeout=6);slow.close();data=json.loads(out)
  assert child.returncode==0 and data['status']=='EXPIRED_CLOSED' and data['after']=={'tcp4':0,'tcp6':0}
  assert data['diagnostics']['local_http_ok'] and data['diagnostics']['request_counts']=={'local_selfcheck':1,'probe':1,'root':0,'other':0}
  assert data['elapsed_seconds']<5 and 'sentinel-SECRET' not in out+err and not err
 finally:
  if child.poll() is None:child.terminate();child.wait()
 with socket.socket() as blocker:
  blocker.bind(('0.0.0.0',0));blocker.listen()
  run=subprocess.run([sys.executable,'-c',remote_source(blocker.getsockname()[1],2)],capture_output=True,text=True,timeout=4)
  data=json.loads(run.stdout);assert run.returncode==2 and not data['bound']
 print('PASS diagnostic server local HTTP, separate counters, redaction, slow client, lifetime, occupied-port refusal')
