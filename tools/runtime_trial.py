"""One approved temporary authenticated endpoint trial; never start/stop Studio."""
import ast,base64,contextlib,copy,datetime,hashlib,http.client,inspect,json,logging,os,pathlib,secrets,shlex,sys,textwrap,time,urllib.error,urllib.parse,urllib.request
import endpoint_readonly as m
BRANCH='audit/runtime-trial-8061-20260920'
CLAIM='claims/runtime-trial-8061-20260920-1114.json'
SID='01m2watakghqmc1fnymkg5czax'
NAME='ridge-autowake-probe-8061'
ORIGINAL='https://8060-'+SID+'.cloudspaces.litng.ai'
VERSION={'game':'ridge-runner','release':'playtest-35445091317-1','archive_sha256':'ad73d9ba67b3cf31f5c9ab57c84d1eeeb74653f748a73d76b5dc32c9b36192f5'}
REMOTE=r'''import http.server,json,signal,time
PORT=__PORT__
LIFETIME=__LIFETIME__
MARKER=__MARKER__.encode()
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
class Server(http.server.HTTPServer):
 allow_reuse_address=False
 def get_request(self):
  sock,address=super().get_request();sock.settimeout(1);return sock,address
class Handler(http.server.BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def do_GET(self):
  if self.path!='/probe':
   self.send_response(404);self.send_header('Content-Length','0');self.end_headers();return
  self.send_response(200);self.send_header('Content-Type','application/json')
  self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(MARKER)))
  self.end_headers();self.wfile.write(MARKER)
server=None;report={'status':'FAIL','bound':False,'lifetime_seconds':LIFETIME};start=time.monotonic();exit_code=2
signal.signal(signal.SIGALRM,expire);signal.alarm(LIFETIME)
try:
 report['before']=counts()
 if any(report['before'].values()):raise RuntimeError('PORT_OCCUPIED')
 server=Server(('0.0.0.0',PORT),Handler);server.timeout=.2;report['bound']=True
 while True:server.handle_request()
except Expired:
 report['status']='EXPIRED_CLOSED' if report['bound'] else 'EXPIRED_BEFORE_BIND';exit_code=0 if report['bound'] else 2
except BaseException as e:
 report['error_type']=type(e).__name__
finally:
 signal.alarm(0)
 if server:server.server_close()
 report['after']=counts();report['elapsed_seconds']=round(time.monotonic()-start,3)
 print(json.dumps(report,sort_keys=True),flush=True)
raise SystemExit(exit_code)
'''
def remote_source(port=8061,lifetime=100,marker='{"probe":"fixture"}'):
 require(type(port) is int and 1<=port<=65535 and type(lifetime) is int and 1<=lifetime<=150,'REMOTE_ARGS')
 return REMOTE.replace('__PORT__',str(port)).replace('__LIFETIME__',str(lifetime)).replace('__MARKER__',repr(marker))
def require(ok,code):
 if not ok:raise RuntimeError(code)
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*a,**k):return None
def request(url,authorization=None):
 headers={'Cache-Control':'no-cache'}
 if authorization:headers['Authorization']=authorization
 req=urllib.request.Request(url,headers=headers)
 try:
  with urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect()).open(req,timeout=10) as r:return r.status,r.read(4097)
 except urllib.error.HTTPError as e:return e.code,e.read(4097)
class Policy:
 def __init__(self):
  self.routes={};self.armed=None;self.writes={'create':0,'command':0,'delete':0};self.gets=0;self.blocked=0
  self.hosts={'lightning.ai','api.lightning.ai',urllib.parse.urlsplit(ORIGINAL).hostname}
 def check(self,method,host,url):
  try:
   u=urllib.parse.urlsplit(url);actual=u.hostname if u.scheme else host.split(':')[0]
   require(not u.scheme or u.scheme=='https','HTTPS_ONLY')
   require(actual in self.hosts,'HOST')
   require(not any(v in u.path.lower() for v in ('keepalive','keep-alive','keep_alive','report-stop-at')),'KEEPALIVE')
   if method=='GET':self.gets+=1;return
   kind=self.armed
   require(actual in ('lightning.ai','api.lightning.ai') and kind in self.routes and self.routes[kind]==(method,u.path) and not u.query,'WRITE_ROUTE')
   require(self.writes[kind]==0,'WRITE_REPLAY')
   self.writes[kind]+=1;self.armed=None
  except Exception:self.blocked+=1;raise
 def unused(self):pass
def route(fn,team,target=None):
 tree=ast.parse(textwrap.dedent(inspect.getsource(fn)))
 calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='call_api']
 require(len(calls)==1,'ROUTE_COUNT')
 path,verb=[ast.literal_eval(n) for n in calls[0].args[:2]]
 for key,value in {'projectId':team,'project_id':team,'id':target}.items():
  if value:path=path.replace('{'+key+'}',urllib.parse.quote(value,safe=''))
 require('{' not in path and team in path,'ROUTE_IDENTITY')
 return verb,path
def owned(e,endpoint_id,team,original_id):
 return bool(endpoint_id and endpoint_id!=original_id and e.id==endpoint_id and e.project_id==team and e.name==NAME and
  [str(v) for v in e.ports]==['8061'] and e.cloudspace and e.cloudspace.cloudspace_id==SID and str(e.cloudspace.port)=='8061')
def github(method,path,data=None):
 req=urllib.request.Request('https://api.github.com/repos/supercubegame/ridge-runner'+path,method=method,
  data=None if data is None else json.dumps(data).encode(),headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json'})
 with urllib.request.urlopen(req,timeout=30) as r:return json.load(r)
def claim():
 require(os.environ['GITHUB_REF']=='refs/heads/'+BRANCH and os.environ['GITHUB_RUN_ATTEMPT']=='1','CLAIM_SCOPE')
 data={'run_id':os.environ['GITHUB_RUN_ID'],'sha':os.environ['GITHUB_SHA'],'approved':'one temporary basic-auth 8061 trial and exact new endpoint deletion; no Studio lifecycle changes','at':now()}
 github('PUT','/contents/'+CLAIM,{'branch':'studio-results','message':'Claim one approved temporary 8061 trial','content':base64.b64encode(json.dumps(data).encode()).decode()})
 live=github('GET','/contents/'+CLAIM+'?ref=studio-results')
 require(json.loads(base64.b64decode(live['content']))==data,'CLAIM_READBACK')
 pathlib.Path('out').mkdir(exist_ok=True);pathlib.Path('out/runtime-claim.json').write_text(json.dumps(data))
def execute():
 import urllib3.connection
 p=Policy();original=http.client.HTTPConnection.putrequest
 r={'status':'FAIL','kind':'approved_8061_runtime_trial','started_at_utc':now(),'checks':[],
  'auto_wake':'NOT_RUN','studio_start_stop':'NOT_RUN','ssh':'NOT_USED','cleanup':{},'service_lifetime_seconds':100}
 stage='scope';eid=None;session=None;client=None;team=None;original_id=None;original_snapshot=None;config_snapshot=None
 username='probe-'+secrets.token_hex(8);password=secrets.token_urlsafe(32)
 authorization='Basic '+base64.b64encode((username+':'+password).encode()).decode()
 marker=json.dumps({'probe':'ridge-autowake-runtime','nonce':secrets.token_hex(16)},sort_keys=True)
 secret_values=[username,password,authorization]+[os.environ.get(k,'') for k in ('LIGHTNING_USER_ID','LIGHTNING_API_KEY')]
 def record(name):r['checks'].append({'name':name,'pass':True})
 def save():
  r['network']={'get':p.gets,'writes':p.writes,'blocked':p.blocked};r['last_stage']=stage
  text=json.dumps(r,indent=2)
  require(not any(v and v in text for v in secret_values),'SECRET_OUTPUT')
  pathlib.Path('out').mkdir(exist_ok=True);pathlib.Path('out/studio-probe.json').write_text(text+'\n')
 def guard(conn,method,url,*a,**kw):
  require(isinstance(conn,(http.client.HTTPSConnection,urllib3.connection.HTTPSConnection)),'HTTPS_TRANSPORT')
  p.check(method,conn.host,url);return original(conn,method,url,*a,**kw)
 def inspect_service():
  if not session:return
  deadline=time.monotonic()+160
  while time.monotonic()<deadline:
   result=client.cloud_space_service_get_long_running_command_in_cloud_space(project_id=team,id=SID,session=session,_request_timeout=(5,15))
   if result.exit_code is not None and result.exit_code!=-1:
    report=json.loads(result.output)
    require(set(report)<= {'status','bound','lifetime_seconds','before','after','elapsed_seconds','error_type'},'REMOTE_OUTPUT')
    r['service']={'exit_code':result.exit_code,**report}
    r['cleanup']['service_finished']=True
    r['cleanup']['8061_no_listeners_after']=report.get('after')=={'tcp4':0,'tcp6':0}
    return
   time.sleep(3)
  r['cleanup']['service_finished']=False
 try:
  require(os.environ['GITHUB_REPOSITORY']=='supercubegame/ridge-runner' and os.environ['GITHUB_REF']=='refs/heads/'+BRANCH and os.environ['GITHUB_RUN_ATTEMPT']=='1','RUN_SCOPE')
  receipt=json.loads(pathlib.Path('out/runtime-claim.json').read_text())
  require(receipt['sha']==os.environ['GITHUB_SHA'] and receipt['run_id']==os.environ['GITHUB_RUN_ID'],'RECEIPT')
  require(all(os.environ.get(k) for k in ('LIGHTNING_USER_ID','LIGHTNING_API_KEY')),'CREDENTIALS')
  os.environ['LIGHTNING_DEBUG']='0';os.environ['LIGHTNING_DISABLE_VERSION_CHECK']='1';logging.disable(logging.CRITICAL)
  with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):
   http.client.HTTPConnection.putrequest=guard
   try:
    from lightning_sdk import Studio
    from lightning_sdk.api.studio_api import StudioApi
    from lightning_sdk.lightning_cloud.openapi import CloudSpaceServiceApi,EndpointServiceApi,EndpointServiceCreateEndpointBody,V1EndpointAuth,V1UpstreamCloudSpace,V1EndpointType,CloudSpaceServiceExecuteCommandInCloudSpaceBody
    Studio._setup=lambda s:None
    def forbidden(*a,**k):raise RuntimeError('KEEPALIVE_REFUSED')
    StudioApi.start_keeping_alive=forbidden
    stage='preflight'
    s=Studio(name='peaceful-dewdney-424',teamspace='vision-model',org='hopkinsrandy537-org',create_ok=False)
    require(s._studio.id==SID,'TARGET');team=s._teamspace.id;client=s._studio_api._client
    kw={'project_id':team,'id':SID,'_request_timeout':(5,20)}
    state=client.cloud_space_service_get_cloud_space_instance_status(**kw)
    require(state.requested is None and state.in_use is not None and state.in_use.phase=='CLOUD_SPACE_INSTANCE_STATE_RUNNING','NOT_STABLE_RUNNING')
    cfg=client.cloud_space_service_get_cloud_space_instance_config(**kw)
    require(cfg.compute_config.name=='cpu-4' and cfg.compute_config.spot is False and cfg.disable_auto_shutdown is False and cfg.idle_shutdown_seconds==0,'CONFIG_DRIFT')
    config_snapshot=(copy.deepcopy(cfg.compute_config.to_dict()),cfg.disable_auto_shutdown,cfg.idle_shutdown_seconds)
    endpoints=s.list_ports()
    require(not any(e.name==NAME or '8061' in [str(v) for v in (e.ports or [])] for e in endpoints),'ENDPOINT_CONFLICT')
    originals=[e for e in endpoints if '8060' in [str(v) for v in (e.ports or [])]]
    require(len(originals)==1,'ORIGINAL_COUNT');original_id=originals[0].id
    original_endpoint=client.endpoint_service_get_endpoint(project_id=team,ref=original_id,_request_timeout=(5,20))
    require(original_endpoint.cloudspace.auto_start is False,'ORIGINAL_AUTOSTART')
    original_snapshot=copy.deepcopy(original_endpoint.to_dict())
    code,body=request(ORIGINAL+'/version.json');require(code==200 and json.loads(body)==VERSION,'ORIGINAL_VERSION')
    record('preflight_original_cpu_and_game')
    p.routes['create']=route(EndpointServiceApi.endpoint_service_create_endpoint_with_http_info,team)
    p.routes['command']=route(CloudSpaceServiceApi.cloud_space_service_execute_command_in_cloud_space_with_http_info,team,SID)
    stage='create_once';save()
    body=EndpointServiceCreateEndpointBody(name=NAME,ports=['8061'],
     auth=V1EndpointAuth(enabled=True,username=username,password=password,user_api_key=False),
     cloudspace=V1UpstreamCloudSpace(cloudspace_id=SID,port='8061',auto_start=False,instance_type='cpu-4',command='',type=V1EndpointType.PLUGIN_API))
    p.armed='create'
    created=client.endpoint_service_create_endpoint(body=body,project_id=team,_request_timeout=(5,25))
    require(created.id and created.id!=original_id,'CREATE_ID');eid=created.id
    r['created_endpoint_id']=eid
    require(owned(created,eid,team,original_id),'CREATED_IDENTITY')
    p.routes['delete']=route(EndpointServiceApi.endpoint_service_delete_endpoint_with_http_info,team,eid)
    stage='auth_config_readback';save()
    live=client.endpoint_service_get_endpoint(project_id=team,ref=eid,_request_timeout=(5,20))
    require(owned(live,eid,team,original_id),'READBACK_IDENTITY')
    require(live.cloudspace.auto_start is False and not live.cloudspace.command,'NO_AUTOSTART_COMMAND')
    require(live.auth is not None and live.auth.enabled is True and live.auth.username==username and not live.auth.user_api_key and not live.auth.token and not live.auth.tokens,'BASIC_CONFIG')
    require(len(live.urls)==1,'URL_COUNT');url=live.urls[0].rstrip('/')
    u=urllib.parse.urlsplit(url)
    require(u.scheme=='https' and u.hostname and not u.username and not u.password and not u.query and not u.fragment and u.path in ('','/') and u.hostname.endswith(('.cloudspaces.litng.ai','.lightning.ai','.lightningapp.ai')),'URL_SCOPE')
    p.hosts.add(u.hostname);r['endpoint_url']=url;record('basic_auth_and_autostart_false_readback')
    stage='auth_before_service'
    for label,auth in [('missing',None),('wrong','Basic '+base64.b64encode(b'wrong:wrong').decode())]:
     code,data=request(url+'/probe',auth);r[label+'_before_status']=code
     require(code in (401,403) and marker.encode() not in data,'AUTH_BEFORE_SERVICE')
    record('unauthenticated_requests_denied_before_binding')
    stage='start_short_lived_service';save()
    # This foreground process inherits no platform secrets and never writes files.
    command='exec env -i PATH=/usr/local/bin:/usr/bin:/bin python3 -c '+shlex.quote(remote_source(marker=marker))
    p.armed='command'
    submitted=client.cloud_space_service_execute_command_in_cloud_space(CloudSpaceServiceExecuteCommandInCloudSpaceBody(command,detached=True),project_id=team,id=SID,_request_timeout=(5,25))
    require(submitted and submitted.session_name,'COMMAND_UNCONFIRMED_NO_REPLAY');session=submitted.session_name
    stage='authenticated_request';deadline=time.monotonic()+40;ready=False
    while time.monotonic()<deadline:
     try:
      code,data=request(url+'/probe',authorization)
      if code==200 and data==marker.encode():ready=True;break
      if code in (401,403):raise RuntimeError('VALID_AUTH_REJECTED')
     except (urllib.error.URLError,TimeoutError):pass
     time.sleep(2)
    require(ready,'AUTHENTICATED_MARKER_NOT_VERIFIED');record('valid_basic_auth_exact_marker')
    for label,auth in [('missing',None),('wrong','Basic '+base64.b64encode(b'wrong:wrong').decode())]:
     code,data=request(url+'/probe',auth);r[label+'_running_status']=code
     require(code in (401,403) and marker.encode() not in data,'AUTH_RUNNING')
    record('missing_and_wrong_auth_denied_while_service_running')
    code,data=request(url+'/',authorization);require(code==404,'NO_FILE_LISTING');record('root_not_served')
    stage='wait_service_exit';inspect_service()
    require(r.get('service',{}).get('exit_code')==0 and r['service'].get('status')=='EXPIRED_CLOSED' and r['cleanup'].get('8061_no_listeners_after') is True,'SERVICE_CLEANUP')
    record('bounded_service_exited_and_listener_closed')
    r['trial_status']='PASS'
   finally:
    stage='cleanup_new_endpoint'
    if eid and client:
     try:
      live=client.endpoint_service_get_endpoint(project_id=team,ref=eid,_request_timeout=(5,20))
      require(owned(live,eid,team,original_id),'CLEANUP_TARGET_CHANGED')
      p.routes['delete']=route(EndpointServiceApi.endpoint_service_delete_endpoint_with_http_info,team,eid)
      p.armed='delete';client.endpoint_service_delete_endpoint(project_id=team,id=eid,_request_timeout=(5,25))
      try:
       client.endpoint_service_get_endpoint(project_id=team,ref=eid,_request_timeout=(5,20))
       r['cleanup']['endpoint_absent']=False
      except Exception as e:r['cleanup']['endpoint_absent']=getattr(e,'status',None)==404
     except Exception as e:r['cleanup']['endpoint_error_type']=type(e).__name__
    elif p.writes['create']:r['cleanup']['endpoint_identity_unconfirmed']=True
    if session and not r['cleanup'].get('service_finished'):
     try:inspect_service()
     except Exception as e:r['cleanup']['service_error_type']=type(e).__name__
    if client and original_snapshot is not None:
     try:
      after=client.endpoint_service_get_endpoint(project_id=team,ref=original_id,_request_timeout=(5,20))
      r['cleanup']['original_endpoint_unchanged']=after.to_dict()==original_snapshot
      cfg=client.cloud_space_service_get_cloud_space_instance_config(project_id=team,id=SID,_request_timeout=(5,20))
      r['cleanup']['machine_sleep_config_unchanged']=(cfg.compute_config.to_dict(),cfg.disable_auto_shutdown,cfg.idle_shutdown_seconds)==config_snapshot
      code,data=request(ORIGINAL+'/version.json')
      r['cleanup']['original_game_version_ok']=code==200 and json.loads(data)==VERSION
     except Exception as e:r['cleanup']['original_readback_error_type']=type(e).__name__
   required=['endpoint_absent','service_finished','8061_no_listeners_after','original_endpoint_unchanged','machine_sleep_config_unchanged','original_game_version_ok']
   r['status']='PASS' if r.get('trial_status')=='PASS' and all(r['cleanup'].get(k) is True for k in required) and p.blocked==0 else 'FAIL'
 except Exception as e:
  r['error_type']=type(e).__name__
  if isinstance(e,RuntimeError):r['error_code']=str(e) if str(e).isupper() else 'RUNTIME_ERROR'
  if isinstance(getattr(e,'status',None),int):r['http_status']=e.status
 finally:
  http.client.HTTPConnection.putrequest=original;r['finished_at_utc']=now();save()
  print('Trial:',r['status'],'writes:',p.writes)
 return 0 if r['status']=='PASS' else 1
def test():
 import socket,subprocess
 from types import SimpleNamespace as N
 m.selftest()
 for method,path in [('POST','/start'),('POST','/stop'),('PUT','/endpoint'),('DELETE','/original')]:
  p=Policy();p.routes['delete']=('DELETE','/new');p.armed='delete'
  try:p.check(method,'lightning.ai',path)
  except RuntimeError:pass
  else:raise AssertionError('WRITE_SCOPE')
 p=Policy();p.routes['create']=('POST','/endpoint');p.armed='create';p.check('POST','lightning.ai','/endpoint');p.armed='create'
 try:p.check('POST','lightning.ai','/endpoint')
 except RuntimeError:pass
 else:raise AssertionError('REPLAY')
 obj=N(id='new',project_id='team',name=NAME,ports=['8061'],cloudspace=N(cloudspace_id=SID,port='8061'))
 require(owned(obj,'new','team','original'),'OWNED')
 require(not owned(obj,'new','team','new'),'ORIGINAL_REFUSED')
 require(not owned(obj,'new','other','original'),'TEAM_REFUSED')
 obj.ports=['8060'];require(not owned(obj,'new','team','original'),'ORIGINAL_PORT_REFUSED')
 def free_port():
  with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
 port=free_port();source=remote_source(port,2)
 child=subprocess.Popen([sys.executable,'-c',source],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 try:
  time.sleep(.3)
  c=http.client.HTTPConnection('127.0.0.1',port,timeout=1);c.request('GET','/probe');res=c.getresponse();require(res.status==200 and res.read()==b'{"probe":"fixture"}','MARKER');c.close()
  # Slow partial request must not defeat SIGALRM lifetime.
  slow=socket.create_connection(('127.0.0.1',port));slow.sendall(b'GET /probe HTTP/1.1\r\n')
  out,err=child.communicate(timeout=4);slow.close()
  data=json.loads(out);require(child.returncode==0 and data['status']=='EXPIRED_CLOSED' and data['after']=={'tcp4':0,'tcp6':0},'LIFETIME')
 finally:
  if child.poll() is None:child.terminate();child.wait()
 with socket.socket() as blocker:
  blocker.bind(('0.0.0.0',0));blocker.listen();port=blocker.getsockname()[1]
  run=subprocess.run([sys.executable,'-c',remote_source(port,2)],capture_output=True,text=True,timeout=4)
  require(run.returncode==2 and not json.loads(run.stdout)['bound'],'CONFLICT_REFUSAL')
 require('environ' not in REMOTE and 'subprocess' not in REMOTE,'REMOTE_NO_SECRET_READ')
 print('PASS scope, replay, exact cleanup identity, real HTTP, slow-client lifetime and occupied-port tests')
if __name__=='__main__':
 if '--self-test' in sys.argv:test()
 elif '--claim' in sys.argv:claim()
 else:sys.exit(execute())
