"""Final exact-ID deletion readback; only allowlisted response classifications."""
import contextlib,datetime,http.client,json,logging,os,pathlib,re,sys
import endpoint_readonly as m
EID='endp_01m2yd678z0rpgnxp70nstknhq'
SID='01m2watakghqmc1fnymkg5czax'
NAME='ridge-autowake-probe-8061'
def classify_error(error):
 text=str(error).lower()
 return {'error_type':type(error).__name__,'http_status':getattr(error,'status',None) if type(getattr(error,'status',None)) is int else None,
 'mentions_not_found':'not found' in text or 'not_found' in text or 'notfound' in text,
 'mentions_404':bool(re.search(r'\b404\b',text)),
 'mentions_permission':any(v in text for v in ('permission','unauthorized','forbidden'))}
def test():
 m.selftest()
 assert classify_error(Exception('404 Not Found sentinel-secret'))['mentions_not_found']
 assert 'sentinel-secret' not in json.dumps(classify_error(Exception('404 Not Found sentinel-secret')))
 print('PASS error redaction and inherited guards')
def main():
 import urllib3.connection
 r={'status':'FAIL','kind':'exact_deleted_endpoint_raw_readback','network':{'get':0,'blocked':0,'writes':0},'command_execution':'NOT_RUN'}
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
    response=client.endpoint_service_get_endpoint(project_id=s._teamspace.id,ref=EID,_request_timeout=(10,20),_preload_content=False)
    r['raw_response_type']=type(response).__name__
    r['raw_status']=getattr(response,'status',None) if type(getattr(response,'status',None)) is int else None
    data=getattr(response,'data',b'')
    if isinstance(data,bytes) and len(data)<65536:
     try:
      payload=json.loads(data)
      if isinstance(payload,dict):
       r['response_fields']=[k for k in ('id','endpoint','error','message','code','detail') if k in payload]
       r['payload_exact_id']=payload.get('id')==EID
       text=json.dumps(payload).lower()
       r['payload_not_found']='not found' in text or 'not_found' in text or 'notfound' in text
     except ValueError:r['json_parsed']=False
    if hasattr(response,'release_conn'):response.release_conn()
   except Exception as e:r['lookup_error']=classify_error(e)
   es=s.list_ports()
   r['exact_id_in_list']=any(e.id==EID for e in es)
   r['candidate_name_count']=sum(e.name==NAME for e in es)
   r['port8061_count']=sum('8061' in [str(v) for v in (e.ports or [])] for e in es)
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
