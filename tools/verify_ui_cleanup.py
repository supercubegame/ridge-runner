import contextlib,http.client,json,logging,os,pathlib,sys
import cleanup_ui_link as c
import ui_link_once as b

def main():
 import urllib3.connection
 p=c.Policy();original=http.client.HTTPConnection.putrequest
 r={'status':'FAIL','kind':'ui_cleanup_readonly_verification','started_at_utc':b.now()}
 def guard(conn,method,url,*a,**k):
  b.require(method=='GET','READ_ONLY');b.require(isinstance(conn,(http.client.HTTPSConnection,urllib3.connection.HTTPSConnection)),'HTTPS')
  p.check(method,conn.host,url);return original(conn,method,url,*a,**k)
 try:
  b.scope();os.environ['LIGHTNING_DISABLE_VERSION_CHECK']='1';os.environ['LIGHTNING_DEBUG']='0';logging.disable(logging.CRITICAL)
  with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):
   http.client.HTTPConnection.putrequest=guard
   from lightning_sdk import Studio
   from lightning_sdk.api.studio_api import StudioApi
   from lightning_sdk.lightning_cloud.openapi import EndpointServiceApi
   Studio._setup=lambda s:None
   def forbidden(*a,**k):raise RuntimeError('KEEPALIVE_REFUSED')
   StudioApi.start_keeping_alive=forbidden
   s=Studio(name='peaceful-dewdney-424',teamspace='vision-model',org='hopkinsrandy537-org',create_ok=False)
   b.require(s._studio.id==b.SID and s._teamspace.id==c.TEAM,'IDENTITY')
   client=s._studio_api._client;api=EndpointServiceApi(client.api_client)
   items=s.list_ports();r['target_list_absent']=not any(e.id==c.EID or e.name==b.NAME or '8061' in [str(v) for v in (e.ports or [])] for e in items)
   try:
    api.endpoint_service_get_endpoint(project_id=c.TEAM,ref=c.EID,_request_timeout=(5,20));r['single_get']={'result':'PRESENT'}
   except Exception as e:
    body=getattr(e,'body',None)
    if isinstance(body,bytes):body=body.decode('utf-8','replace')
    text=body if isinstance(body,str) else json.dumps(body) if isinstance(body,(dict,list)) else ''
    r['single_get']={'http_status':getattr(e,'status',None),'body_type':type(body).__name__,'not_found_marker':any(x in text.lower() for x in ('not found','not exist','not_found'))}
   old=api.endpoint_service_get_endpoint(project_id=c.TEAM,ref=c.OLD,_request_timeout=(5,20))
   r['original_8060_identity_ok']=old.cloudspace.cloudspace_id==b.SID and str(old.cloudspace.port)=='8060'
   r['original_auto_start']=old.cloudspace.auto_start;r['original_command_empty']=not old.cloudspace.command
   cfg=client.cloud_space_service_get_cloud_space_instance_config(project_id=c.TEAM,id=b.SID,_request_timeout=(5,20))
   r['machine_sleep_matches_prior']=cfg.compute_config.name=='cpu-4' and cfg.compute_config.spot is False and cfg.disable_auto_shutdown is False and cfg.idle_shutdown_seconds==0
   b.require(r['target_list_absent'] and r['original_8060_identity_ok'] and r['original_auto_start'] is False and r['original_command_empty'] and r['machine_sleep_matches_prior'],'READBACK')
   r['status']='PASS'
 except Exception as e:r['error_type']=type(e).__name__
 finally:
  http.client.HTTPConnection.putrequest=original;r['finished_at_utc']=b.now();r['network']={'get':p.gets,'delete':p.deletes,'blocked':p.blocked,'writes':0}
  pathlib.Path('out').mkdir(exist_ok=True);pathlib.Path('out/studio-probe.json').write_text(b.encode_report(r,[os.environ.get(k,'') for k in ('LIGHTNING_USER_ID','LIGHTNING_API_KEY')]))
  print('Read-only verification:',r['status'])
 return 0 if r['status']=='PASS' else 1
if __name__=='__main__':sys.exit(main())
