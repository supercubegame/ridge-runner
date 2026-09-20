#!/usr/bin/env python3
"""One approved stop/start, durable one-use claim, no SSH or service repair."""
import ast, base64, contextlib, copy, datetime, hashlib, http.client, inspect
import io, json, logging, os, pathlib, re, sys, textwrap, time
import urllib.error, urllib.parse, urllib.request, zipfile

TARGET='peaceful-dewdney-424'
TARGET_ID='01m2watakghqmc1fnymkg5czax'
PREVIEW_HOST='8060-'+TARGET_ID+'.cloudspaces.litng.ai'
PREVIEW='https://'+PREVIEW_HOST
BRANCH='audit/studio-restart-once-20260920'
CLAIM='claims/studio-restart-20260920-0839.json'
SDK_SHA='a7709959692a4abdcd152f381585eb1de826923b'
OUT=pathlib.Path('out')
class SafetyError(RuntimeError):pass
def require(ok, code):
    if not ok:raise SafetyError(code)
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def safe_json(data,secrets):
    text=json.dumps(data,indent=2)
    require(not any(v and v in text for v in secrets),'CREDENTIAL_OUTPUT_REFUSED')
    return text
def write_report(report):
    OUT.mkdir(exist_ok=True)
    secrets=[os.environ.get(k,'') for k in ('LIGHTNING_USER_ID','LIGHTNING_API_KEY','GH_TOKEN')]
    (OUT/'studio-probe.json').write_text(safe_json(report,secrets)+'\n')

class Policy:
    def __init__(self):
        self.routes={};self.armed=None;self.stopped=False
        self.writes={'stop':0,'start':0};self.gets=0;self.blocked=0
    def check(self,method,host,url):
        try:
            parsed=urllib.parse.urlsplit(url)
            actual=parsed.hostname if parsed.scheme else host.split(':')[0]
            require(not parsed.scheme or parsed.scheme=='https','HTTPS_ONLY')
            require(actual in ('lightning.ai','api.lightning.ai',PREVIEW_HOST),'HOST_REFUSED')
            require(not any(x in parsed.path.lower() for x in ('keepalive','keep-alive','keep_alive','report-stop-at')),'KEEPALIVE_REFUSED')
            if method=='GET':
                self.gets+=1;return
            kind=self.armed
            require(actual in ('lightning.ai','api.lightning.ai'),'WRITE_HOST_REFUSED')
            require(kind in self.routes and self.routes[kind]==(method,parsed.path) and not parsed.query,'WRITE_ROUTE_REFUSED')
            require(self.writes[kind]==0,'WRITE_REPLAY_REFUSED')
            require(kind!='start' or (self.stopped and self.writes['stop']==1),'START_BEFORE_STOP_REFUSED')
            self.writes[kind]+=1;self.armed=None
        except SafetyError:
            self.blocked+=1;raise

def route_from_sdk(method,team,studio):
    tree=ast.parse(textwrap.dedent(inspect.getsource(method)))
    calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='call_api']
    require(len(calls)==1,'SDK_ROUTE_AMBIGUOUS')
    path,verb=[ast.literal_eval(x) for x in calls[0].args[:2]]
    require(verb in ('POST','PUT','DELETE'),'SDK_ROUTE_METHOD')
    replacements={'project_id':team,'projectId':team,'id':studio,'cloudspace_id':studio,'cloudspaceId':studio}
    for k,v in replacements.items():path=path.replace('{'+k+'}',urllib.parse.quote(v,safe=''))
    require('{' not in path and studio in path and team in path,'SDK_ROUTE_TARGET')
    return verb,path

def validate_manifest(manifest):
    require(isinstance(manifest,dict) and 3<=len(manifest)<=200,'ASSET_MANIFEST_EMPTY')
    for name,digest in manifest.items():
        require(isinstance(name,str) and not name.startswith('/') and '\\' not in name and all(p not in ('.','..') and not p.startswith('.') for p in name.split('/')),'ASSET_PATH_REFUSED')
        require(isinstance(digest,str) and re.fullmatch('[a-f0-9]{64}',digest),'ASSET_HASH_REFUSED')
    require('index.html' in manifest and 'version.json' in manifest and any(n.endswith('.wasm') for n in manifest),'ASSET_MANIFEST_INCOMPLETE')

def prepare():
    # No platform credentials are supplied to this mode.
    from studio_remote import ARCHIVE_URL,ARCHIVE_SHA,ARCHIVE_SIZE,VERSION,safe_members
    with urllib.request.urlopen(ARCHIVE_URL,timeout=60) as r:data=r.read(ARCHIVE_SIZE+1)
    require(len(data)==ARCHIVE_SIZE and hashlib.sha256(data).hexdigest()==ARCHIVE_SHA,'RELEASE_CHECKSUM')
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        manifest={m.filename:hashlib.sha256(z.read(m)).hexdigest() for m in safe_members(z) if not m.is_dir()}
    manifest['version.json']=hashlib.sha256((json.dumps(VERSION,sort_keys=True)+'\n').encode()).hexdigest()
    validate_manifest(manifest);OUT.mkdir(exist_ok=True)
    (OUT/'expected-assets.json').write_text(json.dumps(manifest))
    source=pathlib.Path('tools/browser_smoke.cjs').read_text()
    require(source.count("'http://127.0.0.1:8060'")==1,'BROWSER_TARGET_ANCHOR')
    pathlib.Path('tools/restart_browser.cjs').write_text(source.replace("'http://127.0.0.1:8060'",repr(PREVIEW)))
    print('Pinned release and browser assertions prepared')

def public_assets(manifest):
    for name,digest in manifest.items():
        url=PREVIEW+'/'+urllib.parse.quote(name,safe='/')+'?restart_probe='+str(time.time_ns())
        request=urllib.request.Request(url,headers={'Cache-Control':'no-cache'})
        with urllib.request.urlopen(request,timeout=25) as response:
            data=response.read(100*1024*1024)
            require(hashlib.sha256(data).hexdigest()==digest,'PUBLIC_ASSET_CHECKSUM')
            if name.endswith('.wasm'):require(response.headers.get_content_type()=='application/wasm','WASM_MIME')
    return len(manifest)

def github(method,path,data=None):
    request=urllib.request.Request('https://api.github.com/repos/supercubegame/ridge-runner'+path,
        data=None if data is None else json.dumps(data).encode(),method=method,
        headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json'})
    with urllib.request.urlopen(request,timeout=40) as r:return json.load(r)
def claim():
    require(os.environ['GITHUB_RUN_ATTEMPT']=='1','RERUN_REFUSED')
    report=json.loads((OUT/'studio-probe.json').read_text())
    require(report.get('preflight')=='PASS','PREFLIGHT_REQUIRED')
    data={'run_id':os.environ['GITHUB_RUN_ID'],'sha':os.environ['GITHUB_SHA'],
          'authorization':'one stop/start, same CPU; no settings changes','claimed_at_utc':now()}
    # Create without SHA: an existing marker is a hard conflict, never overwritten.
    github('PUT','/contents/'+CLAIM,{'branch':'studio-results','message':'Claim single approved Studio restart',
        'content':base64.b64encode(json.dumps(data).encode()).decode()})
    live=github('GET','/contents/'+CLAIM+'?ref=studio-results')
    require(json.loads(base64.b64decode(live['content']))==data,'CLAIM_READBACK')
    (OUT/'claim.json').write_text(json.dumps(data))
    print('One-use authorization claimed and read back')

def probe(execute=False):
    import urllib3.connection
    policy=Policy()
    report={'schema':3,'status':'FAIL','kind':'single_approved_restart','sdk_source_sha':SDK_SHA,
        'started_at_utc':now(),'checks':[],'ssh':'NOT_USED','keepalive':'DISABLED',
        'auto_start_test':'NOT_RUN','natural_idle_sleep_test':'NOT_RUN','service_repair':'NOT_RUN',
        'browser':{'status':'NOT_RUN'}}
    original=http.client.HTTPConnection.putrequest
    stage='configuration'
    def record(name,detail):report['checks'].append({'name':name,'status':'PASS','detail':detail})
    def guarded(conn,method,url,*args,**kwargs):
        require(isinstance(conn,(http.client.HTTPSConnection,urllib3.connection.HTTPSConnection)),'HTTPS_TRANSPORT')
        policy.check(method,conn.host,url)
        return original(conn,method,url,*args,**kwargs)
    def save():
        report['network']={'get_requests':policy.gets,'blocked_requests':policy.blocked,
            'stop_requests_sent':policy.writes['stop'],'start_requests_sent':policy.writes['start']}
        report['last_stage']=stage;write_report(report)
    try:
        require(os.environ.get('GITHUB_REPOSITORY')=='supercubegame/ridge-runner','REPOSITORY')
        require(os.environ.get('GITHUB_REF')=='refs/heads/'+BRANCH,'BRANCH')
        require(os.environ.get('GITHUB_RUN_ATTEMPT')=='1','ATTEMPT')
        require(all(os.environ.get(k,'').strip() for k in ('LIGHTNING_USER_ID','LIGHTNING_API_KEY')),'SECRETS_MISSING')
        if execute:
            receipt=json.loads((OUT/'claim.json').read_text())
            require(receipt['run_id']==os.environ['GITHUB_RUN_ID'] and receipt['sha']==os.environ['GITHUB_SHA'],'CLAIM_IDENTITY')
        manifest=json.loads((OUT/'expected-assets.json').read_text());validate_manifest(manifest)
        logging.disable(logging.CRITICAL)
        os.environ['LIGHTNING_DEBUG']='0';os.environ['LIGHTNING_DISABLE_VERSION_CHECK']='1'
        with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):
            http.client.HTTPConnection.putrequest=guarded
            stage='sdk_import'
            from lightning_sdk import Studio
            from lightning_sdk.api.studio_api import StudioApi
            from lightning_sdk.lightning_cloud.openapi.api.cloud_space_service_api import CloudSpaceServiceApi
            from lightning_sdk.lightning_cloud.openapi import CloudSpaceServiceStartCloudSpaceInstanceBody
            from lightning_sdk.machine import Machine
            Studio._setup=lambda self:None
            def forbidden(*a,**k):raise SafetyError('KEEPALIVE_OR_MUTATION_REFUSED')
            StudioApi.start_keeping_alive=forbidden
            stage='target_lookup'
            studio=Studio(name=TARGET,teamspace='vision-model',org='hopkinsrandy537-org',create_ok=False)
            sid=studio._studio.id;team=studio._teamspace.id
            require(studio.name==TARGET and sid==TARGET_ID,'TARGET_MISMATCH')
            client=studio._studio_api._client
            kwargs={'project_id':team,'id':sid,'_request_timeout':(10,30)}
            policy.routes={kind:route_from_sdk(getattr(CloudSpaceServiceApi,'cloud_space_service_'+kind+'_cloud_space_instance_with_http_info'),team,sid) for kind in ('stop','start')}
            def status():return client.cloud_space_service_get_cloud_space_instance_status(**kwargs)
            def configuration():return client.cloud_space_service_get_cloud_space_instance_config(**kwargs)
            def ports():
                items=studio.list_ports()
                matches=[e for e in items if '8060' in [str(p) for p in (e.ports or [])]]
                require(len(matches)==1,'PORT_ENDPOINT_COUNT')
                e=matches[0];up=e.cloudspace
                require(up is not None and isinstance(up.auto_start,bool),'ENDPOINT_METADATA')
                return {'auto_start':up.auto_start,'type':up.type,'port':8060}
            stage='preflight_status_config'
            before=status();active=before.in_use
            require(active is not None and active.phase=='CLOUD_SPACE_INSTANCE_STATE_RUNNING' and before.requested is None,'NOT_STABLE_RUNNING')
            config=configuration();compute=copy.deepcopy(config.compute_config)
            require(studio.machine==Machine.CPU,'NOT_CPU')
            require(active.compute_config is not None and active.compute_config.name==compute.name,'ACTIVE_CONFIG_MISMATCH')
            require(isinstance(compute.spot,bool),'SPOT_UNKNOWN')
            require(isinstance(config.disable_auto_shutdown,bool) and isinstance(config.idle_shutdown_seconds,int),'SLEEP_UNKNOWN')
            before_ports=ports();require(before_ports['auto_start'] is False,'AUTO_START_CHANGED')
            snapshot={'compute':compute.to_dict(),'sleep':(config.disable_auto_shutdown,config.idle_shutdown_seconds),'ports':before_ports}
            report['before']={'machine':'CPU','compute_name':compute.name,'spot':compute.spot,
                'auto_sleep_enabled':not config.disable_auto_shutdown,'idle_timeout_seconds':config.idle_shutdown_seconds,
                'port_8060':before_ports}
            record('target_and_current_cpu','Exact existing Studio; active/configured CPU agree')
            record('write_routes_verified','Routes extracted from pinned official SDK; only one stop and one start allowed')
            stage='preflight_public_assets'
            report['preflight_asset_count']=public_assets(manifest)
            record('preflight_assets','Every asset matches checksum-pinned deployed release')
            require(policy.blocked==0,'UNEXPECTED_REQUEST')
            report['preflight']='PASS';save()
            if not execute:
                report['status']='PREFLIGHT_PASS';return 0
            stage='stop_request';report['stop_requested_at_utc']=now();save()
            policy.armed='stop'
            try:client.cloud_space_service_stop_cloud_space_instance(**kwargs)
            except Exception as error:
                # A timed-out response may still have stopped the machine. Never resend.
                report['stop_response_error_type']=type(error).__name__
            require(policy.writes['stop']==1,'STOP_NOT_SENT')
            stage='wait_stopped';deadline=time.monotonic()+300;consecutive=0
            while time.monotonic()<deadline:
                current=status()
                stopped=(current.in_use is None or current.in_use.phase=='CLOUD_SPACE_INSTANCE_STATE_STOPPED') and current.requested is None
                consecutive=consecutive+1 if stopped else 0
                if consecutive>=2:break
                time.sleep(5)
            require(consecutive>=2,'STOP_NOT_CONFIRMED_NO_REPLAY')
            policy.stopped=True;report['stopped_at_utc']=now()
            record('stopped_observed','Two consecutive API observations, five seconds apart; no preview requests while stopped')
            stage='start_request';report['start_requested_at_utc']=now();save()
            policy.armed='start'
            try:client.cloud_space_service_start_cloud_space_instance(body=CloudSpaceServiceStartCloudSpaceInstanceBody(compute_config=compute),**kwargs)
            except Exception as error:report['start_response_error_type']=type(error).__name__
            require(policy.writes['start']==1,'START_NOT_SENT')
            stage='wait_running';deadline=time.monotonic()+600;ready=False
            while time.monotonic()<deadline:
                current=status();live=current.in_use
                ready=live is not None and live.phase=='CLOUD_SPACE_INSTANCE_STATE_RUNNING' and live.startup_status is not None and live.startup_status.top_up_restore_finished is True
                if ready:break
                time.sleep(5)
            require(ready,'START_READINESS_TIMEOUT_NO_REPLAY')
            report['running_at_utc']=now()
            report['instance_identity_changed']=bool(active.cloud_space_instance_id and live.cloud_space_instance_id and active.cloud_space_instance_id!=live.cloud_space_instance_id)
            require(live.compute_config is not None and live.compute_config.name==compute.name,'RESUMED_MACHINE_MISMATCH')
            record('running_restored','Running and top-up restore finished on same CPU configuration')
            stage='settings_readback'
            after=configuration();after_ports=ports()
            require(after.compute_config.to_dict()==snapshot['compute'],'COMPUTE_CONFIG_CHANGED')
            require((after.disable_auto_shutdown,after.idle_shutdown_seconds)==snapshot['sleep'],'SLEEP_CONFIG_CHANGED')
            require(after_ports==snapshot['ports'],'ENDPOINT_CONFIG_CHANGED')
            record('settings_unchanged','Compute config, sleep flag/timeout and 8060 endpoint settings match preflight')
            stage='wait_public_recovery';deadline=time.monotonic()+300;recovered=False
            while time.monotonic()<deadline:
                try:
                    report['recovered_asset_count']=public_assets(manifest);recovered=True;break
                except (urllib.error.URLError,TimeoutError,SafetyError) as error:
                    report['last_public_error_type']=type(error).__name__;time.sleep(5)
            require(recovered,'PUBLIC_RECOVERY_TIMEOUT')
            report['public_recovered_at_utc']=now()
            record('public_service_recovered','All release assets and WASM MIME match without SSH, deployment or manual service start')
            require(policy.blocked==0 and policy.writes=={'stop':1,'start':1},'NETWORK_SCOPE')
            record('single_cycle_boundary','Exactly one stop and one start; no other write accepted')
            report['lifecycle_status']='PASS';report['status']='AWAITING_BROWSER'
    except Exception as error:
        report['status']='FAIL';report['failure_stage']=stage;report['error_type']=type(error).__name__
        if isinstance(error,SafetyError):report['error_code']=str(error)
        if isinstance(getattr(error,'status',None),int):report['http_status']=error.status
    finally:
        http.client.HTTPConnection.putrequest=original
        report['finished_at_utc']=now();save()
        print('Lifecycle stage:',stage,'status:',report['status'],'stop/start:',policy.writes['stop'],policy.writes['start'])
    return 0 if report.get('lifecycle_status')=='PASS' else 1

def merge_browser():
    report=json.loads((OUT/'studio-probe.json').read_text())
    path=OUT/'browser.json'
    browser=json.loads(path.read_text()) if path.exists() else {'status':'NOT_RUN','checks':[]}
    checks=[{'name':c['name'],'pass':c['pass']} for c in browser.get('checks',[])]
    ok=browser.get('status')=='PASS' and len(checks)==5 and all(c['pass'] is True for c in checks)
    report['browser']={'status':'PASS' if ok else 'FAIL','checks':checks,'renderer':'Chromium SwiftShader; not real-device acceptance'}
    report['status']='PASS' if ok and report.get('lifecycle_status')=='PASS' else 'FAIL'
    write_report(report)
    return 0 if report['status']=='PASS' else 1

if __name__=='__main__':
    mode=sys.argv[1]
    if mode=='--prepare':prepare()
    elif mode=='--claim':claim()
    elif mode=='--preflight':sys.exit(probe(False))
    elif mode=='--execute':sys.exit(probe(True))
    elif mode=='--merge-browser':sys.exit(merge_browser())
    else:raise SystemExit('Unknown mode')
