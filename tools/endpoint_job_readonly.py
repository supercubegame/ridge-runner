"""GET-only original endpoint routing shape; deleted endpoint fields remain unknown."""
import contextlib,datetime,http.client,json,logging,os,pathlib,sys
import endpoint_readonly as m
SID='01m2watakghqmc1fnymkg5czax'
OID='endp_01m2x511jn86kwsqt5eh3pkws1'
def shape(e,studio_cluster):
 c=e.cloudspace
 return {'type':m.safe_label(c.type),'port':str(c.port),'auto_start':c.auto_start,'command_empty':not c.command,'instance_type':m.safe_label(c.instance_type) if c.instance_type else 'UNSET','cluster_id_present':bool(c.cluster_id),'cluster_matches_studio':bool(c.cluster_id and studio_cluster and c.cluster_id==studio_cluster),'studio_job_id_present':bool(c.studio_job_id),'terminal_session_id_present':bool(c.terminal_session_id),'auth_present':e.auth is not None,'auth_enabled':getattr(e.auth,'enabled',None),'url_count':len(e.urls or [])}
def test():
 from types import SimpleNamespace as N
 m.selftest()
 c=N(type='ENDPOINT_PLUGIN_PORT',port='8060',auto_start=False,command='',instance_type='',cluster_id='sentinel-private-cluster',studio_job_id='sentinel-private-job',terminal_session_id='sentinel-private-session')
 e=N(cloudspace=c,auth=N(enabled=True,password='sentinel-password'),urls=['https://sentinel-user:sentinel-password@example.invalid'])
 r=shape(e,'sentinel-private-cluster');assert r['cluster_matches_studio'] and r['studio_job_id_present'] and r['terminal_session_id_present']
 assert 'sentinel' not in json.dumps(r)
 c.cluster_id=None;r=shape(e,'sentinel-private-cluster');assert not r['cluster_id_present'] and not r['cluster_matches_studio']
 print('PASS shape redaction, missing cluster and inherited GET guards')
def main():
 import urllib3.connection
 r={'status':'FAIL','kind':'readonly_original_routing_comparison','network':{'get':0,'blocked':0,'writes':0},'commands':'NOT_RUN','public_http':'NOT_REQUESTED','temporary_comparison_source':'prior_create_payload_and_redacted_readback_not_live_deleted_object'}
 original=http.client.HTTPConnection.putrequest
 def guard(conn,method,url,*a,**k):
  try:
   if not isinstance(conn,(http.client.HTTPSConnection,urllib3.connection.HTTPSConnection)):raise m.ReadOnlyViolation()
   m.check_request(method,conn.host,url)
  except m.ReadOnlyViolation:r['network']['blocked']+=1;raise
  r['network']['get']+=1;return original(conn,method,url,*a,**k)
 try:
  assert os.environ['GITHUB_REF']=='refs/heads/audit/endpoint-readonly-20260920'
  assert all(os.environ.get(k) for k in ('LIGHTNING_USER_ID','LIGHTNING_API_KEY'))
  os.environ['LIGHTNING_DEBUG']='0';os.environ['LIGHTNING_DISABLE_VERSION_CHECK']='1';logging.disable(logging.CRITICAL)
  with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):
   http.client.HTTPConnection.putrequest=guard
   from lightning_sdk import Studio
   from lightning_sdk.api.studio_api import StudioApi
   from lightning_sdk.lightning_cloud.openapi import EndpointServiceApi
   Studio._setup=lambda s:None
   def forbidden(*a,**k):raise m.ReadOnlyViolation()
   StudioApi.start_keeping_alive=forbidden
   s=Studio(name='peaceful-dewdney-424',teamspace='vision-model',org='hopkinsrandy537-org',create_ok=False);assert s._studio.id==SID
   direct=EndpointServiceApi(s._studio_api._client.api_client)
   e=direct.endpoint_service_get_endpoint(project_id=s._teamspace.id,ref=OID,_request_timeout=(5,20))
   assert e.id==OID and e.project_id==s._teamspace.id and e.cloudspace.cloudspace_id==SID and str(e.cloudspace.port)=='8060'
   r['original_8060']=shape(e,s._studio.cluster_id)
   r['studio_cluster_present']=bool(s._studio.cluster_id)
   es=direct.endpoint_service_list_endpoints(project_id=s._teamspace.id,cloudspace_id=SID,_request_timeout=(5,20)).endpoints
   r['temporary8061_absent']=not any('8061' in [str(v) for v in (x.ports or [])] or x.name=='ridge-autowake-probe-8061' for x in es)
   r['studio_status']=m.safe_label(s.status)
   r['prior_temporary_confirmed']={'type':'ENDPOINT_PLUGIN_API','port':'8061','auto_start':False,'command_empty':True,'instance_type':'cpu-4','auth':'fresh_basic_enabled','url_count':0}
   r['prior_temporary_unsaved_fields']=['cluster_id','studio_job_id','terminal_session_id']
   r['prior_temporary_request_omitted_fields']=['cluster_id','studio_job_id','terminal_session_id']
   assert r['network']['blocked']==0;r['status']='PASS'
 except Exception as e:
  r['error_type']=type(e).__name__
  if type(getattr(e,'status',None)) is int:r['http_status']=e.status
 finally:
  http.client.HTTPConnection.putrequest=original;r['observed_at_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
  text=json.dumps(r,indent=2)
  for key in ('LIGHTNING_USER_ID','LIGHTNING_API_KEY'):assert not os.environ.get(key) or os.environ[key] not in text
  pathlib.Path('out').mkdir(exist_ok=True);pathlib.Path('out/studio-probe.json').write_text(text+'\n');print(r['status'])
 return 0 if r['status']=='PASS' else 1
if __name__=='__main__':
 if '--self-test' in sys.argv:test()
 else:sys.exit(main())
