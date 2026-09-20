"""Read only original endpoint raw metadata; never output raw auth or routing identifiers."""
import contextlib,datetime,http.client,json,logging,os,pathlib,sys,urllib.parse
SID='01m2watakghqmc1fnymkg5czax'
TEAM='01hrhh1avmp22zbv37depwjkp8'
EID='endp_01m2x511jn86kwsqt5eh3pkws1'
BRANCH='audit/route-metadata-readonly-20260920'
def tri(value):
 return 'TRUE' if value is True else 'FALSE' if value is False else 'NULL' if value is None else 'OTHER_TYPE'
def summarize(raw,root_map,up_map):
 assert isinstance(raw,dict)
 assert raw.get('id')==EID and raw.get('projectId')==TEAM
 up=raw.get('cloudspace');assert isinstance(up,dict)
 assert up.get('cloudspaceId')==SID and str(up.get('port'))=='8060'
 assert raw.get('ports')==['8060'] and up.get('autoStart') is False
 assert not up.get('command')
 known_root=set(root_map.values());known_up=set(up_map.values())
 return {
  'identity_verified':True,
  'proxy':{'key_present':'proxy' in raw,'value':tri(raw.get('proxy'))},
  'job_upstream_present':raw.get('job') is not None,
  'managed_upstream_present':raw.get('managed') is not None,
  'openai_upstream_present':raw.get('openai') is not None,
  'prewarm_present':raw.get('prewarm') is not None,
  'lightning_subdomain_present':bool(raw.get('lightningSubdomain')),
  'custom_domain_present':bool(raw.get('customDomain')),
  'urls_count':len(raw.get('urls') or []),
  'auth_present':isinstance(raw.get('auth'),dict),
  'auth_enabled':tri((raw.get('auth') or {}).get('enabled')),
  'upstream_type':'PLUGIN_PORT' if up.get('type')=='ENDPOINT_PLUGIN_PORT' else 'OTHER',
  'cluster_present':bool(up.get('clusterId')),
  'studio_job_present':bool(up.get('studioJobId')),
  'terminal_session_present':bool(up.get('terminalSessionId')),
  'unknown_root_field_count':len(set(raw)-known_root),
  'unknown_upstream_field_count':len(set(up)-known_up),
  'known_root_field_presence':{key:key in raw for key in sorted(known_root)},
  'known_upstream_field_presence':{key:key in up for key in sorted(known_up)},
 }
def test():
 raw={'id':EID,'projectId':TEAM,'ports':['8060'],'cloudspace':{'cloudspaceId':SID,'port':'8060','autoStart':False,'command':'','type':'ENDPOINT_PLUGIN_PORT','studioJobId':'sentinel-SECRET'},'auth':{'enabled':False,'password':'sentinel-SECRET'},'proxy':True,'extra':'sentinel-SECRET'}
 root={k:k for k in raw if k!='extra'};up={k:k for k in raw['cloudspace']}
 result=summarize(raw,root,up)
 assert result['unknown_root_field_count']==1 and result['unknown_upstream_field_count']==0
 assert result['proxy']=={'key_present':True,'value':'TRUE'}
 assert result['auth_enabled']=='FALSE' and result['studio_job_present']
 assert 'sentinel-SECRET' not in json.dumps(result)
 assert [tri(x) for x in (True,False,None,'secret',1)]==['TRUE','FALSE','NULL','OTHER_TYPE','OTHER_TYPE']
 for key,value in [('id','bad'),('projectId','bad'),('ports',['8061'])]:
  changed=dict(raw);changed[key]=value
  try:summarize(changed,root,up)
  except AssertionError:pass
  else:raise AssertionError('identity guard')
 assert 'proxy' not in summarize({k:v for k,v in raw.items() if k!='proxy'},root,up)['known_upstream_field_presence']
 print('PASS metadata identity, omission, tri-state, unknown counts and secret-redaction fixtures')
def main():
 import urllib3.connection
 from endpoint_readonly import check_request,ReadOnlyViolation
 report={'kind':'original_8060_raw_metadata_readonly','status':'FAIL','network':{'get':0,'blocked':0,'writes':0},'public_url':'NOT_REQUESTED','studio_commands':'NOT_RUN','endpoint_writes':'NOT_RUN','started_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 original=http.client.HTTPConnection.putrequest
 def guard(conn,method,url,*a,**kw):
  try:
   if not isinstance(conn,(http.client.HTTPSConnection,urllib3.connection.HTTPSConnection)):raise ReadOnlyViolation()
   check_request(method,conn.host,url)
   if report['network']['get']>=12:raise ReadOnlyViolation()
   path=urllib.parse.urlsplit(url).path
   if '/endpoints' in path and path!='/v1/projects/'+TEAM+'/endpoints/'+EID:raise ReadOnlyViolation()
  except Exception:report['network']['blocked']+=1;raise
  report['network']['get']+=1;return original(conn,method,url,*a,**kw)
 try:
  assert os.environ['GITHUB_REF']=='refs/heads/'+BRANCH and os.environ['GITHUB_RUN_ATTEMPT']=='1'
  assert all(os.environ.get(k) for k in ('LIGHTNING_USER_ID','LIGHTNING_API_KEY'))
  os.environ['LIGHTNING_DEBUG']='0';os.environ['LIGHTNING_DISABLE_VERSION_CHECK']='1';logging.disable(logging.CRITICAL)
  with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):
   http.client.HTTPConnection.putrequest=guard
   from lightning_sdk import Studio
   from lightning_sdk.api.studio_api import StudioApi
   from lightning_sdk.lightning_cloud.openapi import EndpointServiceApi,V1Endpoint,V1UpstreamCloudSpace
   Studio._setup=lambda s:None
   def forbidden(*a,**kw):raise ReadOnlyViolation()
   StudioApi.start_keeping_alive=forbidden
   s=Studio(name='peaceful-dewdney-424',teamspace='vision-model',org='hopkinsrandy537-org',create_ok=False)
   assert s._studio.id==SID and s._teamspace.id==TEAM
   client=s._studio_api._client.api_client;api=EndpointServiceApi(client)
   response=api.endpoint_service_get_endpoint(project_id=TEAM,ref=EID,_preload_content=False,_request_timeout=(5,20))
   try:
    assert response.status==200
    raw=json.loads(response.data)
   finally:response.release_conn()
   report['raw_readback']=summarize(raw,V1Endpoint.attribute_map,V1UpstreamCloudSpace.attribute_map)
   report['status']='PASS'
 except Exception as e:
  report['error_type']=type(e).__name__
  if isinstance(getattr(e,'status',None),int):report['http_status']=e.status
 finally:
  http.client.HTTPConnection.putrequest=original
  report['finished_at_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
  text=json.dumps(report,indent=2)
  assert not any(os.environ.get(k) and os.environ[k] in text for k in ('LIGHTNING_USER_ID','LIGHTNING_API_KEY'))
  pathlib.Path('out').mkdir(exist_ok=True);pathlib.Path('out/studio-probe.json').write_text(text+'\n')
  print('Raw original endpoint read:',report['status'])
 return 0 if report['status']=='PASS' else 1
if __name__=='__main__':
 if '--self-test' in sys.argv:test()
 else:sys.exit(main())
