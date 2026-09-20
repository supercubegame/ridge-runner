import contextlib,datetime,http.client,json,logging,os,pathlib,sys,urllib.parse
from endpoint_readonly import check_request,ReadOnlyViolation
SID='01m2watakghqmc1fnymkg5czax'
TEAM='01hrhh1avmp22zbv37depwjkp8'
EID='endp_01m2x511jn86kwsqt5eh3pkws1'
BASE='/v1/projects/'+TEAM+'/endpoints'
EXPECTED='https://8060-'+SID+'.cloudspaces.litng.ai'
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def summary(raw):
 assert isinstance(raw,dict) and raw.get('id')==EID and raw.get('projectId')==TEAM
 c=raw.get('cloudspace');assert isinstance(c,dict) and c.get('cloudspaceId')==SID and c.get('port')=='8060' and raw.get('ports')==['8060']
 assert c.get('autoStart') is False and not c.get('command') and c.get('type')=='ENDPOINT_PLUGIN_PORT'
 urls=raw.get('urls');assert urls is None or isinstance(urls,list)
 return {'identity_verified':True,'urls_key_present':'urls' in raw,'urls_is_null':urls is None,'urls_count':len(urls or []),'urls_exact_public_address':urls==[EXPECTED],'urls_empty':urls==[]}
def test():
 a={'id':EID,'projectId':TEAM,'ports':['8060'],'cloudspace':{'cloudspaceId':SID,'port':'8060','autoStart':False,'command':'','type':'ENDPOINT_PLUGIN_PORT'},'urls':[EXPECTED],'auth':{'password':'sentinel-secret'}}
 assert summary(a)['urls_exact_public_address'];assert 'sentinel' not in json.dumps(summary(a))
 a['urls']=[];assert summary(a)['urls_empty']
 a.pop('urls');assert not summary(a)['urls_key_present']
 a['urls']=['https://secret.invalid'];assert not summary(a)['urls_exact_public_address'] and 'secret.invalid' not in json.dumps(summary(a))
 a['id']='wrong'
 try:summary(a)
 except AssertionError:pass
 else:raise AssertionError('identity')
 print('PASS URL shape, identity and no raw URL/auth disclosure fixtures')
def main():
 import urllib3.connection
 r={'kind':'raw_list_detail_url_parity','status':'FAIL','started_at_utc':now(),'network':{'get':0,'writes':0,'blocked':0},'rounds':[],'public_requests':0,'studio_commands':0,'studio_constructed_without_setup':False}
 original=http.client.HTTPConnection.putrequest
 def guard(conn,method,url,*a,**kw):
  try:
   if not isinstance(conn,(http.client.HTTPSConnection,urllib3.connection.HTTPSConnection)):raise ReadOnlyViolation()
   check_request(method,conn.host,url)
   if r['network']['get']>=14:raise ReadOnlyViolation()
   u=urllib.parse.urlsplit(url)
   if '/endpoints' in u.path:
    if u.path==BASE:
     if urllib.parse.parse_qs(u.query)!={'cloudspaceId':[SID]}:raise ReadOnlyViolation()
    elif u.path!=BASE+'/'+EID or u.query:raise ReadOnlyViolation()
  except Exception:r['network']['blocked']+=1;raise
  r['network']['get']+=1;return original(conn,method,url,*a,**kw)
 def raw_call(fn,**kw):
  response=fn(_preload_content=False,_request_timeout=(5,20),**kw)
  try:
   assert response.status==200
   return json.loads(response.data)
  finally:response.release_conn()
 try:
  assert os.environ['GITHUB_REF']=='refs/heads/audit/endpoint-url-parity-20260920' and os.environ['GITHUB_RUN_ATTEMPT']=='1'
  assert all(os.environ.get(k) for k in ('LIGHTNING_USER_ID','LIGHTNING_API_KEY'))
  os.environ['LIGHTNING_DEBUG']='0';os.environ['LIGHTNING_DISABLE_VERSION_CHECK']='1';logging.disable(logging.CRITICAL)
  with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):
   http.client.HTTPConnection.putrequest=guard
   from lightning_sdk import Studio
   from lightning_sdk.api.studio_api import StudioApi
   from lightning_sdk.lightning_cloud.openapi import EndpointServiceApi
   Studio._setup=lambda s:None
   def forbidden(*a,**kw):raise ReadOnlyViolation()
   StudioApi.start_keeping_alive=forbidden
   s=Studio(name='peaceful-dewdney-424',teamspace='vision-model',org='hopkinsrandy537-org',create_ok=False)
   r['studio_constructed_without_setup']=True
   assert s._studio.id==SID and s._teamspace.id==TEAM
   api=EndpointServiceApi(s._studio_api._client.api_client)
   saved=[]
   for order in ('list_then_detail','detail_then_list'):
    started=now()
    def get_list():
     body=raw_call(api.endpoint_service_list_endpoints,project_id=TEAM,cloudspace_id=SID)
     matches=[e for e in body['endpoints'] if e.get('id')==EID];assert len(matches)==1
     return matches[0]
    def get_detail():return raw_call(api.endpoint_service_get_endpoint,project_id=TEAM,ref=EID)
    if order=='list_then_detail':listing=get_list();detail=get_detail()
    else:detail=get_detail();listing=get_list()
    r['rounds'].append({'order':order,'started_at_utc':started,'finished_at_utc':now(),'list':summary(listing),'detail':summary(detail),'same_cloudspace_object':listing.get('cloudspace')==detail.get('cloudspace'),'same_ports':listing.get('ports')==detail.get('ports'),'same_created_at':listing.get('createdAt')==detail.get('createdAt'),'same_updated_at':listing.get('updatedAt')==detail.get('updatedAt'),'same_name':listing.get('name')==detail.get('name')})
    saved.append((listing,detail))
   r['list_stable_across_rounds']=summary(saved[0][0])==summary(saved[1][0]) and saved[0][0].get('cloudspace')==saved[1][0].get('cloudspace')
   r['detail_stable_across_rounds']=summary(saved[0][1])==summary(saved[1][1]) and saved[0][1].get('cloudspace')==saved[1][1].get('cloudspace')
   r['status']='PASS'
 except Exception as e:
  r['error_type']=type(e).__name__
  if isinstance(getattr(e,'status',None),int):r['http_status']=e.status
 finally:
  http.client.HTTPConnection.putrequest=original;r['finished_at_utc']=now()
  text=json.dumps(r,indent=2);assert not any(os.environ.get(k) and os.environ[k] in text for k in ('LIGHTNING_USER_ID','LIGHTNING_API_KEY'))
  pathlib.Path('out').mkdir(exist_ok=True);pathlib.Path('out/studio-probe.json').write_text(text+'\n');print(r['status'])
 return 0 if r['status']=='PASS' else 1
if __name__=='__main__':
 if '--self-test' in sys.argv:test()
 else:sys.exit(main())
