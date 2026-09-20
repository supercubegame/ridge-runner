"""Inspect pinned generated GET methods without platform credentials or network."""
import ast,contextlib,inspect,json,logging,os,pathlib,socket,sys,textwrap
r={'status':'FAIL','kind':'studio_internal_read_schema','network_attempts':0,'platform_requests':0,'methods':{},'models':{}}
def deny(*a,**k):
 r['network_attempts']+=1;raise RuntimeError('NETWORK_DISABLED')
try:
 assert not any(os.environ.get(k) for k in ('LIGHTNING_USER_ID','LIGHTNING_API_KEY'))
 os.environ['LIGHTNING_DISABLE_VERSION_CHECK']='1';os.environ['LIGHTNING_DEBUG']='0';logging.disable(logging.CRITICAL)
 socket.socket.connect=deny;socket.socket.connect_ex=deny;socket.create_connection=deny;socket.getaddrinfo=deny
 with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):
  from lightning_sdk.lightning_cloud import openapi as api
  names=['cloud_space_service_get_cloud_space_app','cloud_space_service_list_cloud_space_apps','cloud_space_service_list_cloud_space_sessions','cloud_space_service_get_long_running_command_in_cloud_space']
  model_names=set()
  for name in names:
   fn=getattr(api.CloudSpaceServiceApi,name+'_with_http_info');src=textwrap.dedent(inspect.getsource(fn));tree=ast.parse(src)
   calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='call_api']
   assert len(calls)==1
   c=calls[0];path,verb=[ast.literal_eval(n) for n in c.args[:2]];assert verb=='GET'
   response=next(ast.literal_eval(k.value) for k in c.keywords if k.arg=='response_type')
   params=[]
   for n in ast.walk(tree):
    if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='all_params' for t in n.targets):params=ast.literal_eval(n.value)
   r['methods'][name]={'signature':str(inspect.signature(fn)),'path':path,'verb':verb,'response_type':response,'allowed_params':params,'doc':inspect.getdoc(fn)}
   model_names.add(response)
  for depth in range(3):
   next_names=set()
   for name in sorted(model_names):
    if name in r['models']:continue
    obj=getattr(api,name,None)
    if obj is None or not hasattr(obj,'swagger_types'):continue
    fields=obj.swagger_types;r['models'][name]=fields
    for typ in fields.values():
     typ=typ.replace('list[','').replace(']','')
     if typ.startswith(('V1','Externalv1')):next_names.add(typ)
   model_names=next_names
  assert r['network_attempts']==0;r['status']='PASS'
except Exception as e:r['error_type']=type(e).__name__
finally:
 pathlib.Path('out').mkdir(exist_ok=True);pathlib.Path('out/studio-probe.json').write_text(json.dumps(r,indent=2)+'\n');print(r['status'])
sys.exit(0 if r['status']=='PASS' else 1)
