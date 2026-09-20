"""Read-only deletion diagnosis bypassing SDK retry wrapper. Never print payloads."""
import contextlib,datetime,http.client,json,logging,os,pathlib,sys,urllib.parse
import endpoint_readonly as m
EID='endp_01m2yd678z0rpgnxp70nstknhq'
SID='01m2watakghqmc1fnymkg5czax'
NAME='ridge-autowake-probe-8061'
def url_shapes(values):
 out=[]
 for value in values or []:
  u=urllib.parse.urlsplit(value)
  out.append({'scheme':u.scheme if u.scheme in ('http','https') else 'OTHER','has_host':bool(u.hostname),
   'has_userinfo':bool(u.username or u.password),'has_query':bool(u.query),'has_fragment':bool(u.fragment),
   'path_kind':'ROOT' if u.path in ('','/') else 'OTHER',
   'platform_host':bool(u.hostname and u.hostname.endswith(('.cloudspaces.litng.ai','.lightning.ai','.lightningapp.ai'))),
   'host_starts_8060':bool(u.hostname and u.hostname.startswith('8060-'))})
 return out

def test():
 m.selftest()
 r=url_shapes(['https://secret:secret@example.invalid/private?token=secret'])
 assert r[0]['has_userinfo'] and r[0]['has_query'] and not r[0]['platform_host']
 assert 'secret' not in json.dumps(r)
 assert url_shapes([])==[]
 print('PASS URL shape redaction and inherited guards')
def main():
 import urllib3.connection
 r={'status':'FAIL','kind':'generated_endpoint_client_readback','network':{'get':0,'blocked':0,'writes':0},'command_execution':'NOT_RUN','public_preview':'NOT_REQUESTED'}
 original=http.client.HTTPConnection.putrequest
 def guard(conn,method,url,*a,**kw):
  try:
   if not isinstance(conn,(http.client.HTTPSConnection,urllib3.connection.HTTPSConnection)):raise m.ReadOnlyViolation()
   m.check_request(method,conn.host,url)
  except m.ReadOnlyViolation:r['network']['blocked']+=1;raise
  r['network']['get']+=1;return original(conn,method,url,*a,**kw)
 try:
  assert os.environ['GITHUB_REF']=='refs/heads/audit/endpoint-readonly-20260920'
  os.environ['LIGHTNING_DEBUG']='0';os.environ['LIGHTNING_DISABLE_VERSION_CHECK']='1';logging.disable(logging.CRITICAL)
  with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):
   http.client.HTTPConnection.putrequest=guard
   from lightning_sdk import Studio
   from lightning_sdk.api.studio_api import StudioApi
   from lightning_sdk.lightning_cloud.openapi import EndpointServiceApi
   Studio._setup=lambda s:None
   def forbidden(*a,**k):raise m.ReadOnlyViolation()
   StudioApi.start_keeping_alive=forbidden
   s=Studio(name='peaceful-dewdney-424',teamspace='vision-model',org='hopkinsrandy537-org',create_ok=False)
   assert s._studio.id==SID
   # Retain authenticated ApiClient but avoid LightningClient method retry wrappers.
   direct=EndpointServiceApi(s._studio_api._client.api_client)
   try:
    response=direct.endpoint_service_get_endpoint(project_id=s._teamspace.id,ref=EID,_request_timeout=(10,20),_preload_content=False)
    r['deleted_lookup']={'outcome':'RETURNED','http_status':getattr(response,'status',None)}
    if hasattr(response,'release_conn'):response.release_conn()
   except Exception as e:
    r['deleted_lookup']={'outcome':'ERROR','error_type':type(e).__name__}
    if type(getattr(e,'status',None)) is int:r['deleted_lookup']['http_status']=e.status
    # Inspect JSON error code only, never emit raw error text/body/headers.
    raw=getattr(e,'body',None)
    if raw:
     try:
      payload=json.loads(raw)
      if isinstance(payload,dict):
       code=payload.get('code')
       if type(code) is int:r['deleted_lookup']['body_numeric_code']=code
       text=json.dumps(payload).lower()
       r['deleted_lookup']['body_says_not_found']=any(v in text for v in ('not found','not_found','notfound','does not exist'))
     except (ValueError,TypeError):pass
   es=direct.endpoint_service_list_endpoints(project_id=s._teamspace.id,cloudspace_id=SID,_request_timeout=(10,20)).endpoints
   r['exact_id_in_list']=any(e.id==EID for e in es)
   r['candidate_name_count']=sum(e.name==NAME for e in es)
   r['port8061_count']=sum('8061' in [str(v) for v in (e.ports or [])] for e in es)
   old=[e for e in es if '8060' in [str(v) for v in (e.ports or [])]]
   assert len(old)==1
   e=direct.endpoint_service_get_endpoint(project_id=s._teamspace.id,ref=old[0].id,_request_timeout=(10,20))
   assert e.id==old[0].id and e.cloudspace.cloudspace_id==SID
   r['original_8060']={'url_count':len(e.urls or []),'url_shapes':url_shapes(e.urls),'auto_start':e.cloudspace.auto_start,
    'command':m.command_summary(e.cloudspace.command),'has_lightning_subdomain':bool(e.lightning_subdomain),'has_custom_domain':bool(e.custom_domain)}
   r['studio_status']=m.safe_label(s.status)
   r['cleanup_confirmed_404']=r['deleted_lookup'].get('http_status')==404 and not r['exact_id_in_list'] and r['candidate_name_count']==0 and r['port8061_count']==0
   assert r['network']['blocked']==0;r['status']='PASS'
 except Exception as e:
  r['error_type']=type(e).__name__
  if type(getattr(e,'status',None)) is int:r['http_status']=e.status
 finally:
  http.client.HTTPConnection.putrequest=original;r['observed_at_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
  text=json.dumps(r,indent=2)
  for key in ('LIGHTNING_USER_ID','LIGHTNING_API_KEY'):
   assert not os.environ.get(key) or os.environ[key] not in text
  pathlib.Path('out').mkdir(exist_ok=True);pathlib.Path('out/studio-probe.json').write_text(text+'\n');print(r['status'])
 return 0 if r['status']=='PASS' else 1
if __name__=='__main__':
 if '--self-test' in sys.argv:test()
 else:sys.exit(main())
