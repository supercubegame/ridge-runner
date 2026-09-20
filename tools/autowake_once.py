#!/usr/bin/env python3
"""Single approved endpoint Auto start experiment with bounded rollback."""
import contextlib, copy, http.client, json, logging, os, pathlib, signal, subprocess, sys, time
import urllib.request, urllib.parse
import restart_once as r
r.BRANCH='audit/studio-autowake-once-20260920'
r.CLAIM='claims/studio-autowake-20260920-0854.json'
require=r.require

class Policy:
    def __init__(self):
        self.routes={};self.armed=None;self.enabled=False;self.recovering=False;self.stopped=False
        self.public_allowed=True;self.gets=0;self.blocked=0
        self.writes={k:0 for k in ('enable','stop','rollback','fallback_start')}
    def check(self,method,host,url):
        try:
            p=urllib.parse.urlsplit(url);actual=p.hostname if p.scheme else host.split(':')[0]
            require(not p.scheme or p.scheme=='https','HTTPS_ONLY')
            require(actual in ('lightning.ai','api.lightning.ai',r.PREVIEW_HOST),'HOST_REFUSED')
            require(not any(x in p.path.lower() for x in ('keepalive','keep-alive','keep_alive','report-stop-at')),'KEEPALIVE_REFUSED')
            if method=='GET':
                require(actual!=r.PREVIEW_HOST or self.public_allowed,'QUIET_WINDOW_PUBLIC_REQUEST')
                self.gets+=1;return
            k=self.armed
            require(actual in ('lightning.ai','api.lightning.ai'),'WRITE_HOST')
            require(k in self.routes and self.routes[k]==(method,p.path) and not p.query,'WRITE_ROUTE')
            require(self.writes[k]==0,'WRITE_REPLAY')
            require(k!='stop' or self.enabled,'ENABLE_NOT_VERIFIED')
            require(k not in ('rollback','fallback_start') or self.recovering,'RECOVERY_ONLY')
            require(k!='fallback_start' or self.stopped,'START_REQUIRES_STOPPED')
            self.writes[k]+=1;self.armed=None
        except r.SafetyError:self.blocked+=1;raise

def browser_env(env):
    return {k:v for k,v in env.items() if k in ('PATH','HOME','LANG','TMPDIR','PLAYWRIGHT_BROWSERS_PATH')}
def is_stopped(status):
    return status.requested is None and (status.in_use is None or status.in_use.phase=='CLOUD_SPACE_INSTANCE_STATE_STOPPED')
def is_ready(status):
    v=status.in_use
    return v is not None and v.phase=='CLOUD_SPACE_INSTANCE_STATE_RUNNING' and v.startup_status is not None and v.startup_status.top_up_restore_finished is True
def endpoint_config(endpoint):
    keys=('name','ports','auth','custom_domain','lightning_subdomain','prewarm','proxy','urls','cloudspace','job','managed','openai')
    return {k:endpoint.to_dict().get(k) for k in keys}
def browser_check():
    result=subprocess.run(['node','tools/restart_browser.cjs'],env=browser_env(os.environ),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=180)
    path=r.OUT/'browser.json'
    value=json.loads(path.read_text()) if path.exists() else {}
    checks=[{'name':c['name'],'pass':c['pass']} for c in value.get('checks',[])]
    ok=result.returncode==0 and value.get('status')=='PASS' and len(checks)==5 and all(c['pass'] is True for c in checks)
    return {'status':'PASS' if ok else 'FAIL','checks':checks,'renderer':'Chromium SwiftShader; not real-device acceptance'}

def probe(execute=False):
    import urllib3.connection
    policy=Policy();original=http.client.HTTPConnection.putrequest
    report={'schema':4,'kind':'single_approved_url_autowake','status':'FAIL','started_at_utc':r.now(),
        'checks':[],'ssh':'NOT_USED','keepalive':'DISABLED','natural_idle_sleep_test':'NOT_RUN',
        'service_repair':'NOT_RUN','rollback':'NOT_NEEDED','browser':{'status':'NOT_RUN'}}
    stage='configuration';client=None;original_endpoint=None;compute=None;kwargs=None
    def record(name,detail):report['checks'].append({'name':name,'status':'PASS','detail':detail})
    def save():
        report['network']={'get_requests':policy.gets,'blocked_requests':policy.blocked,**policy.writes}
        report['last_stage']=stage;r.write_report(report)
    def guarded(conn,method,url,*args,**kw):
        require(isinstance(conn,(http.client.HTTPSConnection,urllib3.connection.HTTPSConnection)),'HTTPS_TRANSPORT')
        policy.check(method,conn.host,url);return original(conn,method,url,*args,**kw)
    def wait_for(predicate,seconds):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            current=status()
            if predicate(current):return current
            time.sleep(5)
        raise r.SafetyError('STATE_WAIT_TIMEOUT')
    def fail_info(error):
        result={'error_type':type(error).__name__}
        if isinstance(error,r.SafetyError):result['error_code']=str(error)
        if isinstance(getattr(error,'status',None),int):result['http_status']=error.status
        return result
    def status():return client.cloud_space_service_get_cloud_space_instance_status(**kwargs)
    def config():return client.cloud_space_service_get_cloud_space_instance_config(**kwargs)
    def endpoint():return client.endpoint_service_get_endpoint(project_id=team,ref=eid,_request_timeout=(10,30))
    def update_endpoint(kind,value):
        body=EndpointServiceUpdateEndpointBody()
        # Preserve all writable existing settings; only auto_start changes.
        for key in body.swagger_types:
            if key not in ('created_at','updated_at','user_id'):
                setattr(body,key,copy.deepcopy(getattr(original_endpoint,key,None)))
        body.cloudspace.auto_start=value;policy.armed=kind
        client.endpoint_service_update_endpoint(body=body,project_id=team,id=eid,_request_timeout=(10,30))
    def rollback():
        nonlocal stage
        policy.recovering=True;policy.public_allowed=True
        stage='rollback_endpoint';save()
        try:
            if endpoint().cloudspace.auto_start is not False:
                try:update_endpoint('rollback',False)
                except Exception as error:report['rollback_response']=fail_info(error)
            require(endpoint_config(endpoint())==endpoint_config(original_endpoint),'ROLLBACK_CONFIG_MISMATCH')
            report['rollback']='PASS'
        except Exception as error:report['rollback']='FAIL';report['rollback_error']=fail_info(error)
        if policy.writes['stop']:
            stage='fallback_recovery';save()
            try:
                state=wait_for(lambda s:is_stopped(s) or is_ready(s),300)
                if is_stopped(state):
                    policy.stopped=True;policy.armed='fallback_start'
                    try:client.cloud_space_service_start_cloud_space_instance(body=CloudSpaceServiceStartCloudSpaceInstanceBody(compute_config=compute),**kwargs)
                    except Exception as error:report['fallback_start_response']=fail_info(error)
                    state=wait_for(is_ready,600)
                require(state.in_use.compute_config.name==compute.name,'FALLBACK_MACHINE_MISMATCH')
                report['fallback_cpu_recovery']='PASS'
                report['fallback_assets']=r.public_assets(manifest)
            except Exception as error:report['fallback_cpu_recovery']='FAIL';report['fallback_error']=fail_info(error)
    try:
        require(os.environ.get('GITHUB_REPOSITORY')=='supercubegame/ridge-runner','REPOSITORY')
        require(os.environ.get('GITHUB_REF')=='refs/heads/'+r.BRANCH,'BRANCH')
        require(os.environ.get('GITHUB_RUN_ATTEMPT')=='1','NO_RERUN')
        require(all(os.environ.get(k,'').strip() for k in ('LIGHTNING_API_KEY','LIGHTNING_USER_ID')),'CREDENTIALS')
        if execute:
            receipt=json.loads((r.OUT/'claim.json').read_text())
            require(receipt['run_id']==os.environ['GITHUB_RUN_ID'] and receipt['sha']==os.environ['GITHUB_SHA'],'CLAIM_IDENTITY')
        manifest=json.loads((r.OUT/'expected-assets.json').read_text());r.validate_manifest(manifest)
        logging.disable(logging.CRITICAL);os.environ['LIGHTNING_DEBUG']='0';os.environ['LIGHTNING_DISABLE_VERSION_CHECK']='1'
        with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):
            http.client.HTTPConnection.putrequest=guarded
            from lightning_sdk import Studio
            from lightning_sdk.machine import Machine
            from lightning_sdk.api.studio_api import StudioApi
            from lightning_sdk.lightning_cloud.openapi.api.endpoint_service_api import EndpointServiceApi
            from lightning_sdk.lightning_cloud.openapi.api.cloud_space_service_api import CloudSpaceServiceApi
            from lightning_sdk.lightning_cloud.openapi import EndpointServiceUpdateEndpointBody,CloudSpaceServiceStartCloudSpaceInstanceBody
            Studio._setup=lambda s:None
            def forbidden(*a,**kw):raise r.SafetyError('KEEPALIVE_REFUSED')
            StudioApi.start_keeping_alive=forbidden
            stage='target_lookup'
            studio=Studio(name=r.TARGET,teamspace='vision-model',org='hopkinsrandy537-org',create_ok=False)
            require(studio.name==r.TARGET and studio._studio.id==r.TARGET_ID,'TARGET_MISMATCH')
            team=studio._teamspace.id;sid=studio._studio.id;client=studio._studio_api._client
            kwargs={'project_id':team,'id':sid,'_request_timeout':(10,30)}
            initial=status();require(is_ready(initial) and initial.requested is None and studio.machine==Machine.CPU,'STABLE_CPU_REQUIRED')
            before_config=config();compute=copy.deepcopy(before_config.compute_config)
            require(compute.name=='cpu-4' and compute.spot is False,'CPU_CONFIG_MISMATCH')
            matches=[e for e in studio.list_ports() if '8060' in [str(p) for p in (e.ports or [])]]
            require(len(matches)==1,'ENDPOINT_COUNT');eid=matches[0].id
            original_endpoint=copy.deepcopy(endpoint());up=original_endpoint.cloudspace
            require(up is not None and up.cloudspace_id==sid and str(up.port)=='8060','ENDPOINT_TARGET')
            require(up.type=='ENDPOINT_PLUGIN_PORT' and up.auto_start is False,'ENDPOINT_PRECONDITION')
            require(up.instance_type in (None,'','cpu-4') and up.cluster_id in (None,'',studio._studio.cluster_id),'WAKE_MACHINE_AMBIGUOUS')
            require(not up.command and not up.studio_job_id,'EXTRA_START_COMMAND_OR_JOB')
            require(r.PREVIEW in [u.rstrip('/') for u in (original_endpoint.urls or [])],'URL_MISMATCH')
            report['before']={'machine':compute.name,'auto_start':False,'wake_machine_field':up.instance_type or 'UNSET',
                'auto_sleep_enabled':not before_config.disable_auto_shutdown,'idle_timeout_seconds':before_config.idle_shutdown_seconds}
            ep_route=r.route_from_sdk(EndpointServiceApi.endpoint_service_update_endpoint_with_http_info,team,eid)
            policy.routes={'enable':ep_route,'rollback':ep_route,
                'stop':r.route_from_sdk(CloudSpaceServiceApi.cloud_space_service_stop_cloud_space_instance_with_http_info,team,sid),
                'fallback_start':r.route_from_sdk(CloudSpaceServiceApi.cloud_space_service_start_cloud_space_instance_with_http_info,team,sid)}
            stage='preflight_public';report['preflight_assets']=r.public_assets(manifest)
            require(policy.blocked==0,'UNEXPECTED_REQUEST')
            report['preflight']='PASS';record('preflight','Exact Studio and existing 8060 endpoint; same CPU; matching public release')
            if not execute:report['status']='PREFLIGHT_PASS';return 0
            stage='enable_autostart';save()
            try:update_endpoint('enable',True)
            except Exception as error:report['enable_response']=fail_info(error)
            expected=endpoint_config(original_endpoint);expected['cloudspace']['auto_start']=True
            require(endpoint_config(endpoint())==expected,'ENABLE_READBACK_MISMATCH')
            require(config().to_dict()==before_config.to_dict(),'STUDIO_CONFIG_CHANGED')
            policy.enabled=True;record('enable_readback','Only Auto start changed; original URL, auth and all compared settings preserved')
            stage='stop_once';policy.public_allowed=False;report['stop_requested_at_utc']=r.now();save()
            policy.armed='stop'
            try:client.cloud_space_service_stop_cloud_space_instance(**kwargs)
            except Exception as error:report['stop_response']=fail_info(error)
            require(policy.writes['stop']==1,'STOP_NOT_SENT')
            stage='wait_stopped';wait_for(is_stopped,300);report['stopped_at_utc']=r.now()
            # Three further samples establish a 15s no-preview baseline.
            for _ in range(3):
                time.sleep(5);require(is_stopped(status()),'EXTERNAL_WAKE_DURING_QUIET_WINDOW')
            record('quiet_stopped_baseline','Confirmed stopped, then 15 seconds without public requests or start API')
            stage='url_wake';policy.public_allowed=True;report['wake_request_at_utc']=r.now();save()
            request=urllib.request.Request(r.PREVIEW+'/version.json?autowake_probe='+str(time.time_ns()),headers={'Cache-Control':'no-cache'})
            try:
                with urllib.request.urlopen(request,timeout=15) as response:
                    report['wake_http_status']=response.status;response.read(65536)
            except Exception as error:
                report['wake_response']=fail_info(error)
                if isinstance(getattr(error,'code',None),int):report['wake_http_status']=error.code
            stage='wait_url_started';live=wait_for(is_ready,600)
            report['running_at_utc']=r.now()
            require(policy.writes['fallback_start']==0,'CONTAMINATED_BY_START_API')
            require(live.in_use.compute_config.name==compute.name,'WAKE_MACHINE_MISMATCH')
            record('url_triggered_running','Running after public URL request; zero explicit start requests during experiment')
            stage='public_recovery';deadline=time.monotonic()+300;recovered=False
            while time.monotonic()<deadline:
                try:report['recovered_assets']=r.public_assets(manifest);recovered=True;break
                except Exception as error:report['last_public_error']=fail_info(error);time.sleep(5)
            require(recovered,'ASSET_RECOVERY_TIMEOUT');report['public_recovered_at_utc']=r.now()
            record('public_release_recovered','All 13 assets match pinned release; no SSH, redeployment or manual server start')
            stage='browser';save();report['browser']=browser_check()
            require(report['browser']['status']=='PASS','BROWSER_FAILED')
            stage='final_config_readback'
            require(endpoint_config(endpoint())==expected,'FINAL_ENDPOINT_MISMATCH')
            require(config().to_dict()==before_config.to_dict(),'FINAL_STUDIO_CONFIG_MISMATCH')
            require(policy.blocked==0 and policy.writes=={'enable':1,'stop':1,'rollback':0,'fallback_start':0},'NETWORK_SCOPE')
            report['after']={'auto_start':True,'machine':'cpu-4','sleep_and_compute_config_unchanged':True}
            record('settings_and_scope','Auto start retained enabled; all other compared settings unchanged; exactly one enable and stop')
            report['status']='PASS'
    except Exception as error:
        report['status']='FAIL';report['failure_stage']=stage;report.update(fail_info(error))
        if execute and policy.writes['enable']:
            with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):rollback()
    finally:
        http.client.HTTPConnection.putrequest=original
        report['finished_at_utc']=r.now();save()
        print('Autowake:',report['status'],'stage:',stage,'writes:',policy.writes)
    return 0 if report['status']=='PASS' else 1

def claim():
    require(os.environ['GITHUB_RUN_ATTEMPT']=='1','RERUN_REFUSED')
    require(json.loads((r.OUT/'studio-probe.json').read_text()).get('preflight')=='PASS','PREFLIGHT_REQUIRED')
    data={'run_id':os.environ['GITHUB_RUN_ID'],'sha':os.environ['GITHUB_SHA'],'claimed_at_utc':r.now(),
        'authorization':'Enable existing 8060 Auto start, stop once, URL wake; retain on success; restore flag and same-CPU start on failure'}
    r.github('PUT','/contents/'+r.CLAIM,{'branch':'studio-results','message':'Claim single approved URL autowake experiment',
        'content':r.base64.b64encode(json.dumps(data).encode()).decode()})
    live=r.github('GET','/contents/'+r.CLAIM+'?ref=studio-results')
    require(json.loads(r.base64.b64decode(live['content']))==data,'CLAIM_READBACK')
    (r.OUT/'claim.json').write_text(json.dumps(data))
    print('One-use autowake authorization claimed and read back')

if __name__=='__main__':
    mode=sys.argv[1]
    if mode=='--prepare':r.prepare()
    elif mode=='--claim':claim()
    elif mode=='--preflight':sys.exit(probe(False))
    elif mode=='--execute':sys.exit(probe(True))
    else:raise SystemExit('Unknown mode')
