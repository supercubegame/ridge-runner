"""Compare endpoint reference with existing sessions. Never execute or fetch output."""
import contextlib,datetime,http.client,json,logging,os,pathlib,re,sys
import endpoint_readonly as m

def compare(sessions,ref,terminal):
    hits=[]
    for s in sessions:
        matches=[k for k in ('id','name') if getattr(s,k,None)==ref]
        if matches:hits.append({'matched_fields':matches,'command':m.command_summary(getattr(s,'command',None))})
    return {'session_count':len(sessions),'studio_job_matches':hits,
        'terminal_reference_present':bool(terminal),
        'terminal_match_count':sum(bool(terminal) and any(getattr(s,k,None)==terminal for k in ('id','name')) for s in sessions)}

def test():
    from types import SimpleNamespace as N
    m.selftest()
    entries=[N(id='job-ref',name='sentinel-name',command='echo sentinel-secret'),N(id='session-two',name='job-ref',command='')]
    r=compare(entries,'job-ref','session-two')
    assert len(r['studio_job_matches'])==2
    assert r['studio_job_matches'][0]['matched_fields']==['id']
    assert r['studio_job_matches'][1]['matched_fields']==['name']
    assert r['terminal_match_count']==1
    assert not compare(entries,'missing',None)['studio_job_matches']
    assert compare([], 'job-ref',None)['session_count']==0
    assert not compare(entries,'missing','')['terminal_reference_present']
    assert all(x not in json.dumps(r) for x in ('sentinel-secret','sentinel-name','job-ref','session-two'))
    print('PASS 8 session comparison/redaction checks plus inherited guard tests')

def main():
    import urllib3.connection
    report={'schema':8,'kind':'endpoint_session_reference_readonly','status':'FAIL','resolution':'UNVERIFIED',
        'network':{'get':0,'blocked':0,'writes':0},'ssh':'NOT_USED','public_preview':'NOT_REQUESTED',
        'command_output':'NOT_REQUESTED','sdk_source_sha':m.SDK_SHA}
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
            assert s._studio.id=='01m2watakghqmc1fnymkg5czax'
            client=s._studio_api._client
            matches=[e for e in s.list_ports() if '8060' in [str(p) for p in (e.ports or [])]]
            assert len(matches)==1
            e=client.endpoint_service_get_endpoint(project_id=s._teamspace.id,ref=matches[0].id,_request_timeout=(10,30))
            up=e.cloudspace;ref=up.studio_job_id
            assert up.cloudspace_id==s._studio.id and str(up.port)=='8060'
            report.update(command=m.command_summary(up.command),auto_start=up.auto_start,studio_status=m.safe_label(s.status))
            assert isinstance(ref,str) and ref and re.fullmatch(r'[A-Za-z0-9_-]{1,128}',ref)
            report['reference_present']=True
            if report['studio_status']!='Running':
                report['resolution']='SESSION_QUERY_SKIPPED_NOT_RUNNING'
            else:
                try:
                    response=client.cloud_space_service_list_cloud_space_sessions(project_id=s._teamspace.id,cloudspace_id=s._studio.id,_request_timeout=(10,30))
                    sessions=response.sessions
                    assert isinstance(sessions,list)
                    summary=compare(sessions,ref,up.terminal_session_id)
                    report['sessions']=summary
                    report['resolution']='SESSION_REFERENCE_MATCH_FOUND' if summary['studio_job_matches'] else 'NO_MATCH_IN_RETURNED_SESSIONS'
                except Exception as error:
                    report['session_lookup']={'error_type':type(error).__name__}
                    if isinstance(getattr(error,'status',None),int):report['session_lookup']['http_status']=error.status
                    report['resolution']='SESSION_LOOKUP_UNRESOLVED'
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
        print('GET-only inspection:',report['status'],'resolution:',report['resolution'])
    return 0 if report['status']=='PASS' else 1
if __name__=='__main__':
    if '--self-test' in sys.argv:test()
    else:sys.exit(main())
