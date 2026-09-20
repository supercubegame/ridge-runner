"""Offline-process SDK introspection; dependency installation happens separately."""
import ast, contextlib, inspect, json, logging, os, pathlib, socket, sys, textwrap
r={'status':'FAIL','kind':'sdk_reference_introspection','checks':[],'network_attempts':0,'studio_constructed':False,'platform_mutations':0,'sdk_sha':'a7709959692a4abdcd152f381585eb1de826923b'}
def deny(*a,**k):
    r['network_attempts']+=1
    raise RuntimeError('NETWORK_DISABLED')
def check(name,ok):
    r['checks'].append({'name':name,'pass':bool(ok)})
    if not ok:raise AssertionError(name)
def source(fn):return textwrap.dedent(inspect.getsource(fn))
try:
    check('no_platform_credentials',not any(os.environ.get(k) for k in ('LIGHTNING_USER_ID','LIGHTNING_API_KEY')))
    os.environ['LIGHTNING_DISABLE_VERSION_CHECK']='1';os.environ['LIGHTNING_DEBUG']='0';logging.disable(logging.CRITICAL)
    socket.socket.connect=deny;socket.socket.connect_ex=deny;socket.create_connection=deny;socket.getaddrinfo=deny
    with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):
        from lightning_sdk import Studio
        from lightning_sdk.status import Status
        from lightning_sdk.lightning_cloud.openapi import CloudSpaceServiceApi, V1UpstreamCloudSpace
        from lightning_sdk.api.studio_api import StudioApi
        check('field_defined',V1UpstreamCloudSpace.swagger_types.get('studio_job_id')=='str')
        check('wire_field_defined',V1UpstreamCloudSpace.attribute_map.get('studio_job_id')=='studioJobId')
        check('run_plugin_absent',not hasattr(Studio,'run_plugin'))
        r['status_comparison']={'Running_enum_equals_string':Status.Running=='Running','enum_value':Status.Running.value}
        r['status_property_source']=source(Studio.status.fget)
        r['setup_source']=source(Studio._setup)
        r['constructor_calls_setup']=any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='_setup' for n in ast.walk(ast.parse(source(Studio.__init__))))
        r['cloudspace_read_methods']=[m for m in dir(CloudSpaceServiceApi) if m.startswith(('cloud_space_service_get_','cloud_space_service_list_')) and not m.endswith('_with_http_info')]
        check('introspection_import_works',bool(r['cloudspace_read_methods']))
        r['cloudspace_job_read_methods']=[m for m in r['cloudspace_read_methods'] if 'job' in m]
        tree=ast.parse(source(StudioApi.add_port))
        ups=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='V1UpstreamCloudSpace']
        check('single_upstream_constructor',len(ups)==1)
        r['add_port_upstream_fields']=[k.arg for k in ups[0].keywords]
        check('add_port_auto_start_no_command', 'auto_start' in r['add_port_upstream_fields'] and 'command' not in r['add_port_upstream_fields'])
        check('no_network_attempts',r['network_attempts']==0)
        r['status']='PASS'
except Exception as e:r['error_type']=type(e).__name__
finally:
    pathlib.Path('out').mkdir(exist_ok=True)
    pathlib.Path('out/studio-probe.json').write_text(json.dumps(r,indent=2)+'\n')
    print(r['status'],len(r['checks']),'checks; blocked network attempts:',r['network_attempts'])
sys.exit(0 if r['status']=='PASS' else 1)
