"""Approved start only. No stop, endpoint change, keepalive, or SSH."""
import base64, contextlib, copy, http.client, json, logging, os, sys, time
import urllib.parse, urllib.error
import restart_once as h

BRANCH='audit/studio-start-only-20260920'
CLAIM='claims/studio-start-only-20260920-0914.json'

class Policy:
    def __init__(self):
        self.reads=h.Policy();self.route=None;self.armed=False;self.starts=0;self.blocked=0
    def check(self,method,host,url):
        try:
            if method=='GET':return self.reads.check(method,host,url)
            u=urllib.parse.urlsplit(url)
            actual=u.hostname if u.scheme else host.split(':')[0]
            h.require(not u.scheme or u.scheme=='https','HTTPS_ONLY')
            h.require(actual in ('lightning.ai','api.lightning.ai'),'WRITE_HOST_REFUSED')
            h.require(self.armed and self.starts==0 and self.route==(method,u.path) and not u.query,'ONLY_ONE_EXACT_START')
            self.starts+=1;self.armed=False
        except h.SafetyError:
            self.blocked+=1;raise

def check_config(name,spot,disabled,timeout):
    h.require(name=='cpu-4' and spot is False,'ORIGINAL_CPU4_REQUIRED')
    h.require(disabled is False and type(timeout) is int and timeout==0,'SLEEP_CONFIG_DRIFT')

def claim():
    h.require(os.environ['GITHUB_RUN_ATTEMPT']=='1','NO_RERUN')
    r=json.loads((h.OUT/'studio-probe.json').read_text())
    h.require(r.get('preflight')=='PASS','PREFLIGHT_REQUIRED')
    data={'run_id':os.environ['GITHUB_RUN_ID'],'sha':os.environ['GITHUB_SHA'],
          'authorization':'Start existing original cpu-4 once; no stop or endpoint writes',
          'claimed_at_utc':h.now()}
    h.github('PUT','/contents/'+CLAIM,{'branch':'studio-results','message':'Claim approved start-only recovery',
        'content':base64.b64encode(json.dumps(data).encode()).decode()})
    live=h.github('GET','/contents/'+CLAIM+'?ref=studio-results')
    h.require(json.loads(base64.b64decode(live['content']))==data,'CLAIM_READBACK')
    (h.OUT/'claim.json').write_text(json.dumps(data))

def probe(execute=False):
    import urllib3.connection
    p=Policy();original=http.client.HTTPConnection.putrequest;stage='configuration'
    r={'schema':4,'kind':'approved_start_only','status':'FAIL','checks':[],'started_at_utc':h.now(),
       'sdk_source_sha':h.SDK_SHA,'ssh':'NOT_USED','keepalive':'DISABLED','endpoint_writes':0,
       'stop_requests_sent':0,'auto_start_test':'NOT_RUN','browser':{'status':'NOT_RUN'}}
    def record(name):r['checks'].append({'name':name,'status':'PASS'})
    def save():
        r['network']={'get_requests':p.reads.gets,'blocked_requests':p.blocked,
            'start_requests_sent':p.starts,'stop_requests_sent':0,'endpoint_writes':0}
        r['last_stage']=stage;h.write_report(r)
    def guarded(conn,method,url,*a,**kw):
        h.require(isinstance(conn,(http.client.HTTPSConnection,urllib3.connection.HTTPSConnection)),'HTTPS_TRANSPORT')
        p.check(method,conn.host,url);return original(conn,method,url,*a,**kw)
    try:
        h.require(os.environ.get('GITHUB_REPOSITORY')=='supercubegame/ridge-runner','REPOSITORY')
        h.require(os.environ.get('GITHUB_REF')=='refs/heads/'+BRANCH,'BRANCH')
        h.require(os.environ.get('GITHUB_RUN_ATTEMPT')=='1','NO_RERUN')
        h.require(all(os.environ.get(k,'').strip() for k in ('LIGHTNING_USER_ID','LIGHTNING_API_KEY')),'SECRETS')
        if execute:
            receipt=json.loads((h.OUT/'claim.json').read_text())
            h.require(receipt['run_id']==os.environ['GITHUB_RUN_ID'] and receipt['sha']==os.environ['GITHUB_SHA'],'CLAIM_IDENTITY')
        manifest=json.loads((h.OUT/'expected-assets.json').read_text());h.validate_manifest(manifest)
        logging.disable(logging.CRITICAL)
        os.environ['LIGHTNING_DEBUG']='0';os.environ['LIGHTNING_DISABLE_VERSION_CHECK']='1'
        with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):
            http.client.HTTPConnection.putrequest=guarded
            stage='sdk_import'
            from lightning_sdk import Studio
            from lightning_sdk.api.studio_api import StudioApi
            from lightning_sdk.lightning_cloud.openapi.api.cloud_space_service_api import CloudSpaceServiceApi
            from lightning_sdk.lightning_cloud.openapi import CloudSpaceServiceStartCloudSpaceInstanceBody
            Studio._setup=lambda self:None
            def forbidden(*a,**kw):raise h.SafetyError('KEEPALIVE_REFUSED')
            StudioApi.start_keeping_alive=forbidden
            stage='target_lookup'
            studio=Studio(name=h.TARGET,teamspace='vision-model',org='hopkinsrandy537-org',create_ok=False)
            sid=studio._studio.id;team=studio._teamspace.id
            h.require(studio.name==h.TARGET and sid==h.TARGET_ID,'TARGET')
            client=studio._studio_api._client
            kw={'project_id':team,'id':sid,'_request_timeout':(10,30)}
            p.route=h.route_from_sdk(CloudSpaceServiceApi.cloud_space_service_start_cloud_space_instance_with_http_info,team,sid)
            def status():return client.cloud_space_service_get_cloud_space_instance_status(**kw)
            def config():return client.cloud_space_service_get_cloud_space_instance_config(**kw)
            def endpoint():
                es=[e for e in studio.list_ports() if '8060' in [str(v) for v in (e.ports or [])]]
                h.require(len(es)==1 and es[0].cloudspace is not None,'ENDPOINT')
                h.require(es[0].cloudspace.auto_start is False,'AUTO_START_NOT_FALSE')
                return es[0].cloudspace.to_dict()
            stage='preflight'
            before=status();cfg=config();compute=copy.deepcopy(cfg.compute_config)
            check_config(compute.name,compute.spot,cfg.disable_auto_shutdown,cfg.idle_shutdown_seconds)
            ep=endpoint();snap=compute.to_dict()
            active=before.in_use
            phase=active.phase if active is not None else 'CLOUD_SPACE_INSTANCE_STATE_STOPPED'
            h.require(before.requested is None and phase in ('CLOUD_SPACE_INSTANCE_STATE_STOPPED','CLOUD_SPACE_INSTANCE_STATE_RUNNING'),'TRANSITION_REFUSED')
            r['before']={'phase':phase,'compute_name':compute.name,'spot':compute.spot,
                'auto_sleep_enabled':True,'idle_timeout_seconds':0,'port_8060_auto_start':False}
            record('target_original_cpu_sleep_and_endpoint_verified')
            h.require(p.blocked==0,'UNEXPECTED_REQUEST')
            r['preflight']='PASS';save()
            if not execute:
                r['status']='PREFLIGHT_PASS';return 0
            if phase=='CLOUD_SPACE_INSTANCE_STATE_STOPPED':
                stage='start_request';r['start_requested_at_utc']=h.now();save();p.armed=True
                try:client.cloud_space_service_start_cloud_space_instance(body=CloudSpaceServiceStartCloudSpaceInstanceBody(compute_config=compute),**kw)
                except Exception as e:r['start_response_error_type']=type(e).__name__
                h.require(p.starts==1,'START_NOT_SENT')
            else:r['start_skipped']='ALREADY_RUNNING'
            stage='wait_running';deadline=time.monotonic()+600;ready=False
            while time.monotonic()<deadline:
                st=status();live=st.in_use
                ready=st.requested is None and live is not None and live.phase=='CLOUD_SPACE_INSTANCE_STATE_RUNNING' and live.startup_status is not None and live.startup_status.top_up_restore_finished is True
                if ready:break
                time.sleep(5)
            h.require(ready,'READINESS_TIMEOUT_NO_REPLAY')
            h.require(live.compute_config is not None and live.compute_config.name=='cpu-4','ACTIVE_CPU_MISMATCH')
            r['running_at_utc']=h.now();record('running_original_cpu_restore_finished')
            stage='settings_readback';after=config()
            h.require(after.compute_config.to_dict()==snap,'COMPUTE_CHANGED')
            check_config(after.compute_config.name,after.compute_config.spot,after.disable_auto_shutdown,after.idle_shutdown_seconds)
            h.require(endpoint()==ep,'ENDPOINT_CHANGED');record('settings_unchanged')
            stage='public_recovery';deadline=time.monotonic()+300;recovered=False
            while time.monotonic()<deadline:
                try:r['recovered_asset_count']=h.public_assets(manifest);recovered=True;break
                except (urllib.error.URLError,TimeoutError,h.SafetyError) as e:
                    r['last_public_error_type']=type(e).__name__;time.sleep(5)
            h.require(recovered,'PUBLIC_RECOVERY_TIMEOUT')
            r['public_recovered_at_utc']=h.now();record('all_pinned_release_assets_verified')
            h.require(p.blocked==0 and p.starts in (0,1),'NETWORK_SCOPE')
            record('start_only_no_stop_endpoint_write_or_ssh')
            r['lifecycle_status']='PASS';r['status']='AWAITING_BROWSER'
    except Exception as e:
        r['status']='FAIL';r['failure_stage']=stage;r['error_type']=type(e).__name__
        if isinstance(e,h.SafetyError):r['error_code']=str(e)
        if isinstance(getattr(e,'status',None),int):r['http_status']=e.status
    finally:
        http.client.HTTPConnection.putrequest=original
        r['finished_at_utc']=h.now();save()
        print('Start-only:',r['status'],'stage:',stage,'start requests:',p.starts)
    return 0 if r.get('lifecycle_status')=='PASS' else 1

if __name__=='__main__':
    mode=sys.argv[1]
    if mode=='--prepare':h.prepare()
    elif mode=='--claim':claim()
    elif mode=='--preflight':sys.exit(probe(False))
    elif mode=='--execute':sys.exit(probe(True))
    elif mode=='--merge-browser':sys.exit(h.merge_browser())
    else:raise SystemExit('Unknown mode')
