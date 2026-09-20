"""Enrich the same GET-only probe with typed job-link metadata; no additional requests."""
import json,os,pathlib,re,sys
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

def summarize(e):
    up=e.cloudspace;job=e.job
    return {'studio_job_reference_kind':id_shape(up.studio_job_id),
        'job_upstream_reference_kind':id_shape(getattr(job,'job_id',None)),
        'job_references_equal':bool(up.studio_job_id) and up.studio_job_id==getattr(job,'job_id',None),
        'job_upstream_port_kind':'MATCHES_8060' if str(getattr(job,'port',None))=='8060' else id_shape(getattr(job,'port',None)),
        'job_auto_start':getattr(job,'auto_start',None),
        'job_idle_shutdown':getattr(job,'idle_shutdown',None),
        'job_idle_timeout_kind':id_shape(getattr(job,'idle_shutdown_seconds',None))}

def test():
    cases=[(None,'ABSENT'),('','EMPTY'),(' ','WHITESPACE'),('null','LITERAL_NULL_MARKER'),('0','ALL_ZERO_PLACEHOLDER'),('00000000-0000-0000-0000-000000000000','ALL_ZERO_PLACEHOLDER'),('11111111-1111-1111-1111-111111111111','NONZERO_UUID'),('sentinel-secret','OTHER_NONEMPTY_REFERENCE')]
    for value,kind in cases:assert id_shape(value)==kind
    assert 'sentinel-secret' not in json.dumps(id_shape('sentinel-secret'))
    print('PASS 9 reference classification/redaction checks')

def main():
    captured={}
    def profile(frame,event,arg):
        if event=='return' and frame.f_code is m.main.__code__ and frame.f_locals.get('report',{}).get('status')=='PASS':
            captured.update(summarize(frame.f_locals['e']))
    previous=sys.getprofile();sys.setprofile(profile)
    try:code=m.main()
    finally:sys.setprofile(previous)
    path=pathlib.Path('out/studio-probe.json');report=json.loads(path.read_text())
    if code==0:
        if not captured:report['status']='FAIL';report['error_type']='MissingJobMetadata';code=1
        report['job_metadata']=captured
    text=json.dumps(report,indent=2)
    for key in ('LIGHTNING_USER_ID','LIGHTNING_API_KEY'):
        if os.environ.get(key) and os.environ[key] in text:raise RuntimeError('Credential serialization refused')
    path.write_text(text+'\n')
    return code
if __name__=='__main__':
    if '--self-test' in sys.argv:test()
    else:sys.exit(main())
