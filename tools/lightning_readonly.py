#!/usr/bin/env python3
"""Pinned SDK, GET-only transport, no Studio keepalive, allowlisted evidence."""
import contextlib,datetime,http.client,importlib.metadata,json,logging,os,pathlib,re,sys,urllib.parse
SDK_SHA='a7709959692a4abdcd152f381585eb1de826923b'
TARGET='peaceful-dewdney-424'
class ReadOnlyViolation(RuntimeError):pass

def check_request(method,host,url):
    p=urllib.parse.urlsplit(url)
    actual=p.hostname if p.scheme else host.split(':')[0]
    if method.upper()!='GET' or actual not in ('lightning.ai','api.lightning.ai'):
        raise ReadOnlyViolation('Request blocked by read-only host/method policy')
    if p.scheme and p.scheme!='https':raise ReadOnlyViolation('HTTPS required')
    if any(x in p.path.lower() for x in ('keepalive','keep-alive','keep_alive')):
        raise ReadOnlyViolation('Keepalive prohibited')

def safe_label(v):
    value=getattr(v,'value',v)
    text=str(value)
    if not re.fullmatch(r'[A-Za-z0-9_.: /-]{1,80}',text):return 'UNRECOGNIZED'
    return text

def selftest():
    check_request('GET','lightning.ai','/v1/projects')
    for method,host,url in [('POST','lightning.ai','/v1/projects'),('PUT','lightning.ai','/v1/projects'),('DELETE','lightning.ai','/v1/projects'),('PATCH','lightning.ai','/v1/projects'),('GET','evil.example','/'),('GET','lightning.ai','/v1/keepalive'),('GET','lightning.ai','https://evil.example'),('GET','lightning.ai','http://lightning.ai')]:
        try:check_request(method,host,url)
        except ReadOnlyViolation:continue
        raise AssertionError('Guard accepted forbidden request')
    assert safe_label('CPU.4')=='CPU.4'
    assert safe_label('sentinel-secret=hidden')=='UNRECOGNIZED'
    print('PASS 11 policy and output checks')

def main():
    out=pathlib.Path('out');out.mkdir(exist_ok=True)
    report={'schema':1,'status':'FAIL','scope':'Lightning account read-only API probe','sdk_source_sha':SDK_SHA,'observed_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'checks':[],'network':{'get_requests':0,'blocked_requests':0,'write_requests_sent':0},'ssh':'NOT_USED','start_stop_delete':'NOT_CALLED','keepalive':'DISABLED','auto_start_lifecycle_test':'NOT_RUN'}
    stage='configuration'
    def record(name,status,detail):report['checks'].append({'name':name,'status':status,'detail':detail})
    original=http.client.HTTPConnection.putrequest
    def guarded(self,method,url,*args,**kwargs):
        try:
            if not isinstance(self,http.client.HTTPSConnection):raise ReadOnlyViolation('HTTPS transport required')
            check_request(method,self.host,url)
        except ReadOnlyViolation:
            report['network']['blocked_requests']+=1
            report['blocked_method']=method if method in ('GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS') else 'OTHER'
            report['blocked_host_category']='lightning' if self.host in ('lightning.ai','api.lightning.ai') else 'non_allowlisted'
            raise
        report['network']['get_requests']+=1
        return original(self,method,url,*args,**kwargs)
    try:
        if not all(os.environ.get(k,'').strip() for k in ('LIGHTNING_USER_ID','LIGHTNING_API_KEY')):
            record('credentials_present','FAIL','One or both GitHub Secrets missing');return 1
        record('credentials_present','PASS','Both API credential Secrets supplied; values withheld')
        logging.disable(logging.CRITICAL)
        os.environ['LIGHTNING_DEBUG']='0'
        os.environ['LIGHTNING_DISABLE_VERSION_CHECK']='1'
        stage='sdk_import'
        # /dev/null supplies fileno needed by SDK noninteractive setup; no raw output retained.
        with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):
            http.client.HTTPConnection.putrequest=guarded
            from lightning_sdk import Studio
            from lightning_sdk.api.studio_api import StudioApi
            Studio._setup=lambda self:None
            def forbidden(*args,**kwargs):raise ReadOnlyViolation('Keepalive/API mutation prohibited')
            StudioApi.start_keeping_alive=forbidden
            for method in ('start','stop','delete','switch_machine','duplicate','run','run_with_exit_code','run_and_detach','add_ports','set_env','delete_env','upload_file','upload_folder'):
                setattr(Studio,method,forbidden)
            report['sdk_version']=importlib.metadata.version('lightning-sdk')
            stage='target_lookup'
            studio=Studio(name=TARGET,teamspace='vision-model',org='hopkinsrandy537-org',create_ok=False)
            if studio.name!=TARGET:raise ValueError('Target mismatch')
            record('authenticated_target_lookup','PASS','Requested existing Studio found; create_ok=False')
            stage='read_status'
            status=studio.status
            report['studio_status']=safe_label(status)
            record('read_status','PASS','Status read through authenticated API')
            stage='read_sleep_config'
            config=studio._studio.code_config
            disabled=getattr(config,'disable_auto_shutdown',None)
            timeout=getattr(config,'idle_shutdown_seconds',None)
            if not isinstance(disabled,bool):raise ValueError('Auto-sleep boolean not present')
            report['auto_sleep_enabled']=not disabled
            if isinstance(timeout,str) and timeout.isdigit():timeout=int(timeout)
            if not isinstance(timeout,int) or isinstance(timeout,bool) or timeout<0:raise ValueError('Timeout not numeric')
            report['idle_timeout_seconds']=timeout
            record('read_sleep_config','PASS','Raw disable_auto_shutdown and idle_shutdown_seconds validated')
            stage='read_machine'
            machine=studio.machine
            report['machine']=None if machine is None else safe_label(machine)
            record('read_machine','PASS','Active machine read without changes')
            stage='read_port_metadata'
            try:
                endpoints=studio.list_ports();matches=[]
                for endpoint in endpoints:
                    ports=getattr(endpoint,'ports',None) or []
                    if '8060' not in [str(x) for x in ports]:continue
                    upstream=getattr(endpoint,'cloudspace',None)
                    auto=getattr(upstream,'auto_start',None)
                    matches.append({'port':8060,'auto_start':auto if isinstance(auto,bool) else None,'endpoint_type':safe_label(getattr(upstream,'type','unknown'))})
                report['port_8060_endpoints']=matches
                record('read_port_metadata','PASS' if matches else 'UNVERIFIED','Only matching port fields retained; no endpoint secrets/URLs exported')
            except Exception as e:
                record('read_port_metadata','UNVERIFIED',type(e).__name__)
            if report['network']['blocked_requests']:raise ReadOnlyViolation('Unexpected request blocked')
            report['status']='PASS'
    except Exception as error:
        report['failure_stage']=stage;report['error_type']=type(error).__name__
        status=getattr(error,'status',None)
        if isinstance(status,int):report['http_status']=status
        report['status']='FAIL'
    finally:
        http.client.HTTPConnection.putrequest=original
        text=json.dumps(report,indent=2)
        for name in ('LIGHTNING_USER_ID','LIGHTNING_API_KEY'):
            value=os.environ.get(name,'')
            if value and value in text:raise RuntimeError('Credential serialization refused')
        (out/'studio-probe.json').write_text(text+'\n')
        print('API probe:',report['status'],'(redacted report only)')
    return 0 if report['status']=='PASS' else 1

if __name__=='__main__':
    if '--self-test' in sys.argv:selftest()
    else:sys.exit(main())
