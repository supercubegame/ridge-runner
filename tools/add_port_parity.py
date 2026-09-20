import ast,datetime,hashlib,inspect,json,os,pathlib,socket,sys,types
r={'status':'FAIL','kind':'official_add_port_v6_parity','checks':[],'socket_attempts':0,'platform_requests':0,'studio_constructed':False,'sdk_api_initialized':False}
def blocked(*a,**k):
 r['socket_attempts']+=1
 raise RuntimeError('NETWORK_FORBIDDEN')
def require(ok,name):
 if not ok:raise RuntimeError(name)
 r['checks'].append(name)
def main():
 os.environ['LIGHTNING_DISABLE_VERSION_CHECK']='1';os.environ['LIGHTNING_DEBUG']='0'
 socket.socket.connect=blocked;socket.socket.connect_ex=blocked;socket.create_connection=blocked;socket.getaddrinfo=blocked
 try:
  require(not any(os.environ.get(k) for k in ('LIGHTNING_USER_ID','LIGHTNING_API_KEY','GH_TOKEN','GITHUB_TOKEN','STUDIO_SSH_PRIVATE_KEY')),'no_platform_or_github_credentials_in_test')
  from lightning_sdk.api.studio_api import StudioApi
  from lightning_sdk.lightning_cloud.openapi import EndpointServiceCreateEndpointBody,V1EndpointAuth,V1EndpointType,V1UpstreamCloudSpace
  from lightning_sdk.lightning_cloud.openapi.api_client import ApiClient
  client=ApiClient()
  source=pathlib.Path('tools/runtime_v6.py').read_bytes()
  git_hash=hashlib.sha1(b'blob '+str(len(source)).encode()+b'\0'+source).hexdigest()
  require(git_hash=='5f94da3abf17b9857aec9e6f1963f33114b9dfde','v6_source_matches_executed_blob')
  tree=ast.parse(source)
  calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='EndpointServiceCreateEndpointBody']
  require(len(calls)==1,'one_actual_v6_create_body_expression')
  expr=ast.Expression(body=calls[0]);ast.fix_missing_locations(expr)
  env={'__builtins__':{},'EndpointServiceCreateEndpointBody':EndpointServiceCreateEndpointBody,'V1EndpointAuth':V1EndpointAuth,'V1EndpointType':V1EndpointType,'V1UpstreamCloudSpace':V1UpstreamCloudSpace,'b':types.SimpleNamespace(NAME='fixture-endpoint',SID='fixture-studio'),'username':'fixture-user','password':'fixture-password'}
  v6=client.sanitize_for_serialization(eval(compile(expr,'frozen_v6_expression','eval'),env))
  captured=[]
  sentinel=object()
  class FakeClient:
   def endpoint_service_create_endpoint(self,**kw):
    captured.append(kw);return sentinel
   def __getattr__(self,key):raise RuntimeError('UNEXPECTED_SDK_CLIENT_METHOD')
  obj=object.__new__(StudioApi);obj._client=FakeClient()
  returned=StudioApi.add_port(obj,teamspace_id='fixture-team',studio_id='fixture-studio',name='fixture-endpoint',port=8061,auto_start=False)
  require(returned is sentinel,'official_method_returns_create_response')
  require(len(captured)==1,'official_method_exactly_one_mock_create_no_extra_registration')
  require(set(captured[0])=={'project_id','body'} and captured[0]['project_id']=='fixture-team','same_project_scoping')
  official=client.sanitize_for_serialization(captured[0]['body'])
  require('auth' not in official,'official_add_port_omits_auth')
  require(v6['auth']=={'enabled':True,'username':'fixture-user','password':'fixture-password'},'v6_adds_only_fresh_basic_auth_values')
  no_auth=dict(v6);no_auth.pop('auth')
  require(no_auth==official,'all_other_serialized_fields_exactly_equal')
  require(official['cloudspace']=={'cloudspaceId':'fixture-studio','port':'8061','autoStart':False,'type':'ENDPOINT_PLUGIN_PORT'},'same_upstream_port_type_autostart_omissions')
  require(official['ports']==['8061'] and official['name']=='fixture-endpoint','same_top_level_port_and_name')
  captured.clear()
  StudioApi.add_port(obj,teamspace_id='fixture-team',studio_id='fixture-studio',name='fixture-endpoint',port=8061)
  require(client.sanitize_for_serialization(captured[0]['body'])==official,'official_default_autostart_is_identical_false')
  require(r['socket_attempts']==0,'zero_network_attempts')
  r['difference_paths']=['auth'];r['official_top_level_keys']=sorted(official);r['v6_top_level_keys']=sorted(v6)
  r['official_method_source_sha256']=hashlib.sha256(inspect.getsource(StudioApi.add_port).encode()).hexdigest()
  r['v6_source_git_blob']=git_hash
  r['limitations']=['Mock captures real SDK method and real serializer, not a platform endpoint creation.','Does not establish Basic authentication causes 502.','Does not establish omitted auth means public access on the platform.','No inference about web UI registration implementation or gateway routing target.']
  r['status']='PASS'
 except Exception as e:
  r['error_type']=type(e).__name__
  if type(e) is RuntimeError:r['error_code']=str(e)
 finally:
  r['observed_at_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
  pathlib.Path('out').mkdir(exist_ok=True);pathlib.Path('out/studio-probe.json').write_text(json.dumps(r,indent=2)+'\n');print(r['status'])
 return 0 if r['status']=='PASS' else 1
if __name__=='__main__':sys.exit(main())
