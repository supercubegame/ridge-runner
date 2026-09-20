"""Read only 8060 metadata. Raw commands, job IDs, auth and environment never published."""
import contextlib,http.client,json,logging,os,pathlib,shlex,sys
from lightning_readonly import check_request,safe_label,ReadOnlyViolation,SDK_SHA

def command_summary(value):
    if value is None:return {'kind':'ABSENT','truthy':False}
    if not isinstance(value,str):return {'kind':'NON_STRING','truthy':bool(value)}
    result={'truthy':bool(value),'characters':len(value),'kind':'EMPTY' if not value else 'WHITESPACE' if not value.strip() else 'UNRECOGNIZED'}
    exact={'sleep infinity':'SLEEP_INFINITY','sleep inf':'SLEEP_INFINITY','tail -f /dev/null':'TAIL_DEV_NULL',':':'SHELL_NOOP','true':'TRUE','':'EMPTY'}
    if value.strip() in exact:result['kind']=exact[value.strip()];return result
    try:tokens=shlex.split(value)
    except ValueError:result['parse']='INVALID_SHELL_QUOTES';return result
    allowed={'python','python3','bash','sh','node','npm','uvicorn','streamlit','sleep','tail','echo','nohup','exec','cd'}
    result['first_program']=tokens[0] if tokens and tokens[0] in allowed else 'OTHER'
    result['token_count']=len(tokens)
    result['known_path_markers']={x:x in value for x in ('.ridge-runner-preview','server.py','resume.py','on_start.sh','8060','port-viewer','port_viewer')}
    result['shell_operators_present']=any(x in value for x in (';','&&','||','|','>','$(','`','\n'))
    return result

def selftest():
    assert command_summary(None)['kind']=='ABSENT'
    assert command_summary('')['kind']=='EMPTY'
    assert command_summary('sleep infinity')['kind']=='SLEEP_INFINITY'
    assert command_summary('tail -f /dev/null')['kind']=='TAIL_DEV_NULL'
    assert command_summary(':')['kind']=='SHELL_NOOP'
    assert command_summary('python3 server.py')['first_program']=='python3'
    assert command_summary('python3 server.py')['known_path_markers']['server.py']
    assert command_summary('sleep infinity; rm -rf /')['kind']=='UNRECOGNIZED'
    assert command_summary('"')['parse']=='INVALID_SHELL_QUOTES'
    assert 'sentinel-SECRET' not in json.dumps(command_summary('TOKEN=sentinel-SECRET python3 server.py'))
    for method,host,path in [('POST','lightning.ai','/start'),('PUT','lightning.ai','/endpoint'),('DELETE','lightning.ai','/studio'),('GET','evil.example','/'),('GET','lightning.ai','/keepalive')]:
        try:check_request(method,host,path)
        except ReadOnlyViolation:continue
        raise AssertionError('write or unsafe read accepted')
    print('PASS 15 classifier/redaction/transport checks')

def main():
    import urllib3.connection
    report={'schema':5,'kind':'endpoint_readonly','status':'FAIL','sdk_source_sha':SDK_SHA,'network':{'get':0,'blocked':0,'writes':0},'ssh':'NOT_USED','public_preview':'NOT_REQUESTED'}
    original=http.client.HTTPConnection.putrequest
    def guard(conn,method,url,*args,**kwargs):
        try:
            if not isinstance(conn,(http.client.HTTPSConnection,urllib3.connection.HTTPSConnection)):raise ReadOnlyViolation()
            check_request(method,conn.host,url)
        except ReadOnlyViolation:report['network']['blocked']+=1;raise
        report['network']['get']+=1
        return original(conn,method,url,*args,**kwargs)
    try:
        assert os.environ.get('GITHUB_REF')=='refs/heads/audit/endpoint-readonly-20260920'
        assert all(os.environ.get(k) for k in ('LIGHTNING_USER_ID','LIGHTNING_API_KEY'))
        os.environ['LIGHTNING_DEBUG']='0';os.environ['LIGHTNING_DISABLE_VERSION_CHECK']='1';logging.disable(logging.CRITICAL)
        with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):
            http.client.HTTPConnection.putrequest=guard
            from lightning_sdk import Studio
            from lightning_sdk.api.studio_api import StudioApi
            Studio._setup=lambda s:None
            def forbidden(*a,**k):raise ReadOnlyViolation()
            StudioApi.start_keeping_alive=forbidden
            s=Studio(name='peaceful-dewdney-424',teamspace='vision-model',org='hopkinsrandy537-org',create_ok=False)
            assert s._studio.id=='01m2watakghqmc1fnymkg5czax'
            matches=[e for e in s.list_ports() if '8060' in [str(p) for p in (e.ports or [])]]
            assert len(matches)==1
            e=s._studio_api._client.endpoint_service_get_endpoint(project_id=s._teamspace.id,ref=matches[0].id,_request_timeout=(10,30))
            up=e.cloudspace
            assert up.cloudspace_id==s._studio.id and str(up.port)=='8060'
            report['command']=command_summary(up.command)
            report['studio_job_id_present']=bool(up.studio_job_id)
            report['terminal_session_id_present']=bool(up.terminal_session_id)
            report['separate_job_upstream_present']=e.job is not None
            report['auto_start']=up.auto_start
            report['endpoint_type']=safe_label(up.type)
            report['instance_type']=safe_label(up.instance_type) if up.instance_type else 'UNSET'
            report['studio_status']=safe_label(s.status)
            report['guard_trigger']={'command_truthy':bool(up.command),'studio_job_id_truthy':bool(up.studio_job_id)}
            assert report['network']['blocked']==0
            report['status']='PASS'
    except Exception as error:
        report['error_type']=type(error).__name__
        if isinstance(getattr(error,'status',None),int):report['http_status']=error.status
    finally:
        http.client.HTTPConnection.putrequest=original
        import datetime
        report['observed_at_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        text=json.dumps(report,indent=2)
        for k in ('LIGHTNING_USER_ID','LIGHTNING_API_KEY'):
            if os.environ.get(k) and os.environ[k] in text:raise RuntimeError('CREDENTIAL_OUTPUT_REFUSED')
        pathlib.Path('out').mkdir(exist_ok=True);pathlib.Path('out/studio-probe.json').write_text(text+'\n')
        print('Endpoint metadata inspection:',report['status'])
    return 0 if report['status']=='PASS' else 1
if __name__=='__main__':
    if '--self-test' in sys.argv:selftest()
    else:sys.exit(main())
