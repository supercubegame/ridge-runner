"""Bounded numeric-only TCP/HTTP instrumentation; never logs requests."""
import json,pathlib,socket,subprocess,sys,time
REMOTE=r'''
import http.server,json,signal,socket,threading,time,urllib.request
PORT=__PORT__
LIFETIME=__LIFETIME__
MARKER=__MARKER__
METHODS=('GET','HEAD','POST','OPTIONS','OTHER')
STATUSES=('200','400','404','405','408','501','other')
class Expired(BaseException):pass
class Counters:
 def __init__(self):
  self.lock=threading.Lock();self.tcp=0;self.methods=dict.fromkeys(METHODS,0);self.statuses=dict.fromkeys(STATUSES,0);self.parse=0;self.timeout=0
 def add(self,kind,key=None):
  with self.lock:
   if kind=='tcp':self.tcp+=1
   elif kind=='parse':self.parse+=1;self.methods['OTHER']+=1
   elif kind=='timeout':self.timeout+=1
   elif kind=='method':self.methods[key if key in METHODS[:-1] else 'OTHER']+=1
   elif kind=='status':self.statuses[str(key) if str(key) in STATUSES[:-1] else 'other']+=1
 def snapshot(self):
  with self.lock:return dict(accepted_tcp=self.tcp,method_counts=dict(self.methods),status_counts=dict(self.statuses),parse_error_count=self.parse,read_timeout_count=self.timeout)
counter=Counters()
class Server(http.server.ThreadingHTTPServer):
 allow_reuse_address=False
 daemon_threads=True
 def get_request(self):
  sock,address=super().get_request();counter.add('tcp');sock.settimeout(1);return sock,address
 def handle_error(self,*a):pass
class Handler(http.server.BaseHTTPRequestHandler):
 server_version=''
 sys_version=''
 def log_message(self,*a):pass
 def send_response(self,code,message=None):
  counter.add('status',code);return super().send_response(code,message)
 def send_error(self,code,message=None,explain=None):
  self.send_response(code);self.send_header('Content-Length','0');self.end_headers();self.wfile.flush()
 def parse_request(self):
  try:ok=super().parse_request()
  except (socket.timeout,TimeoutError):raise
  except Exception:self.close_connection=True;counter.add('parse');return False
  if not ok:counter.add('parse');return False
  counter.add('method',self.command.upper());return True
 def handle_one_request(self):
  try:
   self.raw_requestline=self.rfile.readline(65537)
   if len(self.raw_requestline)>65536:
    self.requestline='';self.request_version='';self.command='';self.send_error(414);return
   if not self.raw_requestline:self.close_connection=True;return
   if not self.parse_request():return
   getattr(self,'do_'+self.command,self.unsupported)();self.wfile.flush()
  except (socket.timeout,TimeoutError):self.close_connection=True;counter.add('timeout')
  except Exception:self.close_connection=True
 def empty(self,code):
  self.send_response(code);self.send_header('Content-Length','0');self.end_headers()
 def marker(self):
  data=MARKER.encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
 def do_GET(self):
  if self.path=='/local-selfcheck' and self.client_address[0]=='127.0.0.1':self.server.local=True;self.marker()
  elif self.path=='/probe':self.server.probes+=1;self.marker()
  else:
   if self.path=='/':self.server.roots+=1
   self.empty(404)
 def unsupported(self):self.empty(405)
 do_HEAD=unsupported
 do_POST=unsupported
 do_OPTIONS=unsupported
def counts():
 out={'tcp4':0,'tcp6':0}
 for family,path in [('tcp4','/proc/net/tcp'),('tcp6','/proc/net/tcp6')]:
  with open(path) as f:lines=f.read().splitlines()[1:]
  for line in lines:
   fields=line.split()
   if len(fields)>3 and fields[3]=='0A' and int(fields[1].rsplit(':',1)[1],16)==PORT:out[family]+=1
 return out
def expire(*a):raise Expired()
server=None;thread=None;code=2;start=time.monotonic();local=False
report={'status':'FAIL','bound':False,'lifetime_seconds':LIFETIME,'local_selfcheck_http':False}
signal.signal(signal.SIGALRM,expire);signal.alarm(LIFETIME)
try:
 report['before']=counts()
 if any(report['before'].values()):report['status']='PORT_CONFLICT'
 else:
  server=Server(('0.0.0.0',PORT),Handler);server.local=False;server.probes=0;server.roots=0;report['bound']=True
  thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.1},daemon=True);thread.start()
  try:
   opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
   with opener.open('http://127.0.0.1:'+str(PORT)+'/local-selfcheck',timeout=2) as response:local=response.status==200 and response.read(4097)==MARKER.encode()
  except Exception:local=False
  report['local_selfcheck_http']=local
  while True:time.sleep(.2)
except Expired:
 report['status']='EXPIRED_CLOSED' if report['bound'] and local else 'EXPIRED_LOCAL_CHECK_FAILED';code=0 if report['bound'] and local else 2
except OSError:report['status']='BIND_OR_RUNTIME_ERROR' if report['bound'] else 'PORT_CONFLICT'
except BaseException:report['status']='RUNTIME_ERROR'
finally:
 signal.alarm(0)
 if server:
  server.shutdown()
  if thread:thread.join(timeout=2)
  server.server_close()
 report['after']=counts();report['elapsed_seconds']=round(time.monotonic()-start,3);report['counters']=counter.snapshot()
 report['http_classification']={'local_selfcheck':bool(server and server.local),'probe_get':server.probes if server else 0,'root_get':server.roots if server else 0}
 print(json.dumps(report,sort_keys=True),flush=True)
raise SystemExit(code)
'''
def remote_source(marker,port=8061,lifetime=120):
 if type(port) is not int or not 1<=port<=65535 or type(lifetime) is not int or not 1<=lifetime<=150:raise ValueError('BOUNDS')
 return REMOTE.replace('__PORT__',str(port)).replace('__LIFETIME__',str(lifetime)).replace('__MARKER__',repr(marker))
def validate_report(data):
 assert set(data)=={'status','bound','lifetime_seconds','local_selfcheck_http','before','after','elapsed_seconds','counters','http_classification'}
 assert data['status'] in {'EXPIRED_CLOSED','EXPIRED_LOCAL_CHECK_FAILED','PORT_CONFLICT','BIND_OR_RUNTIME_ERROR','RUNTIME_ERROR','FAIL'}
 assert type(data['bound']) is bool and type(data['local_selfcheck_http']) is bool
 assert type(data['lifetime_seconds']) is int and 1<=data['lifetime_seconds']<=150
 assert type(data['elapsed_seconds']) in (int,float) and 0<=data['elapsed_seconds']<180
 for k in ('before','after'):
  assert set(data[k])=={'tcp4','tcp6'} and all(type(v) is int and v>=0 for v in data[k].values())
 c=data['counters'];assert set(c)=={'accepted_tcp','method_counts','status_counts','parse_error_count','read_timeout_count'}
 assert set(c['method_counts'])=={'GET','HEAD','POST','OPTIONS','OTHER'}
 assert set(c['status_counts'])=={'200','400','404','405','408','501','other'}
 assert all(type(v) is int and v>=0 for v in [c['accepted_tcp'],c['parse_error_count'],c['read_timeout_count'],*c['method_counts'].values(),*c['status_counts'].values()])
 h=data['http_classification'];assert set(h)=={'local_selfcheck','probe_get','root_get'}
 assert type(h['local_selfcheck']) is bool and all(type(h[k]) is int and h[k]>=0 for k in ('probe_get','root_get'))
def test():
 checks=[]
 def check(name,value):checks.append({'name':name,'pass':bool(value)});assert value,name
 for value in (0,151,True):
  try:remote_source('fixture',lifetime=value);ok=False
  except ValueError:ok=True
  check('reject_lifetime_'+str(value),ok)
 marker='{"probe":"fixture-v6"}';source=remote_source(marker);compile(source,'remote','exec')
 check('no_file_server_or_env',all(x not in source for x in ('SimpleHTTPRequestHandler','environ','lightning_sdk','subprocess')))
 reserve=socket.socket();reserve.bind(('127.0.0.1',0));port=reserve.getsockname()[1];reserve.close()
 child=subprocess.Popen([sys.executable,'-c',remote_source(marker,port,6)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 try:
  for _ in range(80):
   try:s=socket.create_connection(('127.0.0.1',port),.1);s.close();break
   except OSError:time.sleep(.03)
  for method,path,status in [('GET','/probe',200),('GET','/',404),('HEAD','/probe',405),('POST','/probe',405),('OPTIONS','/probe',405),('PATCH','/probe',405)]:
   with socket.create_connection(('127.0.0.1',port),2) as s:
    s.settimeout(2);s.sendall((method+' '+path+' HTTP/1.1\r\nHost: wrong-host\r\nAuthorization: Basic sentinel-SECRET\r\nConnection: close\r\n\r\n').encode());data=b''
    while True:
     part=s.recv(4096)
     if not part:break
     data+=part
   check(method+path,data.startswith(('HTTP/1.0 '+str(status)).encode()) and (status!=200 or data.endswith(marker.encode())))
  with socket.create_connection(('127.0.0.1',port),2) as s:s.sendall(b'NOT A VALID REQUEST\r\n\r\n');s.recv(4096)
  with socket.create_connection(('127.0.0.1',port),2) as s:s.sendall(b'GET /probe HTTP/1.1\r\nHost: slow\r\n');time.sleep(1.3)
  output,error=child.communicate(timeout=8);report=json.loads(output);validate_report(report)
  check('clean_expiry',child.returncode==0 and report['status']=='EXPIRED_CLOSED' and report['after']=={'tcp4':0,'tcp6':0})
  check('no_secret_output','sentinel-SECRET' not in output+error and error=='')
  c=report['counters']
  check('tcp_and_methods',c['accepted_tcp']>=9 and c['method_counts']['GET']>=3 and all(c['method_counts'][k]>=1 for k in ('HEAD','POST','OPTIONS','OTHER')))
  check('parser_and_timeout',c['parse_error_count']>=1 and c['read_timeout_count']>=1)
  check('local_separate',report['local_selfcheck_http'] and report['http_classification']['probe_get']==1 and report['http_classification']['root_get']==1)
  invalid=json.loads(output);invalid['counters']['accepted_tcp']='SECRET'
  try:validate_report(invalid);ok=False
  except AssertionError:ok=True
  check('reject_non_numeric_telemetry',ok)
 finally:
  if child.poll() is None:child.kill();child.wait()
 blocker=socket.socket();blocker.bind(('0.0.0.0',0));blocker.listen(1);port=blocker.getsockname()[1]
 try:
  run=subprocess.run([sys.executable,'-c',remote_source(marker,port,2)],capture_output=True,text=True,timeout=4)
  report=json.loads(run.stdout);validate_report(report)
  check('bind_conflict_refused',run.returncode==2 and report['status']=='PORT_CONFLICT' and not report['bound'])
 finally:blocker.close()
 pathlib.Path('out').mkdir(exist_ok=True);pathlib.Path('out/v6-local-tests.json').write_text(json.dumps({'status':'PASS','tests':checks}))
 print('PASS v6 integrated diagnostics',len(checks),'tests')
if __name__=='__main__':test()
