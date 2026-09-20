"""Approved create-only endpoint receipt; no service or lifecycle operations."""
import ast,base64,contextlib,copy,datetime,http.client,inspect,json,logging,os,pathlib,secrets,sys,textwrap,urllib.parse,urllib.request
BRANCH='audit/ui-link-8061-20260920'
CLAIM='claims/ui-link-8061-20260920-1141.json'
SID='01m2watakghqmc1fnymkg5czax'
NAME='ridge-autowake-probe-8061'
def require(ok,code):
 if not ok:raise RuntimeError(code)
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
class Policy:
 def __init__(self):
  self.route=None;self.armed=False;self.creates=0;self.gets=0;self.blocked=0
 def check(self,method,host,url):
  try:
   u=urllib.parse.urlsplit(url);actual=u.hostname if u.scheme else host.split(':')[0]
   require(not u.scheme or u.scheme=='https','HTTPS_ONLY')
   require(actual in ('lightning.ai','api.lightning.ai'),'HOST')
   require(not any(x in u.path.lower() for x in ('keepalive','keep-alive','keep_alive','report-stop-at')),'KEEPALIVE')
   if method=='GET':self.gets+=1;return
   require(self.armed and method=='POST' and self.route==u.path and not u.query and self.creates==0,'WRITE_REFUSED')
   self.creates+=1;self.armed=False
  except Exception:self.blocked+=1;raise
def route(fn,team):
 tree=ast.parse(textwrap.dedent(inspect.getsource(fn)))
 calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='call_api']
 require(len(calls)==1,'ROUTE_COUNT')
 path,verb=[ast.literal_eval(n) for n in calls[0].args[:2]]
 require(verb=='POST' and path=='/v1/projects/{projectId}/endpoints','CREATE_ROUTE')
 return path.replace('{projectId}',urllib.parse.quote(team,safe=''))
def owned(e,eid,team,original):
 return bool(eid and eid!=original and e.id==eid and e.project_id==team and e.name==NAME and
  [str(x) for x in (e.ports or [])]==['8061'] and e.cloudspace and e.cloudspace.cloudspace_id==SID and str(e.cloudspace.port)=='8061')
def basic_ok(e,username):
 a=e.auth;c=e.cloudspace
 return bool(a and a.enabled is True and a.username==username and not a.user_api_key and not a.token and not a.tokens and
  c.auto_start is False and not c.command and c.instance_type=='cpu-4' and c.type=='ENDPOINT_PLUGIN_API')
def encode_report(r,private):
 text=json.dumps(r,indent=2)
 require(not any(v and v in text for v in private),'SECRET_OUTPUT')
 return text+'\n'
def selftest():
 from types import SimpleNamespace as N
 count=0
 def denied(fn):
  nonlocal count
  try:fn()
  except RuntimeError:count+=1;return
  raise AssertionError('EXPECTED_REFUSAL')
 for method,path in [('POST','/start'),('POST','/stop'),('POST','/execute'),('PUT','/v1/projects/team/endpoints'),('DELETE','/v1/projects/team/endpoints/new')]:
  p=Policy();p.route='/v1/projects/team/endpoints';p.armed=True;denied(lambda:p.check(method,'lightning.ai',path))
 p=Policy();p.route='/v1/projects/team/endpoints';p.armed=True;p.check('POST','lightning.ai',p.route);count+=1
 p.armed=True;denied(lambda:p.check('POST','lightning.ai',p.route))
 for method,host,path in [('GET','evil.example','/'),('GET','lightning.ai','/keepalive'),('GET','lightning.ai','http://lightning.ai/x')]:
  denied(lambda:p.check(method,host,path))
 p=Policy();p.check('GET','lightning.ai','/v1/projects/team/endpoints');require(p.gets==1,'GET');count+=1
 e=N(id='new',project_id='team',name=NAME,ports=['8061'],urls=[],cloudspace=N(cloudspace_id=SID,port='8061',auto_start=False,command='',instance_type='cpu-4',type='ENDPOINT_PLUGIN_API'),auth=N(enabled=True,username='sentinel-user',user_api_key=False,token=None,tokens=[]))
 require(owned(e,'new','team','original') and basic_ok(e,'sentinel-user'),'VALID_EMPTY_URLS');count+=1
 require(not owned(e,'new','team','new') and not owned(e,'new','wrong','original'),'OWNERSHIP');count+=1
 e.cloudspace.auto_start=True;require(not basic_ok(e,'sentinel-user'),'AUTOSTART');count+=1
 denied(lambda:encode_report({'password':'sentinel-password'},['sentinel-password']))
 require('sentinel-password' not in encode_report({'auth':'BASIC_ENABLED'},['sentinel-password']),'REDACTION');count+=1
 print('PASS',count,'create-only, replay, identity, empty-URL and redaction checks')
def github(method,path,data=None):
 req=urllib.request.Request('https://api.github.com/repos/supercubegame/ridge-runner'+path,method=method,data=None if data is None else json.dumps(data).encode(),headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json'})
 with urllib.request.urlopen(req,timeout=30) as r:return json.load(r)
def scope():
 require(os.environ['GITHUB_REPOSITORY']=='supercubegame/ridge-runner' and os.environ['GITHUB_REF']=='refs/heads/'+BRANCH and os.environ['GITHUB_RUN_ATTEMPT']=='1','SCOPE')
def claim():
 scope()
 data={'run_id':os.environ['GITHUB_RUN_ID'],'sha':os.environ['GITHUB_SHA'],'approval':'one Basic-auth 8061 endpoint; auto_start false; UI link only; no service/lifecycle; retain until user captures link','at':now()}
 github('PUT','/contents/'+CLAIM,{'branch':'studio-results','message':'Claim approved UI-only endpoint creation','content':base64.b64encode(json.dumps(data).encode()).decode()})
 live=github('GET','/contents/'+CLAIM+'?ref=studio-results')
 require(json.loads(base64.b64decode(live['content']))==data,'CLAIM_READBACK')
 pathlib.Path('out').mkdir(exist_ok=True);pathlib.Path('out/ui-link-claim.json').write_text(json.dumps(data))
def execute():
 import urllib3.connection
 p=Policy();original=http.client.HTTPConnection.putrequest
 username='probe-'+secrets.token_hex(8);password=secrets.token_urlsafe(32)
 private=[username,password]+[os.environ.get(k,'') for k in ('LIGHTNING_USER_ID','LIGHTNING_API_KEY')]
 r={'status':'FAIL','kind':'ui_link_create_only','started_at_utc':now(),'checks':[],'service':'NOT_STARTED','studio_lifecycle':'NOT_REQUESTED','cleanup':'WAITING_FOR_USER_LINK_CAPTURE','public_url':'NOT_INFERRED'}
 stage='scope'
 def save():
  r['last_stage']=stage;r['network']={'get':p.gets,'create':p.creates,'blocked':p.blocked,'delete':0,'command':0,'studio_start_stop':0}
  pathlib.Path('out').mkdir(exist_ok=True);pathlib.Path('out/studio-probe.json').write_text(encode_report(r,private))
 def guard(conn,method,url,*a,**k):
  require(isinstance(conn,(http.client.HTTPSConnection,urllib3.connection.HTTPSConnection)),'HTTPS_TRANSPORT')
  p.check(method,conn.host,url);return original(conn,method,url,*a,**k)
 try:
  scope();receipt=json.loads(pathlib.Path('out/ui-link-claim.json').read_text())
  require(receipt['sha']==os.environ['GITHUB_SHA'] and receipt['run_id']==os.environ['GITHUB_RUN_ID'],'CLAIM')
  require(all(os.environ.get(k) for k in ('LIGHTNING_USER_ID','LIGHTNING_API_KEY')),'CREDENTIALS')
  os.environ['LIGHTNING_DISABLE_VERSION_CHECK']='1';os.environ['LIGHTNING_DEBUG']='0';logging.disable(logging.CRITICAL)
  with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):
   http.client.HTTPConnection.putrequest=guard
   from lightning_sdk import Studio
   from lightning_sdk.api.studio_api import StudioApi
   from lightning_sdk.lightning_cloud.openapi import EndpointServiceApi,EndpointServiceCreateEndpointBody,V1EndpointAuth,V1UpstreamCloudSpace,V1EndpointType
   Studio._setup=lambda s:None
   def forbidden(*a,**k):raise RuntimeError('KEEPALIVE_REFUSED')
   StudioApi.start_keeping_alive=forbidden
   stage='preflight'
   s=Studio(name='peaceful-dewdney-424',teamspace='vision-model',org='hopkinsrandy537-org',create_ok=False)
   require(s._studio.id==SID,'TARGET');team=s._teamspace.id;client=s._studio_api._client
   api=EndpointServiceApi(client.api_client)
   kw={'project_id':team,'id':SID,'_request_timeout':(5,20)}
   state=client.cloud_space_service_get_cloud_space_instance_status(**kw)
   require(state.requested is None and state.in_use is not None and state.in_use.phase=='CLOUD_SPACE_INSTANCE_STATE_RUNNING','NOT_STABLE_RUNNING')
   cfg=client.cloud_space_service_get_cloud_space_instance_config(**kw)
   require(cfg.compute_config.name=='cpu-4' and cfg.compute_config.spot is False and cfg.disable_auto_shutdown is False and cfg.idle_shutdown_seconds==0,'CONFIG_DRIFT')
   snapshot=(copy.deepcopy(cfg.compute_config.to_dict()),cfg.disable_auto_shutdown,cfg.idle_shutdown_seconds)
   endpoints=s.list_ports()
   require(not any(e.name==NAME or '8061' in [str(v) for v in (e.ports or [])] or (e.cloudspace and str(e.cloudspace.port)=='8061') for e in endpoints),'ENDPOINT_CONFLICT')
   originals=[e for e in endpoints if '8060' in [str(v) for v in (e.ports or [])]]
   require(len(originals)==1,'ORIGINAL_COUNT');oid=originals[0].id
   old=api.endpoint_service_get_endpoint(project_id=team,ref=oid,_request_timeout=(5,20))
   require(old.cloudspace.cloudspace_id==SID and old.cloudspace.auto_start is False and not old.cloudspace.command,'ORIGINAL_DRIFT')
   old_snapshot=copy.deepcopy(old.to_dict());r['checks'].append('preflight_no_endpoint_conflict_original_cpu_and_8060')
   p.route=route(EndpointServiceApi.endpoint_service_create_endpoint_with_http_info,team)
   body=EndpointServiceCreateEndpointBody(name=NAME,ports=['8061'],auth=V1EndpointAuth(enabled=True,username=username,password=password,user_api_key=False),cloudspace=V1UpstreamCloudSpace(cloudspace_id=SID,port='8061',auto_start=False,instance_type='cpu-4',command='',type=V1EndpointType.PLUGIN_API))
   stage='create_once';save();p.armed=True
   created=api.endpoint_service_create_endpoint(body=body,project_id=team,_request_timeout=(5,25))
   require(created.id and created.id!=oid,'CREATE_ID_UNCONFIRMED')
   r['receipt']={'endpoint_id':created.id,'project_id':team,'studio_id':SID,'name':NAME,'port':8061,'original_endpoint_id':oid};save()
   require(owned(created,created.id,team,oid),'CREATED_IDENTITY')
   stage='readback'
   live=api.endpoint_service_get_endpoint(project_id=team,ref=created.id,_request_timeout=(5,20))
   require(owned(live,created.id,team,oid) and basic_ok(live,username),'READBACK_SCOPE')
   r['configuration']={'auto_start':False,'command_empty':True,'auth':'BASIC_ENABLED','instance_type':'cpu-4','url_count':len(live.urls or []),'studio_job_id_present':bool(live.cloudspace.studio_job_id)}
   r['checks'].append('exact_created_identity_basic_auth_autostart_false_no_command')
   after=api.endpoint_service_get_endpoint(project_id=team,ref=oid,_request_timeout=(5,20))
   require(after.to_dict()==old_snapshot,'ORIGINAL_CHANGED');r['checks'].append('original_8060_unchanged')
   cfg=client.cloud_space_service_get_cloud_space_instance_config(**kw)
   require((cfg.compute_config.to_dict(),cfg.disable_auto_shutdown,cfg.idle_shutdown_seconds)==snapshot,'CONFIG_CHANGED')
   r['checks'].append('machine_and_sleep_settings_unchanged')
   require(p.creates==1 and p.blocked==0,'NETWORK_COUNTS');r['status']='PASS'
 except Exception as e:
  r['error_type']=type(e).__name__
  if type(e) is RuntimeError and str(e).isupper():r['error_code']=str(e)
  if isinstance(getattr(e,'status',None),int):r['http_status']=e.status
  if p.creates and 'receipt' not in r:r['creation']='UNCONFIRMED_DO_NOT_RETRY'
 finally:
  http.client.HTTPConnection.putrequest=original;r['finished_at_utc']=now();save()
  print('UI-only endpoint:',r['status'],'create attempts:',p.creates)
 return 0 if r['status']=='PASS' else 1
if __name__=='__main__':
 if '--self-test' in sys.argv:selftest()
 elif '--claim' in sys.argv:claim()
 else:sys.exit(execute())
