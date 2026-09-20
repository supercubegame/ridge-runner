"""Read exact temporary endpoint after deletion, without any platform writes."""
import contextlib,datetime,http.client,json,logging,os,pathlib,sys,urllib.parse
import endpoint_readonly as m
EID='endp_01m2yd678z0rpgnxp70nstknhq'
SID='01m2watakghqmc1fnymkg5czax'
NAME='ridge-autowake-probe-8061'
def summarize(e):
 up=e.cloudspace
 return {'id_matches':e.id==EID,'name_matches':e.name==NAME,'studio_matches':up is not None and up.cloudspace_id==SID,
  'ports':[str(v) for v in (e.ports or []) if str(v) in ('8060','8061')],
  'url_count':len(e.urls or []),'url_shapes':[{'scheme':urllib.parse.urlsplit(v).scheme if urllib.parse.urlsplit(v).scheme in ('http','https') else 'OTHER','has_host':bool(urllib.parse.urlsplit(v).hostname),'has_path':bool(urllib.parse.urlsplit(v).path),'has_userinfo':bool(urllib.parse.urlsplit(v).username),'has_query':bool(urllib.parse.urlsplit(v).query)} for v in (e.urls or [])],
  'auto_start':up.auto_start if up is not None else None,'auth_enabled':e.auth.enabled if e.auth is not None else None}
def test():
 m.selftest();print('PASS inherited read-only/redaction checks')
def main():
 import urllib3.connection
 r={'status':'FAIL','kind':'temporary_endpoint_cleanup_readback','network':{'get':0,'blocked':0,'writes':0},'command_execution':'NOT_RUN','public_preview':'NOT_REQUESTED'}
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
   Studio._setup=lambda s:None
   def forbidden(*a,**k):raise m.ReadOnlyViolation()
   StudioApi.start_keeping_alive=forbidden
   s=Studio(name='peaceful-dewdney-424',teamspace='vision-model',org='hopkinsrandy537-org',create_ok=False)
   assert s._studio.id==SID
   client=s._studio_api._client
   try:
    e=client.endpoint_service_get_endpoint(project_id=s._teamspace.id,ref=EID,_request_timeout=(10,20))
    r['direct_lookup']='RETURNED';r['endpoint']=summarize(e)
   except Exception as e:
    r['direct_lookup']='NOT_FOUND' if getattr(e,'status',None)==404 else 'UNRESOLVED'
    r['lookup_error_type']=type(e).__name__
    if isinstance(getattr(e,'status',None),int):r['lookup_http_status']=e.status
   es=s.list_ports()
   r['exact_id_in_list']=any(e.id==EID for e in es)
   r['candidate_name_count']=sum(e.name==NAME for e in es)
   r['port8061_count']=sum('8061' in [str(v) for v in (e.ports or [])] for e in es)
   r['cleanup_confirmed']=r['direct_lookup']=='NOT_FOUND' and not r['exact_id_in_list'] and r['candidate_name_count']==0 and r['port8061_count']==0
   r['studio_status']=m.safe_label(s.status)
   assert r['network']['blocked']==0;r['status']='PASS'
 except Exception as e:r['error_type']=type(e).__name__
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
