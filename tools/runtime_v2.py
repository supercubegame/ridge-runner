"""Fresh one-use 12:14 authorization; fixed UI-observed URL, bounded service."""
import base64,contextlib,copy,http.client,json,logging,os,pathlib,secrets,shlex,sys,time
import runtime_trial as b
b.BRANCH='audit/runtime-8061-v2-20260920'
b.CLAIM='claims/runtime-8061-v2-20260920-1214.json'
URL='https://8061-01m2watakghqmc1fnymkg5czax.cloudspaces.litng.ai'
def absent_error(error):
 body=getattr(error,'body',None)
 if isinstance(body,bytes):body=body.decode('utf-8','replace')
 text=body if isinstance(body,str) else json.dumps(body) if isinstance(body,(dict,list)) else ''
 status=getattr(error,'status',None)
 return {'http_status':status if isinstance(status,int) else None,'not_found_marker':any(x in text.lower() for x in ('not found','not exist','not_found'))}
def scope():
 b.require(os.environ['GITHUB_REPOSITORY']=='supercubegame/ridge-runner' and os.environ['GITHUB_REF']=='refs/heads/'+b.BRANCH and os.environ['GITHUB_RUN_ATTEMPT']=='1','SCOPE')
def claim():
 scope()
 data={'run_id':os.environ['GITHUB_RUN_ID'],'sha':os.environ['GITHUB_SHA'],'approved':'12:14 one fresh Basic 8061 endpoint, auto_start false, service max180s, test auth at UI-observed URL, delete only newly created endpoint; no Studio start/stop','at':b.now()}
 b.github('PUT','/contents/'+b.CLAIM,{'branch':'studio-results','message':'Claim approved 12:14 runtime trial','content':base64.b64encode(json.dumps(data).encode()).decode()})
 live=b.github('GET','/contents/'+b.CLAIM+'?ref=studio-results')
 b.require(json.loads(base64.b64decode(live['content']))==data,'CLAIM_READBACK')
 pathlib.Path('out').mkdir(exist_ok=True);pathlib.Path('out/runtime-v2-claim.json').write_text(json.dumps(data))
def test():
 b.test()
 from types import SimpleNamespace as N
 for value in ('not found',b'not found',{'message':'not found'},None):
  result=absent_error(N(status=500,body=value));b.require(result['not_found_marker']==(value is not None),'BODY_TYPES')
 b.require(URL=='https://8061-01m2watakghqmc1fnymkg5czax.cloudspaces.litng.ai','UI_URL')
 print('PASS added str/bytes/dict/None error-body fixtures and UI URL identity')
def execute():
 import urllib3.connection
 p=b.Policy();p.hosts.add(b.urllib.parse.urlsplit(URL).hostname);original=http.client.HTTPConnection.putrequest
 username='probe-'+secrets.token_hex(8);password=secrets.token_urlsafe(32)
 auth='Basic '+base64.b64encode((username+':'+password).encode()).decode()
 private=[username,password,auth]+[os.environ.get(k,'') for k in ('LIGHTNING_USER_ID','LIGHTNING_API_KEY')]
 marker=json.dumps({'probe':'runtime-v2','nonce':secrets.token_hex(16)},sort_keys=True)
 r={'status':'FAIL','kind':'approved_runtime_v2','started_at_utc':b.now(),'checks':[],'cleanup':{},'service_lifetime_seconds':100,'url_source':'user_API_Builder_screenshots_12:01','endpoint_url':URL,'studio_start_stop':'NOT_RUN','auto_wake':'NOT_RUN'}
 stage='scope';eid=None;session=None;api=None;cloud=None;client=None;team=None;oid=None;old_snapshot=None;cfg_snapshot=None
 def save():
  r['last_stage']=stage;r['network']={'get':p.gets,'writes':p.writes,'blocked':p.blocked}
  text=json.dumps(r,indent=2);b.require(not any(v and v in text for v in private),'SECRET_OUTPUT')
  pathlib.Path('out').mkdir(exist_ok=True);pathlib.Path('out/studio-probe.json').write_text(text+'\n')
 def guard(conn,method,url,*a,**kw):
  b.require(isinstance(conn,(http.client.HTTPSConnection,urllib3.connection.HTTPSConnection)),'HTTPS_TRANSPORT')
  p.check(method,conn.host,url);return original(conn,method,url,*a,**kw)
 def inspect_service():
  deadline=time.monotonic()+150
  while time.monotonic()<deadline:
   result=cloud.cloud_space_service_get_long_running_command_in_cloud_space(project_id=team,id=b.SID,session=session,_request_timeout=(5,15))
   if result.exit_code is not None and result.exit_code!=-1:
    data=json.loads(result.output)
    b.require(set(data)<= {'status','bound','lifetime_seconds','before','after','elapsed_seconds','error_type'},'REMOTE_OUTPUT')
    r['service']={'exit_code':result.exit_code,**data}
    r['cleanup']['service_finished']=True
    r['cleanup']['8061_no_listeners_after']=data.get('after')=={'tcp4':0,'tcp6':0}
    return
   time.sleep(3)
  r['cleanup']['service_finished']=False
 try:
  scope();receipt=json.loads(pathlib.Path('out/runtime-v2-claim.json').read_text())
  b.require(receipt['sha']==os.environ['GITHUB_SHA'] and receipt['run_id']==os.environ['GITHUB_RUN_ID'],'CLAIM')
  b.require(all(os.environ.get(k) for k in ('LIGHTNING_USER_ID','LIGHTNING_API_KEY')),'CREDENTIALS')
  os.environ['LIGHTNING_DEBUG']='0';os.environ['LIGHTNING_DISABLE_VERSION_CHECK']='1';logging.disable(logging.CRITICAL)
  with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):
   http.client.HTTPConnection.putrequest=guard
   try:
    from lightning_sdk import Studio
    from lightning_sdk.api.studio_api import StudioApi
    from lightning_sdk.lightning_cloud.openapi import EndpointServiceApi,CloudSpaceServiceApi,EndpointServiceCreateEndpointBody,V1EndpointAuth,V1UpstreamCloudSpace,V1EndpointType,CloudSpaceServiceExecuteCommandInCloudSpaceBody
    Studio._setup=lambda s:None
    def forbidden(*a,**k):raise RuntimeError('KEEPALIVE_REFUSED')
    StudioApi.start_keeping_alive=forbidden
    stage='preflight'
    s=Studio(name='peaceful-dewdney-424',teamspace='vision-model',org='hopkinsrandy537-org',create_ok=False)
    b.require(s._studio.id==b.SID,'TARGET');team=s._teamspace.id;client=s._studio_api._client
    api=EndpointServiceApi(client.api_client);cloud=CloudSpaceServiceApi(client.api_client)
    kw={'project_id':team,'id':b.SID,'_request_timeout':(5,20)}
    state=cloud.cloud_space_service_get_cloud_space_instance_status(**kw)
    b.require(state.requested is None and state.in_use is not None and state.in_use.phase=='CLOUD_SPACE_INSTANCE_STATE_RUNNING','NOT_STABLE_RUNNING')
    cfg=cloud.cloud_space_service_get_cloud_space_instance_config(**kw)
    b.require(cfg.compute_config.name=='cpu-4' and cfg.compute_config.spot is False and cfg.disable_auto_shutdown is False and cfg.idle_shutdown_seconds==0,'CONFIG_DRIFT')
    cfg_snapshot=(copy.deepcopy(cfg.compute_config.to_dict()),cfg.disable_auto_shutdown,cfg.idle_shutdown_seconds)
    endpoints=s.list_ports()
    b.require(not any(e.name==b.NAME or '8061' in [str(v) for v in (e.ports or [])] or (e.cloudspace and str(e.cloudspace.port)=='8061') for e in endpoints),'ENDPOINT_CONFLICT')
    originals=[e for e in endpoints if '8060' in [str(v) for v in (e.ports or [])]]
    b.require(len(originals)==1,'ORIGINAL_COUNT');oid=originals[0].id
    old=api.endpoint_service_get_endpoint(project_id=team,ref=oid,_request_timeout=(5,20))
    b.require(old.cloudspace.cloudspace_id==b.SID and old.cloudspace.auto_start is False and not old.cloudspace.command,'ORIGINAL_DRIFT')
    old_snapshot=copy.deepcopy(old.to_dict())
    code,data=b.request(b.ORIGINAL+'/version.json');b.require(code==200 and json.loads(data)==b.VERSION,'ORIGINAL_GAME')
    r['checks'].append('preflight_original_cpu_game_no_endpoint_conflict')
    p.routes['create']=b.route(EndpointServiceApi.endpoint_service_create_endpoint_with_http_info,team)
    p.routes['command']=b.route(CloudSpaceServiceApi.cloud_space_service_execute_command_in_cloud_space_with_http_info,team,b.SID)
    body=EndpointServiceCreateEndpointBody(name=b.NAME,ports=['8061'],auth=V1EndpointAuth(enabled=True,username=username,password=password,user_api_key=False),cloudspace=V1UpstreamCloudSpace(cloudspace_id=b.SID,port='8061',auto_start=False,instance_type='cpu-4',command='',type=V1EndpointType.PLUGIN_API))
    stage='create_once';save();p.armed='create'
    created=api.endpoint_service_create_endpoint(body=body,project_id=team,_request_timeout=(5,25))
    b.require(created.id and created.id!=oid,'CREATE_ID');eid=created.id;r['created_endpoint_id']=eid;r['project_id']=team;save()
    b.require(b.owned(created,eid,team,oid),'CREATED_IDENTITY')
    live=api.endpoint_service_get_endpoint(project_id=team,ref=eid,_request_timeout=(5,20))
    b.require(b.owned(live,eid,team,oid),'READBACK_IDENTITY')
    b.require(live.cloudspace.auto_start is False and not live.cloudspace.command and live.cloudspace.instance_type=='cpu-4' and live.cloudspace.type==V1EndpointType.PLUGIN_API,'UPSTREAM_CONFIG')
    b.require(live.auth and live.auth.enabled is True and live.auth.username==username and not live.auth.user_api_key and not live.auth.token and not live.auth.tokens,'BASIC_CONFIG')
    r['api_url_count']=len(live.urls or []);r['checks'].append('new_identity_basic_auth_autostart_false')
    stage='submit_bounded_service';save()
    command='exec env -i PATH=/usr/local/bin:/usr/bin:/bin python3 -c '+shlex.quote(b.remote_source(marker=marker))
    p.armed='command'
    submitted=cloud.cloud_space_service_execute_command_in_cloud_space(CloudSpaceServiceExecuteCommandInCloudSpaceBody(command,detached=True),project_id=team,id=b.SID,_request_timeout=(5,25))
    b.require(submitted and submitted.session_name,'COMMAND_UNCONFIRMED_NO_REPLAY');session=submitted.session_name
    stage='authenticated_http';deadline=time.monotonic()+40;ready=False
    while time.monotonic()<deadline:
     try:
      code,data=b.request(URL+'/probe',auth);r['valid_auth_last_http_status']=code
      if code==200 and data==marker.encode():ready=True;break
      if code in (401,403):raise RuntimeError('VALID_AUTH_REJECTED')
     except (b.urllib.error.URLError,TimeoutError):pass
     time.sleep(2)
    b.require(ready,'EXACT_AUTHENTICATED_MARKER_NOT_VERIFIED');r['checks'].append('valid_basic_auth_exact_marker')
    for label,header in [('missing',None),('wrong','Basic '+base64.b64encode(b'wrong:wrong').decode())]:
     code,data=b.request(URL+'/probe',header);r[label+'_auth_http_status']=code
     b.require(code in (401,403) and marker.encode() not in data,'UNAUTHORIZED_NOT_DENIED')
    r['checks'].append('missing_and_wrong_auth_denied')
    code,data=b.request(URL+'/',auth);r['root_http_status']=code;b.require(code==404,'NO_FILES');r['checks'].append('root_has_no_file_serving')
    r['trial_status']='PASS';stage='wait_service_exit';inspect_service()
    b.require(r.get('service',{}).get('exit_code')==0 and r['service'].get('status')=='EXPIRED_CLOSED' and r['cleanup'].get('8061_no_listeners_after'),'SERVICE_EXIT')
    r['checks'].append('bounded_service_closed')
   finally:
    stage='cleanup'
    if eid and api:
     try:
      live=api.endpoint_service_get_endpoint(project_id=team,ref=eid,_request_timeout=(5,20));b.require(b.owned(live,eid,team,oid),'CLEANUP_IDENTITY')
      p.routes['delete']=b.route(EndpointServiceApi.endpoint_service_delete_endpoint_with_http_info,team,eid);p.armed='delete'
      api.endpoint_service_delete_endpoint(project_id=team,id=eid,_request_timeout=(5,25));r['cleanup']['delete_returned']=True
      r['cleanup']['endpoint_list_absent']=not any(e.id==eid or e.name==b.NAME or '8061' in [str(v) for v in (e.ports or [])] for e in s.list_ports())
      try:api.endpoint_service_get_endpoint(project_id=team,ref=eid,_request_timeout=(5,20));r['cleanup']['single_get']={'result':'PRESENT'}
      except Exception as e:r['cleanup']['single_get']=absent_error(e)
     except Exception as e:r['cleanup']['endpoint_error_type']=type(e).__name__
    elif p.writes['create']:r['cleanup']['creation_identity_unconfirmed']=True
    if session and not r['cleanup'].get('service_finished'):
     try:inspect_service()
     except Exception as e:r['cleanup']['service_error_type']=type(e).__name__
    if p.writes['command'] and not session:r['cleanup']['service_submission_unconfirmed_no_replay']=True
    if old_snapshot is not None:
     try:
      after=api.endpoint_service_get_endpoint(project_id=team,ref=oid,_request_timeout=(5,20));r['cleanup']['original_endpoint_unchanged']=after.to_dict()==old_snapshot
      cfg=cloud.cloud_space_service_get_cloud_space_instance_config(project_id=team,id=b.SID,_request_timeout=(5,20))
      r['cleanup']['machine_sleep_unchanged']=(cfg.compute_config.to_dict(),cfg.disable_auto_shutdown,cfg.idle_shutdown_seconds)==cfg_snapshot
      code,data=b.request(b.ORIGINAL+'/version.json');r['cleanup']['original_game_version_ok']=code==200 and json.loads(data)==b.VERSION
     except Exception as e:r['cleanup']['original_readback_error_type']=type(e).__name__
   required=['delete_returned','endpoint_list_absent','service_finished','8061_no_listeners_after','original_endpoint_unchanged','machine_sleep_unchanged','original_game_version_ok']
   b.require(r.get('trial_status')=='PASS' and all(r['cleanup'].get(k) is True for k in required) and p.blocked==0,'INCOMPLETE')
   r['status']='PASS'
 except Exception as e:
  r['error_type']=type(e).__name__
  if type(e) is RuntimeError and str(e).isupper():r['error_code']=str(e)
  if isinstance(getattr(e,'status',None),int):r['http_status']=e.status
 finally:
  http.client.HTTPConnection.putrequest=original;r['finished_at_utc']=b.now();save();print('Runtime v2:',r['status'],'writes:',p.writes)
 return 0 if r['status']=='PASS' else 1
if __name__=='__main__':
 if '--self-test' in sys.argv:test()
 elif '--claim' in sys.argv:claim()
 else:sys.exit(execute())
