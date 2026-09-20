"""Delete only the captured UI-link endpoint under the existing approval."""
import contextlib,copy,http.client,json,logging,os,pathlib,sys,urllib.parse
import ui_link_once as b
b.BRANCH='audit/ui-link-cleanup-20260920'
b.CLAIM='claims/ui-link-cleanup-20260920-1141.json'
EID='endp_01m2yet8wyks3ts2rcdzfppzqc'
TEAM='01hrhh1avmp22zbv37depwjkp8'
OLD='endp_01m2x511jn86kwsqt5eh3pkws1'
URL='https://8061-01m2watakghqmc1fnymkg5czax.cloudspaces.litng.ai'
class Policy:
 def __init__(self):self.armed=False;self.deletes=0;self.gets=0;self.blocked=0
 def check(self,method,host,url):
  try:
   u=urllib.parse.urlsplit(url);host=u.hostname if u.scheme else host.split(':')[0]
   b.require(not u.scheme or u.scheme=='https','HTTPS')
   b.require(host in ('lightning.ai','api.lightning.ai'),'HOST')
   b.require(not any(v in u.path.lower() for v in ('keepalive','keep-alive','keep_alive','report-stop-at')),'KEEPALIVE')
   if method=='GET':self.gets+=1;return
   b.require(self.armed and method=='DELETE' and u.path=='/v1/projects/'+TEAM+'/endpoints/'+EID and not u.query and self.deletes==0,'WRITE_REFUSED')
   self.deletes+=1;self.armed=False
  except Exception:self.blocked+=1;raise
def validate(e):
 b.require(b.owned(e,EID,TEAM,OLD),'IDENTITY')
 b.require(e.cloudspace.auto_start is False and not e.cloudspace.command and e.cloudspace.type=='ENDPOINT_PLUGIN_API','CONFIG_CHANGED')
def test():
 from types import SimpleNamespace as N
 b.selftest();count=0
 for method,path in [('POST','/start'),('POST','/stop'),('POST','/execute'),('POST','/v1/projects/'+TEAM+'/endpoints'),('DELETE','/v1/projects/'+TEAM+'/endpoints/'+OLD),('PUT','/v1/projects/'+TEAM+'/endpoints/'+EID)]:
  p=Policy();p.armed=True
  try:p.check(method,'lightning.ai',path)
  except RuntimeError:count+=1
  else:raise AssertionError('SCOPE')
 p=Policy();p.armed=True;p.check('DELETE','lightning.ai','/v1/projects/'+TEAM+'/endpoints/'+EID);p.armed=True
 try:p.check('DELETE','lightning.ai','/v1/projects/'+TEAM+'/endpoints/'+EID)
 except RuntimeError:count+=1
 else:raise AssertionError('REPLAY')
 e=N(id=EID,project_id=TEAM,name=b.NAME,ports=['8061'],cloudspace=N(cloudspace_id=b.SID,port='8061',auto_start=False,command='',type='ENDPOINT_PLUGIN_API'))
 validate(e);count+=1;e.id=OLD
 try:validate(e)
 except RuntimeError:count+=1
 else:raise AssertionError('ORIGINAL')
 print('PASS',count,'additional exact-delete checks')
def execute():
 import urllib3.connection
 p=Policy();original=http.client.HTTPConnection.putrequest;stage='scope'
 r={'status':'FAIL','kind':'approved_ui_link_cleanup','started_at_utc':b.now(),'captured_url':URL,'endpoint_id':EID,'service':'NOT_STARTED','public_http':'NOT_REQUESTED','checks':[]}
 private=[os.environ.get(k,'') for k in ('LIGHTNING_USER_ID','LIGHTNING_API_KEY')]
 def guard(conn,method,url,*a,**k):
  b.require(isinstance(conn,(http.client.HTTPSConnection,urllib3.connection.HTTPSConnection)),'HTTPS_TRANSPORT')
  p.check(method,conn.host,url);return original(conn,method,url,*a,**k)
 try:
  b.scope();receipt=json.loads(pathlib.Path('out/ui-link-claim.json').read_text())
  b.require(receipt['sha']==os.environ['GITHUB_SHA'] and receipt['run_id']==os.environ['GITHUB_RUN_ID'],'CLAIM')
  b.require(all(private),'CREDENTIALS')
  os.environ['LIGHTNING_DEBUG']='0';os.environ['LIGHTNING_DISABLE_VERSION_CHECK']='1';logging.disable(logging.CRITICAL)
  with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):
   http.client.HTTPConnection.putrequest=guard
   from lightning_sdk import Studio
   from lightning_sdk.api.studio_api import StudioApi
   from lightning_sdk.lightning_cloud.openapi import EndpointServiceApi
   Studio._setup=lambda s:None
   def forbidden(*a,**k):raise RuntimeError('KEEPALIVE_REFUSED')
   StudioApi.start_keeping_alive=forbidden
   s=Studio(name='peaceful-dewdney-424',teamspace='vision-model',org='hopkinsrandy537-org',create_ok=False)
   b.require(s._studio.id==b.SID and s._teamspace.id==TEAM,'STUDIO_TEAM')
   client=s._studio_api._client;api=EndpointServiceApi(client.api_client)
   stage='identity_preflight'
   target=api.endpoint_service_get_endpoint(project_id=TEAM,ref=EID,_request_timeout=(5,20));validate(target)
   r['checks'].append('exact_created_endpoint_identity_and_no_autostart')
   old=api.endpoint_service_get_endpoint(project_id=TEAM,ref=OLD,_request_timeout=(5,20));old_snapshot=copy.deepcopy(old.to_dict())
   b.require(old.cloudspace.cloudspace_id==b.SID and str(old.cloudspace.port)=='8060','ORIGINAL_IDENTITY')
   kw={'project_id':TEAM,'id':b.SID,'_request_timeout':(5,20)}
   cfg=client.cloud_space_service_get_cloud_space_instance_config(**kw)
   snap=(copy.deepcopy(cfg.compute_config.to_dict()),cfg.disable_auto_shutdown,cfg.idle_shutdown_seconds)
   stage='delete_once';p.armed=True
   api.endpoint_service_delete_endpoint(project_id=TEAM,id=EID,_request_timeout=(5,25))
   r['delete_returned']=True
   stage='verify_removal'
   items=s.list_ports()
   r['list_absent']=not any(e.id==EID or e.name==b.NAME or '8061' in [str(v) for v in (e.ports or [])] for e in items)
   try:
    api.endpoint_service_get_endpoint(project_id=TEAM,ref=EID,_request_timeout=(5,20))
    r['single_get']={'result':'STILL_PRESENT'}
   except Exception as e:
    body=getattr(e,'body','') or ''
    r['single_get']={'error_type':type(e).__name__,'http_status':getattr(e,'status',None),'not_found_marker':any(x in body.lower() for x in ('not found','not exist','not_found'))}
   after=api.endpoint_service_get_endpoint(project_id=TEAM,ref=OLD,_request_timeout=(5,20))
   r['original_8060_unchanged']=after.to_dict()==old_snapshot
   cfg=client.cloud_space_service_get_cloud_space_instance_config(**kw)
   r['machine_sleep_unchanged']=(cfg.compute_config.to_dict(),cfg.disable_auto_shutdown,cfg.idle_shutdown_seconds)==snap
   b.require(r['list_absent'] and r['original_8060_unchanged'] and r['machine_sleep_unchanged'],'READBACK')
   r['checks'].extend(['target_absent_from_endpoint_list','original_8060_unchanged','machine_sleep_unchanged'])
   b.require(p.deletes==1 and p.blocked==0,'NETWORK');r['status']='PASS'
 except Exception as e:
  r['error_type']=type(e).__name__
  if type(e) is RuntimeError and str(e).isupper():r['error_code']=str(e)
  if isinstance(getattr(e,'status',None),int):r['http_status']=e.status
 finally:
  http.client.HTTPConnection.putrequest=original
  r['last_stage']=stage;r['finished_at_utc']=b.now();r['network']={'get':p.gets,'delete':p.deletes,'blocked':p.blocked,'create':0,'command':0,'studio_start_stop':0}
  pathlib.Path('out').mkdir(exist_ok=True);pathlib.Path('out/studio-probe.json').write_text(b.encode_report(r,private));print('Cleanup:',r['status'])
 return 0 if r['status']=='PASS' else 1
if __name__=='__main__':
 if '--self-test' in sys.argv:test()
 elif '--claim' in sys.argv:
  import base64
  b.scope()
  data={'run_id':os.environ['GITHUB_RUN_ID'],'sha':os.environ['GITHUB_SHA'],'approval':'11:41 approved deletion of exact newly created endpoint after UI link capture; link captured 12:01','endpoint_id':EID,'at':b.now()}
  b.github('PUT','/contents/'+b.CLAIM,{'branch':'studio-results','message':'Claim previously approved exact endpoint cleanup','content':base64.b64encode(json.dumps(data).encode()).decode()})
  live=b.github('GET','/contents/'+b.CLAIM+'?ref=studio-results')
  b.require(json.loads(base64.b64decode(live['content']))==data,'CLAIM_READBACK')
  pathlib.Path('out').mkdir(exist_ok=True);pathlib.Path('out/ui-link-claim.json').write_text(json.dumps(data))
 else:sys.exit(execute())
