"""Fresh 17:55 approval: omit auth, anonymous diagnostic only, exact cleanup."""
import base64,contextlib,copy,http.client,json,logging,os,pathlib,secrets,shlex,sys,time
import runtime_trial as b
import diagnostic_v6 as d
b.BRANCH='audit/runtime-8061-v7-20260920'
b.CLAIM='claims/runtime-8061-v7-20260920-1755.json'
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
 data={'run_id':os.environ['GITHUB_RUN_ID'],'sha':os.environ['GITHUB_SHA'],'approved':'17:55 approve_8061_omit_auth_comparison_v7; one new PLUGIN_PORT omit auth anonymous diagnostics only; auto_start false; one service command max180s; exact new endpoint deletion; preserve8060; no Studio start/stop machine or SSH changes; abort conflict/not Running/auth enabled readback','at':b.now()}
 b.github('PUT','/contents/'+b.CLAIM,{'branch':'studio-results','message':'Claim approved 17:55 anonymous diagnostic comparison','content':base64.b64encode(json.dumps(data).encode()).decode()})
 live=b.github('GET','/contents/'+b.CLAIM+'?ref=studio-results')
 b.require(json.loads(base64.b64decode(live['content']))==data,'CLAIM_READBACK')
 pathlib.Path('out').mkdir(exist_ok=True);pathlib.Path('out/runtime-v7-claim.json').write_text(json.dumps(data))
def test():
 b.test()
 d.test()
 import ast
 tree=ast.parse(pathlib.Path(__file__).read_text())
 calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='V1UpstreamCloudSpace']
 b.require(len(calls)==1 and {k.arg for k in calls[0].keywords}=={'cloudspace_id','port','auto_start','type'},'MINIMAL_UPSTREAM')
 calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='V1EndpointAuth']
 b.require(len(calls)==0,'NO_AUTH_CONSTRUCTION')
 calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='EndpointServiceCreateEndpointBody']
 b.require(len(calls)==1 and {k.arg for k in calls[0].keywords}=={'name','ports','cloudspace'},'AUTH_OMITTED')
 calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name) and n.func.value.id=='b' and n.func.attr=='request']
 b.require(all(len(n.args)==1 and not n.keywords for n in calls),'ALL_HTTP_REQUESTS_WITHOUT_AUTH_HEADER')
 import hashlib
 b.require(hashlib.sha1(b'blob '+str(len(pathlib.Path(d.__file__).read_bytes())).encode()+b'\0'+pathlib.Path(d.__file__).read_bytes()).hexdigest()=='d684a4a408fe758bf385c581d089c66bf76e6da7','DIAGNOSTIC_UNCHANGED_FROM_V6')
 from types import SimpleNamespace as N
 for value in ('not found',b'not found',{'message':'not found'},None):
  result=absent_error(N(status=500,body=value));b.require(result['not_found_marker']==(value is not None),'BODY_TYPES')
 b.require(URL=='https://8061-01m2watakghqmc1fnymkg5czax.cloudspaces.litng.ai','UI_URL')
 print('PASS added str/bytes/dict/None error-body fixtures and UI URL identity')
def execute():
 import urllib3.connection
 p=b.Policy();p.hosts.add(b.urllib.parse.urlsplit(URL).hostname);original=http.client.HTTPConnection.putrequest
 private=[os.environ.get(k,'') for k in ('LIGHTNING_USER_ID','LIGHTNING_API_KEY')]
 marker=json.dumps({'probe':'runtime-v7','nonce':secrets.token_hex(16)},sort_keys=True)
 r={'status':'FAIL','kind':'approved_runtime_v7_omit_auth','omitted_request_fields':['auth','command','instanceType'],'causation':'AUTH_OMISSION_COMPARISON_NOT_CAUSAL_PROOF','started_at_utc':b.now(),'checks':[],'cleanup':{},'service_lifetime_seconds':120,'service_hard_kill_seconds':165,'public_attempts':[],'url_source':'user_API_Builder_screenshots_12:01','endpoint_url':URL,'studio_start_stop':'NOT_RUN','auto_wake':'NOT_RUN','ssh':'NOT_USED'}
 stage='scope';eid=None;session=None;api=None;cloud=None;client=None;team=None;oid=None;old_snapshot=None;cfg_snapshot=None;service_deadline=None
 def save():
  r['last_stage']=stage;r['network']={'get':p.gets,'writes':p.writes,'blocked':p.blocked}
  text=json.dumps(r,indent=2);b.require(not any(v and v in text for v in private),'SECRET_OUTPUT')
  pathlib.Path('out').mkdir(exist_ok=True);pathlib.Path('out/studio-probe.json').write_text(text+'\n')
 def guard(conn,method,url,*a,**kw):
  b.require(isinstance(conn,(http.client.HTTPSConnection,urllib3.connection.HTTPSConnection)),'HTTPS_TRANSPORT')
  p.check(method,conn.host,url);return original(conn,method,url,*a,**kw)
 def inspect_service():
  while service_deadline is not None and time.monotonic()<service_deadline:
   result=cloud.cloud_space_service_get_long_running_command_in_cloud_space(project_id=team,id=b.SID,session=session,_request_timeout=(5,15))
   if result.exit_code is not None and result.exit_code!=-1:
    data=json.loads(result.output)
    d.validate_report(data)
    r['service']={'exit_code':result.exit_code,**data}
    r['cleanup']['service_finished']=True
    r['cleanup']['8061_no_listeners_after']=data.get('after')=={'tcp4':0,'tcp6':0}
    return
   time.sleep(3)
  r['cleanup']['service_finished']=False
 try:
  scope();receipt=json.loads(pathlib.Path('out/runtime-v7-claim.json').read_text())
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
    b.require(team=='01hrhh1avmp22zbv37depwjkp8','TEAM_IDENTITY')
    api=EndpointServiceApi(client.api_client);cloud=CloudSpaceServiceApi(client.api_client)
    kw={'project_id':team,'id':b.SID,'_request_timeout':(5,20)}
    state=cloud.cloud_space_service_get_cloud_space_instance_status(**kw)
    r['preflight_state']={'phase':state.in_use.phase if state.in_use else None,'requested_present':state.requested is not None};save()
    b.require(state.requested is None and state.in_use is not None and state.in_use.phase=='CLOUD_SPACE_INSTANCE_STATE_RUNNING','NOT_STABLE_RUNNING')
    cfg=cloud.cloud_space_service_get_cloud_space_instance_config(**kw)
    b.require(cfg.compute_config.name=='cpu-4' and cfg.compute_config.spot is False and cfg.disable_auto_shutdown is False and cfg.idle_shutdown_seconds==0,'CONFIG_DRIFT')
    cfg_snapshot=(copy.deepcopy(cfg.compute_config.to_dict()),cfg.disable_auto_shutdown,cfg.idle_shutdown_seconds)
    endpoints=s.list_ports()
    b.require(not any(e.name==b.NAME or '8061' in [str(v) for v in (e.ports or [])] or (e.cloudspace and str(e.cloudspace.port)=='8061') for e in endpoints),'ENDPOINT_CONFLICT')
    originals=[e for e in endpoints if '8060' in [str(v) for v in (e.ports or [])]]
    b.require(len(originals)==1,'ORIGINAL_COUNT');oid=originals[0].id
    b.require(oid=='endp_01m2x511jn86kwsqt5eh3pkws1','ORIGINAL_IDENTITY')
    old=api.endpoint_service_get_endpoint(project_id=team,ref=oid,_request_timeout=(5,20))
    b.require(old.cloudspace.cloudspace_id==b.SID and old.cloudspace.auto_start is False and not old.cloudspace.command,'ORIGINAL_DRIFT')
    old_snapshot=copy.deepcopy(old.to_dict())
    code,data=b.request(b.ORIGINAL+'/version.json');b.require(code==200 and json.loads(data)==b.VERSION,'ORIGINAL_GAME')
    r['checks'].append('preflight_original_cpu_game_no_endpoint_conflict')
    p.routes['create']=b.route(EndpointServiceApi.endpoint_service_create_endpoint_with_http_info,team)
    p.routes['command']=b.route(CloudSpaceServiceApi.cloud_space_service_execute_command_in_cloud_space_with_http_info,team,b.SID)
    body=EndpointServiceCreateEndpointBody(name=b.NAME,ports=['8061'],cloudspace=V1UpstreamCloudSpace(cloudspace_id=b.SID,port='8061',auto_start=False,type=V1EndpointType.PLUGIN_PORT))
    wire=client.api_client.sanitize_for_serialization(body)
    b.require(set(wire)=={'name','ports','cloudspace'} and set(wire['cloudspace'])=={'cloudspaceId','port','autoStart','type'},'WIRE_MINIMAL_KEYS')
    b.require(wire['cloudspace']['autoStart'] is False and wire['cloudspace']['type']=='ENDPOINT_PLUGIN_PORT','WIRE_VALUES')
    r['wire_keys']={'cloudspace':sorted(wire['cloudspace']),'top_level':sorted(wire)}
    stage='create_once';save();p.armed='create'
    created=api.endpoint_service_create_endpoint(body=body,project_id=team,_request_timeout=(5,25))
    b.require(created.id and created.id!=oid,'CREATE_ID');eid=created.id;r['created_endpoint_id']=eid;r['project_id']=team;save()
    b.require(b.owned(created,eid,team,oid),'CREATED_IDENTITY')
    live=api.endpoint_service_get_endpoint(project_id=team,ref=eid,_request_timeout=(5,20))
    b.require(b.owned(live,eid,team,oid),'READBACK_IDENTITY')
    b.require(live.cloudspace.auto_start is False and not live.cloudspace.command and live.cloudspace.type==V1EndpointType.PLUGIN_PORT,'UPSTREAM_CONFIG')
    c=live.cloudspace
    r['routing_readback']={'instance_type':'UNSET' if not c.instance_type else 'CPU4' if c.instance_type=='cpu-4' else 'OTHER','cluster_present':bool(c.cluster_id),'cluster_matches_studio':bool(c.cluster_id and c.cluster_id==s._studio.cluster_id),'studio_job_present':bool(c.studio_job_id),'studio_job_matches_original':bool(c.studio_job_id and c.studio_job_id==old.cloudspace.studio_job_id),'terminal_session_present':bool(c.terminal_session_id)}
    r['auth_readback']={'present':live.auth is not None,'enabled':live.auth.enabled if live.auth else None}
    b.require(live.auth is None or (live.auth.enabled is False and not live.auth.user_api_key and not live.auth.token and not live.auth.tokens and not live.auth.username and not live.auth.password),'UNEXPECTED_AUTH_READBACK')
    r['api_url_count']=len(live.urls or []);r['checks'].append('new_identity_auth_omitted_autostart_false')
    stage='submit_bounded_service';save()
    command='exec env -i PATH=/usr/local/bin:/usr/bin:/bin timeout --signal=KILL 165s python3 -c '+shlex.quote(d.remote_source(marker=marker))
    service_deadline=time.monotonic()+200
    p.armed='command'
    submitted=cloud.cloud_space_service_execute_command_in_cloud_space(CloudSpaceServiceExecuteCommandInCloudSpaceBody(command,detached=True),project_id=team,id=b.SID,_request_timeout=(5,25))
    b.require(submitted and submitted.session_name,'COMMAND_UNCONFIRMED_NO_REPLAY');session=submitted.session_name
    stage='diagnostic_http';deadline=time.monotonic()+70;ready=False
    def observe(label,path='/probe'):
     entry={'label':label,'at_utc':b.now()};start=time.monotonic()
     try:
      code,data=b.request(URL+path)
      entry.update(http_status=code,exact_marker=data==marker.encode(),body_bytes_sampled=len(data))
     except (b.urllib.error.URLError,TimeoutError) as e:
      entry['error_type']=type(e).__name__
     entry['elapsed_seconds']=round(time.monotonic()-start,3)
     r['public_attempts'].append(entry);save()
     return entry
    while time.monotonic()<deadline:
     entry=observe('anonymous')
     if entry.get('http_status')==200 and entry.get('exact_marker'):ready=True;break
     if entry.get('http_status') in (401,403):break
     time.sleep(3)
    r['anonymous_marker_verified']=ready
    if ready:r['checks'].append('anonymous_exact_marker')
    root=observe('root_anonymous','/')
    r['trial_status']='PASS' if ready and root.get('http_status')==404 else 'FAIL'
    stage='wait_service_exit';inspect_service()
    b.require(r.get('service',{}).get('exit_code')==0 and r['service'].get('status')=='EXPIRED_CLOSED' and r['cleanup'].get('8061_no_listeners_after') and r['service'].get('local_selfcheck_http') is True,'SERVICE_EXIT_OR_LOCAL_HTTP')
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
  http.client.HTTPConnection.putrequest=original;r['finished_at_utc']=b.now();save();print('Runtime v7:',r['status'],'writes:',p.writes)
 return 0 if r['status']=='PASS' else 1
if __name__=='__main__':
 if '--self-test' in sys.argv:test()
 elif '--claim' in sys.argv:claim()
 else:sys.exit(execute())
