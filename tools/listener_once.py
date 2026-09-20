"""One approved runtime read of /proc/net/tcp{,6}; no bind, secrets, or process control."""
import ast,base64,contextlib,datetime,http.client,inspect,json,logging,os,pathlib,shlex,sys,textwrap,time,urllib.parse,urllib.request
import endpoint_readonly as m
BRANCH='audit/listener-once-20260920'
CLAIM='claims/listener-inspection-20260920-1104.json'
REMOTE='''import json
out={'schema':1,'scope':'command_process_network_namespace','ports':{'8060':{'tcp4':0,'tcp6':0},'8061':{'tcp4':0,'tcp6':0}},'tables':{}}
for family,path in [('tcp4','/proc/net/tcp'),('tcp6','/proc/net/tcp6')]:
 try:
  with open(path) as stream:lines=stream.read().splitlines()[1:]
  for line in lines:
   fields=line.split()
   if len(fields)<4:raise ValueError('MALFORMED_TABLE')
   if fields[3]!='0A':continue
   port=str(int(fields[1].rsplit(':',1)[1],16))
   if port in out['ports']:out['ports'][port][family]+=1
  out['tables'][family]='READ'
 except FileNotFoundError:out['tables'][family]='UNAVAILABLE'
 except Exception:out['tables'][family]='READ_FAILED'
print(json.dumps(out,sort_keys=True))
'''
COMMAND='python3 -c '+shlex.quote(REMOTE)
def require(ok,code):
 if not ok:raise RuntimeError(code)
def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def parse_output(text):
 value=json.loads(text)
 require(set(value)=={'schema','scope','ports','tables'},'OUTPUT_FIELDS')
 require(value['schema']==1 and value['scope']=='command_process_network_namespace','OUTPUT_SCOPE')
 require(set(value['ports'])=={'8060','8061'} and set(value['tables'])=={'tcp4','tcp6'},'OUTPUT_PORTS')
 for family in ('tcp4','tcp6'):
  require(value['tables'][family] in ('READ','UNAVAILABLE','READ_FAILED'),'TABLE_STATE')
 for port in ('8060','8061'):
  require(set(value['ports'][port])=={'tcp4','tcp6'},'FAMILY_FIELDS')
  require(all(type(v) is int and 0<=v<=100000 for v in value['ports'][port].values()),'COUNTS')
 return value
class Policy:
 def __init__(self):self.route=None;self.armed=False;self.gets=0;self.posts=0;self.blocked=0
 def check(self,method,host,url):
  try:
   if method=='GET':m.check_request(method,host,url);self.gets+=1;return
   u=urllib.parse.urlsplit(url);actual=u.hostname if u.scheme else host.split(':')[0]
   require(not u.scheme or u.scheme=='https','HTTPS_ONLY')
   require(actual in ('lightning.ai','api.lightning.ai'),'HOST')
   require(method=='POST' and self.armed and self.posts==0 and u.path==self.route and not u.query,'ONLY_ONE_COMMAND_POST')
   self.posts+=1;self.armed=False
  except Exception:self.blocked+=1;raise

def github(method,path,data=None):
 req=urllib.request.Request('https://api.github.com/repos/supercubegame/ridge-runner'+path,method=method,data=None if data is None else json.dumps(data).encode(),headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json'})
 with urllib.request.urlopen(req,timeout=30) as r:return json.load(r)
def claim():
 require(os.environ['GITHUB_REF']=='refs/heads/'+BRANCH and os.environ['GITHUB_RUN_ATTEMPT']=='1','CLAIM_SCOPE')
 data={'run_id':os.environ['GITHUB_RUN_ID'],'sha':os.environ['GITHUB_SHA'],'approved':'one runtime listener read only','at':stamp()}
 github('PUT','/contents/'+CLAIM,{'branch':'studio-results','message':'Claim single approved listener inspection','content':base64.b64encode(json.dumps(data).encode()).decode()})
 live=github('GET','/contents/'+CLAIM+'?ref=studio-results')
 require(json.loads(base64.b64decode(live['content']))==data,'CLAIM_READBACK')
 pathlib.Path('out').mkdir(exist_ok=True);pathlib.Path('out/listener-claim.json').write_text(json.dumps(data))
def test():
 import subprocess
 m.selftest()
 result=subprocess.run([sys.executable,'-c',REMOTE],capture_output=True,text=True,timeout=5)
 require(result.returncode==0 and not result.stderr,'LOCAL_PROC_READ')
 parse_output(result.stdout)
 try:parse_output('{"unexpected":"sentinel-secret"}')
 except RuntimeError:pass
 else:raise AssertionError('OUTPUT_NOT_RESTRICTED')
 for method,path in [('POST','/start'),('POST','/stop'),('PUT','/endpoint'),('DELETE','/endpoint')]:
  p=Policy();p.route='/execute';p.armed=True
  try:p.check(method,'lightning.ai',path)
  except RuntimeError:pass
  else:raise AssertionError('WRITE_ACCEPTED')
 p=Policy();p.route='/execute';p.armed=True;p.check('POST','lightning.ai','/execute');p.armed=True
 try:p.check('POST','lightning.ai','/execute')
 except RuntimeError:pass
 else:raise AssertionError('REPLAY_ACCEPTED')
 tree=ast.parse(REMOTE)
 require({n.name for a in ast.walk(tree) if isinstance(a,ast.Import) for n in a.names}=={'json'},'REMOTE_IMPORTS')
 require('socket' not in REMOTE and 'subprocess' not in REMOTE and 'environ' not in REMOTE,'REMOTE_SCOPE')
 print('PASS local proc read, output schema, forbidden writes and replay checks')
def execute():
 import urllib3.connection
 p=Policy();original=http.client.HTTPConnection.putrequest;stage='scope'
 report={'status':'FAIL','kind':'approved_listener_inspection_once','ssh':'NOT_USED','start_stop':'NOT_RUN','bind':'NOT_RUN','public_preview':'NOT_REQUESTED','started_at_utc':stamp()}
 def guard(conn,method,url,*a,**kw):
  require(isinstance(conn,(http.client.HTTPSConnection,urllib3.connection.HTTPSConnection)),'HTTPS_TRANSPORT')
  p.check(method,conn.host,url);return original(conn,method,url,*a,**kw)
 try:
  require(os.environ['GITHUB_REF']=='refs/heads/'+BRANCH and os.environ['GITHUB_RUN_ATTEMPT']=='1','RUN_SCOPE')
  receipt=json.loads(pathlib.Path('out/listener-claim.json').read_text())
  require(receipt['sha']==os.environ['GITHUB_SHA'] and receipt['run_id']==os.environ['GITHUB_RUN_ID'],'RECEIPT')
  require(all(os.environ.get(k) for k in ('LIGHTNING_USER_ID','LIGHTNING_API_KEY')),'CREDENTIALS')
  os.environ['LIGHTNING_DEBUG']='0';os.environ['LIGHTNING_DISABLE_VERSION_CHECK']='1';logging.disable(logging.CRITICAL)
  with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):
   http.client.HTTPConnection.putrequest=guard
   from lightning_sdk import Studio
   from lightning_sdk.api.studio_api import StudioApi
   from lightning_sdk.lightning_cloud.openapi import CloudSpaceServiceApi,CloudSpaceServiceExecuteCommandInCloudSpaceBody
   Studio._setup=lambda s:None
   def forbidden(*a,**k):raise RuntimeError('KEEPALIVE_REFUSED')
   StudioApi.start_keeping_alive=forbidden
   stage='preflight';s=Studio(name='peaceful-dewdney-424',teamspace='vision-model',org='hopkinsrandy537-org',create_ok=False)
   sid=s._studio.id;team=s._teamspace.id;require(sid=='01m2watakghqmc1fnymkg5czax','TARGET')
   client=s._studio_api._client
   state=client.cloud_space_service_get_cloud_space_instance_status(project_id=team,id=sid,_request_timeout=(10,30))
   require(state.requested is None and state.in_use is not None and state.in_use.phase=='CLOUD_SPACE_INSTANCE_STATE_RUNNING','NOT_STABLE_RUNNING')
   report['preflight']='STABLE_RUNNING'
   tree=ast.parse(textwrap.dedent(inspect.getsource(CloudSpaceServiceApi.cloud_space_service_execute_command_in_cloud_space_with_http_info)))
   calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='call_api'];require(len(calls)==1,'ROUTE_COUNT')
   path,verb=[ast.literal_eval(n) for n in calls[0].args[:2]];require(verb=='POST','ROUTE_VERB')
   for key,value in {'projectId':team,'project_id':team,'id':sid}.items():path=path.replace('{'+key+'}',urllib.parse.quote(value,safe=''))
   require('{' not in path and sid in path and team in path,'ROUTE_TARGET');p.route=path
   body=CloudSpaceServiceExecuteCommandInCloudSpaceBody(COMMAND,detached=True)
   stage='submit_once';p.armed=True
   response=client.cloud_space_service_execute_command_in_cloud_space(body,project_id=team,id=sid,_request_timeout=(10,30))
   require(p.posts==1 and response and response.session_name,'SUBMISSION_UNCONFIRMED_NO_REPLAY')
   stage='read_command_result';deadline=time.monotonic()+90;done=False
   while time.monotonic()<deadline:
    result=client.cloud_space_service_get_long_running_command_in_cloud_space(project_id=team,id=sid,session=response.session_name,_request_timeout=(10,15))
    if result.exit_code is not None and result.exit_code!=-1:
     report['exit_code']=result.exit_code;require(result.exit_code==0,'COMMAND_FAILED')
     report['listeners']=parse_output(result.output);done=True;break
    time.sleep(2)
   require(done,'RESULT_TIMEOUT_NO_REPLAY')
   require(p.blocked==0,'REQUEST_BLOCKED')
   report['status']='PASS' if all(v=='READ' for v in report['listeners']['tables'].values()) else 'PARTIAL'
 except Exception as e:
  report['error_type']=type(e).__name__
  if isinstance(getattr(e,'status',None),int):report['http_status']=e.status
 finally:
  http.client.HTTPConnection.putrequest=original
  report['last_stage']=stage;report['observed_at_utc']=stamp();report['network']={'get':p.gets,'command_posts':p.posts,'blocked':p.blocked}
  text=json.dumps(report,indent=2)
  for key in ('LIGHTNING_USER_ID','LIGHTNING_API_KEY'):
   require(not os.environ.get(key) or os.environ[key] not in text,'SECRET_OUTPUT')
  pathlib.Path('out').mkdir(exist_ok=True);pathlib.Path('out/studio-probe.json').write_text(text+'\n');print(report['status'],stage)
 return 0 if report['status']=='PASS' else 1
if __name__=='__main__':
 if '--self-test' in sys.argv:test()
 elif '--claim' in sys.argv:claim()
 else:sys.exit(execute())
