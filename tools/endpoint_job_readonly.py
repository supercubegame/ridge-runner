"""Read-only candidate port preflight. No commands, preview traffic, or lifecycle writes."""
import contextlib,datetime,http.client,json,logging,os,pathlib,sys
import endpoint_readonly as m

def classify_ports(values):
    assert isinstance(values,list)
    assert all(str(v).isdigit() and 1<=int(v)<=65535 for v in values)
    ports={int(v) for v in values}
    return {'8060_reported_open':8060 in ports,'8061_reported_open':8061 in ports}

def test():
    m.selftest()
    assert classify_ports(['8060'])=={'8060_reported_open':True,'8061_reported_open':False}
    assert classify_ports(['8061'])['8061_reported_open']
    assert not classify_ports([])['8061_reported_open']
    for value in (None,['bad'],['0'],['65536']):
        try:classify_ports(value)
        except AssertionError:continue
        raise AssertionError('Malformed metadata accepted')
    print('PASS 7 port metadata checks plus inherited safeguards')

def main():
    import urllib3.connection
    report={'schema':9,'kind':'candidate_8061_readonly_preflight','status':'FAIL','network':{'get':0,'blocked':0,'writes':0},
        'ssh':'NOT_USED','public_preview':'NOT_REQUESTED','command_execution':'NOT_RUN','sdk_source_sha':m.SDK_SHA,
        'port_bind_test':'NOT_RUN','creation_authorized':False}
    original=http.client.HTTPConnection.putrequest
    def guard(conn,method,url,*args,**kwargs):
        try:
            if not isinstance(conn,(http.client.HTTPSConnection,urllib3.connection.HTTPSConnection)):raise m.ReadOnlyViolation()
            m.check_request(method,conn.host,url)
        except m.ReadOnlyViolation:report['network']['blocked']+=1;raise
        report['network']['get']+=1
        return original(conn,method,url,*args,**kwargs)
    try:
        assert os.environ.get('GITHUB_REPOSITORY')=='supercubegame/ridge-runner'
        assert os.environ.get('GITHUB_REF')=='refs/heads/audit/endpoint-readonly-20260920'
        assert all(os.environ.get(k) for k in ('LIGHTNING_USER_ID','LIGHTNING_API_KEY'))
        os.environ['LIGHTNING_DEBUG']='0';os.environ['LIGHTNING_DISABLE_VERSION_CHECK']='1';logging.disable(logging.CRITICAL)
        with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):
            http.client.HTTPConnection.putrequest=guard
            from lightning_sdk import Studio
            from lightning_sdk.api.studio_api import StudioApi
            Studio._setup=lambda s:None
            def forbidden(*a,**k):raise m.ReadOnlyViolation()
            StudioApi.start_keeping_alive=forbidden
            s=Studio(name='peaceful-dewdney-424',teamspace='vision-model',org='hopkinsrandy537-org',create_ok=False)
            sid=s._studio.id;team=s._teamspace.id
            assert sid=='01m2watakghqmc1fnymkg5czax'
            client=s._studio_api._client;kw={'project_id':team,'id':sid,'_request_timeout':(10,30)}
            state=client.cloud_space_service_get_cloud_space_instance_status(**kw)
            cfg=client.cloud_space_service_get_cloud_space_instance_config(**kw)
            endpoints=s.list_ports()
            report['endpoint_counts']={str(p):sum(str(p) in [str(v) for v in (e.ports or [])] for e in endpoints) for p in (8060,8061)}
            report['candidate_name_matches']=sum(e.name=='ridge-autowake-probe-8061' for e in endpoints)
            originals=[e for e in endpoints if '8060' in [str(v) for v in (e.ports or [])]]
            assert len(originals)==1
            e=client.endpoint_service_get_endpoint(project_id=team,ref=originals[0].id,_request_timeout=(10,30))
            assert e.cloudspace.cloudspace_id==sid
            report['original_8060']={'auto_start':e.cloudspace.auto_start,'command':m.command_summary(e.cloudspace.command),'studio_job_reference_present':bool(e.cloudspace.studio_job_id)}
            report['configuration']={'original_cpu4':cfg.compute_config.name=='cpu-4','nonspot':cfg.compute_config.spot is False,
                'auto_sleep_enabled':cfg.disable_auto_shutdown is False,'idle_timeout_seconds':cfg.idle_shutdown_seconds}
            live=state.in_use
            running=live is not None and live.phase=='CLOUD_SPACE_INSTANCE_STATE_RUNNING' and state.requested is None
            report['stable_running']=running
            if running:
                response=client.cloud_space_service_get_cloud_space_instance_open_ports(project_id=team,cloudspace_id=sid,cloudspace_instance_id=live.cloud_space_instance_id,_request_timeout=(10,30))
                report['open_ports']=classify_ports(response.ports)
                report['candidate_metadata_clear']=not report['open_ports']['8061_reported_open'] and report['endpoint_counts']['8061']==0 and report['candidate_name_matches']==0
            else:report['open_ports_status']='NOT_QUERIED_NOT_STABLE_RUNNING'
            assert report['network']['blocked']==0
            report['status']='PASS'
    except Exception as error:
        report['error_type']=type(error).__name__
        if isinstance(getattr(error,'status',None),int):report['http_status']=error.status
    finally:
        http.client.HTTPConnection.putrequest=original
        report['observed_at_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        text=json.dumps(report,indent=2)
        for key in ('LIGHTNING_USER_ID','LIGHTNING_API_KEY'):
            if os.environ.get(key) and os.environ[key] in text:raise RuntimeError('Credential serialization refused')
        pathlib.Path('out').mkdir(exist_ok=True);pathlib.Path('out/studio-probe.json').write_text(text+'\n')
        print('Read-only preflight:',report['status'])
    return 0 if report['status']=='PASS' else 1
if __name__=='__main__':
    if '--self-test' in sys.argv:test()
    else:sys.exit(main())
