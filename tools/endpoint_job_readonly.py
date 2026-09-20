"""Read exact linked Job with authenticated GET only. Never execute referenced commands."""
import contextlib,datetime,http.client,json,logging,os,pathlib,re,sys
import endpoint_readonly as m

def id_shape(value):
    if value is None:return 'ABSENT'
    if not isinstance(value,str):return 'NON_STRING'
    if not value:return 'EMPTY'
    v=value.strip()
    if not v:return 'WHITESPACE'
    if v.lower() in ('null','none','undefined'):return 'LITERAL_NULL_MARKER'
    if re.fullmatch(r'0+(?:-0+)*',v):return 'ALL_ZERO_PLACEHOLDER'
    if re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}',v):return 'NONZERO_UUID'
    return 'OTHER_NONEMPTY_REFERENCE'

def test():
    cases=[(None,'ABSENT'),('','EMPTY'),(' ','WHITESPACE'),('null','LITERAL_NULL_MARKER'),('0','ALL_ZERO_PLACEHOLDER'),('00000000-0000-0000-0000-000000000000','ALL_ZERO_PLACEHOLDER'),('11111111-1111-1111-1111-111111111111','NONZERO_UUID'),('sentinel-secret','OTHER_NONEMPTY_REFERENCE')]
    for value,kind in cases:assert id_shape(value)==kind
    assert 'sentinel-secret' not in json.dumps(id_shape('sentinel-secret'))
    print('PASS 9 reference classification/redaction checks')

def main():
    import urllib3.connection
    report={'schema':6,'kind':'linked_job_readonly','status':'FAIL','resolution':'UNVERIFIED','network':{'get':0,'blocked':0,'writes':0},'ssh':'NOT_USED','public_preview':'NOT_REQUESTED'}
    original=http.client.HTTPConnection.putrequest
    def guard(conn,method,url,*args,**kwargs):
        try:
            if not isinstance(conn,(http.client.HTTPSConnection,urllib3.connection.HTTPSConnection)):raise m.ReadOnlyViolation()
            m.check_request(method,conn.host,url)
        except m.ReadOnlyViolation:report['network']['blocked']+=1;raise
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
            report['reference']={'kind':id_shape(ref),'equals_studio_id':ref==s._studio.id,'equals_endpoint_id':ref==e.id,
                'equals_teamspace_id':ref==s._teamspace.id,'is_known_literal':ref in ('default','unknown','none','null','0','-'),
                'prefix_category':'STUDIO_JOB' if isinstance(ref,str) and ref.startswith('sj_') else 'JOB' if isinstance(ref,str) and ref.startswith('j_') else 'OTHER'}
            assert isinstance(ref,str) and ref and re.fullmatch(r'[A-Za-z0-9_-]{1,128}',ref)
            try:
                job=client.jobs_service_get_job(project_id=s._teamspace.id,id=ref,_request_timeout=(10,30))
                assert job.id==ref and job.project_id==s._teamspace.id
                spec=getattr(job,'spec',None)
                info={'id_matches_reference':True,'project_matches':True,'state':job.state if job.state in ('pending','running','stopped','completed','failed') else 'OTHER',
                    'has_spec':spec is not None,'has_endpoint':job.endpoint is not None,
                    'endpoint_matches':job.endpoint is not None and job.endpoint.id==e.id,
                    'has_deployment':bool(job.deployment_id),'has_pipeline':bool(job.pipeline_id)}
                if spec is not None:
                    info['spec_field_presence']={k:getattr(spec,k,None) is not None for k in ('command','entrypoint','cloudspace_id','studio_id','compute_config','image','env')}
                    for key in ('command','entrypoint'):
                        if hasattr(spec,key):info[key+'_summary']=m.command_summary(getattr(spec,key))
                    info['studio_link_matches']=any(getattr(spec,k,None)==s._studio.id for k in ('cloudspace_id','studio_id'))
                report['linked_job']=info;report['resolution']='RESOLVED_OFFICIAL_JOB'
            except Exception as error:
                report['job_lookup']={'error_type':type(error).__name__}
                if isinstance(getattr(error,'status',None),int):report['job_lookup']['http_status']=error.status
                report['resolution']='UNRESOLVED_IN_JOB_API'
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
        print('GET-only inspection:',report['status'],'job resolution:',report['resolution'])
    return 0 if report['status']=='PASS' else 1
if __name__=='__main__':
    if '--self-test' in sys.argv:test()
    else:sys.exit(main())
