"""Read exact endpoint reference via legacy app GET. No command execution."""
import contextlib,datetime,http.client,json,logging,os,pathlib,re,sys
import endpoint_readonly as m

def classify(app,ref,team,studio):
    spec=getattr(app,'spec',None)
    return {'id_matches_reference':getattr(app,'id',None)==ref,
        'project_matches':getattr(app,'project_id',None)==team,
        'has_spec':spec is not None,
        'studio_link_matches':any(getattr(o,k,None)==studio for o in (app,spec) if o is not None for k in ('cloudspace_id','studio_id')),
        'command_fields':{k:m.command_summary(getattr(spec,k,None)) for k in ('command','entrypoint')},
        'has_status':getattr(app,'status',None) is not None}

def test():
    from types import SimpleNamespace as N
    m.selftest()
    app=N(id='ref',project_id='team',spec=N(cloudspace_id='studio',command='echo sentinel-secret',entrypoint=None),status=N())
    r=classify(app,'ref','team','studio')
    assert r['id_matches_reference'] and r['project_matches'] and r['studio_link_matches']
    assert 'sentinel-secret' not in json.dumps(r)
    assert not classify(app,'other','other','other')['id_matches_reference']
    assert not classify(app,'other','other','other')['project_matches']
    assert not classify(app,'other','other','other')['studio_link_matches']
    assert not classify(N(),'ref','team','studio')['has_spec']
    print('PASS 6 legacy response identity/redaction checks plus inherited guard tests')

def main():
    import urllib3.connection
    report={'schema':7,'kind':'legacy_endpoint_reference_readonly','status':'FAIL','resolution':'UNVERIFIED',
        'network':{'get':0,'blocked':0,'writes':0},'ssh':'NOT_USED','public_preview':'NOT_REQUESTED',
        'sdk_source_sha':m.SDK_SHA}
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
            try:
                app=client.lightningapp_instance_service_get_lightningapp_instance(project_id=s._teamspace.id,id=ref,_request_timeout=(10,30))
                info=classify(app,ref,s._teamspace.id,s._studio.id)
                report['linked_application']=info
                report['resolution']='RESOLVED_LEGACY_APPLICATION' if info['id_matches_reference'] and info['project_matches'] else 'LEGACY_RESPONSE_IDENTITY_UNCONFIRMED'
            except Exception as error:
                report['legacy_lookup']={'error_type':type(error).__name__}
                if isinstance(getattr(error,'status',None),int):report['legacy_lookup']['http_status']=error.status
                report['resolution']='UNRESOLVED_IN_LEGACY_API'
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
