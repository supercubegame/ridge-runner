"""One approved capability-only command; no traffic observation or endpoint writes."""
import ast,base64,contextlib,http.client,json,logging,os,pathlib,shlex,subprocess,sys,time
import runtime_trial as b
BRANCH='audit/net-capability-once-20260920'
CLAIM='claims/net-capability-once-20260920-1717.json'
TEAM='01hrhh1avmp22zbv37depwjkp8'
REMOTE=r'''import json,os,shutil,signal,time
start=time.monotonic()
def expired(*a):os._exit(124)
signal.signal(signal.SIGALRM,expired);signal.alarm(10)
caps={}
with open('/proc/self/status') as stream:
 for line in stream:
  name,_,value=line.partition(':')
  if name in ('CapEff','CapBnd'):caps[name]=int(value.strip(),16)
assert set(caps)=={'CapEff','CapBnd'}
data={'uid_class':'ROOT' if os.getuid()==0 else 'NON_ROOT','euid_class':'ROOT' if os.geteuid()==0 else 'NON_ROOT','capabilities':{name:{'effective':bool(caps['CapEff']&(1<<bit)),'bounding':bool(caps['CapBnd']&(1<<bit))} for name,bit in [('CAP_NET_ADMIN',12),('CAP_NET_RAW',13)]},'tools':{name:shutil.which(name,path='/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin') is not None for name in ('tcpdump','ss','ip','timeout')},'elapsed_seconds':round(time.monotonic()-start,6)}
print(json.dumps(data,sort_keys=True),flush=True)
'''
def validate(data):
 assert set(data)=={'uid_class','euid_class','capabilities','tools','elapsed_seconds'}
 assert data['uid_class'] in ('ROOT','NON_ROOT') and data['euid_class'] in ('ROOT','NON_ROOT')
 assert set(data['capabilities'])=={'CAP_NET_ADMIN','CAP_NET_RAW'}
 for value in data['capabilities'].values():
  assert set(value)=={'effective','bounding'} and all(type(v) is bool for v in value.values())
 assert set(data['tools'])=={'tcpdump','ss','ip','timeout'} and all(type(v) is bool for v in data['tools'].values())
 assert type(data['elapsed_seconds']) in (int,float) and 0<=data['elapsed_seconds']<15
def scope():
 b.require(os.environ['GITHUB_REPOSITORY']=='supercubegame/ridge-runner' and os.environ['GITHUB_REF']=='refs/heads/'+BRANCH and os.environ['GITHUB_RUN_ATTEMPT']=='1','SCOPE')
def claim():
 scope();data={'sha':os.environ['GITHUB_SHA'],'run_id':os.environ['GITHUB_RUN_ID'],'at':b.now(),'approval':'17:17 one max15s command; own UID/effective+bounding NET_RAW/NET_ADMIN bits and tcpdump/ss/ip/timeout availability only; no capture/raw sockets/network/bind/install/escalation/environment/other process cmdline/endpoint changes/lifecycle; abort unless Running'}
 b.github('PUT','/contents/'+CLAIM,{'branch':'studio-results','message':'Claim one 17:17 capability-only command','content':base64.b64encode(json.dumps(data).encode()).decode()})
 read=b.github('GET','/contents/'+CLAIM+'?ref=studio-results')
 b.require(json.loads(base64.b64decode(read['content']))==data,'CLAIM_READBACK')
 pathlib.Path('out').mkdir(exist_ok=True);pathlib.Path('out/net-capability-claim.json').write_text(json.dumps(data))
def test():
 b.test()
 tree=ast.parse(REMOTE)
 imports={a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names}
 assert imports=={'json','os','shutil','signal','time'}
 assert all(x not in REMOTE for x in ('environ','socket','subprocess','os.system','exec(','eval('))
 opened=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='open']
 assert len(opened)==1 and ast.literal_eval(opened[0].args[0])=='/proc/self/status' and len(opened[0].args)==1
 run=subprocess.run([sys.executable,'-c',REMOTE],env={'PATH':'/usr/local/bin:/usr/bin:/bin'},capture_output=True,text=True,timeout=15)
 assert run.returncode==0 and not run.stderr;data=json.loads(run.stdout);validate(data)
 data['tools']['tcpdump']='sentinel-SECRET'
 try:validate(data)
 except AssertionError:pass
 else:raise AssertionError('nonboolean telemetry accepted')
 p=b.Policy();p.routes['command']=('POST','/command');p.armed='command';p.check('POST','lightning.ai','/command')
 try:p.armed='command';p.check('POST','lightning.ai','/command')
 except RuntimeError:pass
 else:raise AssertionError('replay')
 print('PASS capability-only source, local command, output schema and one-command replay guard')
def execute():
 import urllib3.connection
 p=b.Policy();original=http.client.HTTPConnection.putrequest
 r={'kind':'approved_network_capability_preflight','status':'FAIL','started_at_utc':b.now(),'remote_alarm_seconds':10,'approved_max_seconds':15,'capture':'NOT_RUN','raw_sockets':'NOT_OPENED','endpoint_changes':'NOT_RUN','public_requests':'NOT_RUN','studio_lifecycle':'NOT_RUN'}
 stage='scope'
 def save():
  r['network']={'get':p.gets,'writes':p.writes,'blocked':p.blocked};r['last_stage']=stage
  text=json.dumps(r,indent=2)
  assert not any(os.environ.get(k) and os.environ[k] in text for k in ('LIGHTNING_USER_ID','LIGHTNING_API_KEY'))
  pathlib.Path('out').mkdir(exist_ok=True);pathlib.Path('out/studio-probe.json').write_text(text+'\n')
 def guard(conn,method,url,*a,**kw):
  b.require(isinstance(conn,(http.client.HTTPSConnection,urllib3.connection.HTTPSConnection)),'HTTPS_TRANSPORT')
  p.check(method,conn.host,url);return original(conn,method,url,*a,**kw)
 try:
  scope();receipt=json.loads(pathlib.Path('out/net-capability-claim.json').read_text())
  b.require(receipt['sha']==os.environ['GITHUB_SHA'] and receipt['run_id']==os.environ['GITHUB_RUN_ID'],'CLAIM')
  b.require(all(os.environ.get(k) for k in ('LIGHTNING_USER_ID','LIGHTNING_API_KEY')),'CREDENTIALS')
  os.environ['LIGHTNING_DEBUG']='0';os.environ['LIGHTNING_DISABLE_VERSION_CHECK']='1';logging.disable(logging.CRITICAL)
  with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):
   http.client.HTTPConnection.putrequest=guard
   from lightning_sdk import Studio
   from lightning_sdk.api.studio_api import StudioApi
   from lightning_sdk.lightning_cloud.openapi import CloudSpaceServiceApi,CloudSpaceServiceExecuteCommandInCloudSpaceBody
   Studio._setup=lambda s:None
   def forbidden(*a,**kw):raise RuntimeError('KEEPALIVE_REFUSED')
   StudioApi.start_keeping_alive=forbidden
   stage='preflight'
   s=Studio(name='peaceful-dewdney-424',teamspace='vision-model',org='hopkinsrandy537-org',create_ok=False)
   b.require(s._studio.id==b.SID and s._teamspace.id==TEAM,'IDENTITY')
   cloud=CloudSpaceServiceApi(s._studio_api._client.api_client)
   state=cloud.cloud_space_service_get_cloud_space_instance_status(project_id=TEAM,id=b.SID,_request_timeout=(5,15))
   r['preflight']={'running':bool(state.in_use and state.in_use.phase=='CLOUD_SPACE_INSTANCE_STATE_RUNNING'),'requested_present':state.requested is not None}
   b.require(r['preflight']['running'] and not r['preflight']['requested_present'],'NOT_STABLE_RUNNING')
   p.routes['command']=b.route(CloudSpaceServiceApi.cloud_space_service_execute_command_in_cloud_space_with_http_info,TEAM,b.SID)
   stage='submit_once';save();p.armed='command'
   command='exec env -i PATH=/usr/local/bin:/usr/bin:/bin python3 -c '+shlex.quote(REMOTE)
   result=cloud.cloud_space_service_execute_command_in_cloud_space(CloudSpaceServiceExecuteCommandInCloudSpaceBody(command,detached=True),project_id=TEAM,id=b.SID,_request_timeout=(5,20))
   b.require(result and result.session_name,'UNCONFIRMED_NO_REPLAY')
   stage='wait_exit';deadline=time.monotonic()+40;session=result.session_name
   while time.monotonic()<deadline:
    output=cloud.cloud_space_service_get_long_running_command_in_cloud_space(project_id=TEAM,id=b.SID,session=session,_request_timeout=(5,10))
    if output.exit_code is not None and output.exit_code!=-1:
     r['remote_exit_code']=output.exit_code
     b.require(output.exit_code==0,'REMOTE_NONZERO')
     data=json.loads(output.output);validate(data);r['capability_readback']=data
     r['status']='PASS';break
    time.sleep(1)
   b.require(r['status']=='PASS','COMMAND_EXIT_UNCONFIRMED')
 except Exception as e:
  r['error_type']=type(e).__name__
  if type(e) is RuntimeError and str(e).isupper():r['error_code']=str(e)
  if isinstance(getattr(e,'status',None),int):r['http_status']=e.status
 finally:
  http.client.HTTPConnection.putrequest=original;r['finished_at_utc']=b.now();save();print('Capability preflight:',r['status'])
 return 0 if r['status']=='PASS' else 1
if __name__=='__main__':
 if '--self-test' in sys.argv:test()
 elif '--claim' in sys.argv:claim()
 else:sys.exit(execute())
