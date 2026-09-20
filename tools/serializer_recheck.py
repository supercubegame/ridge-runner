import datetime,json,os,pathlib,socket,sys
r={'status':'FAIL','kind':'sdk_serializer_recheck','checks':[],'platform_requests':0,'socket_attempts':0,'studio_constructed':False}
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
  require(not os.environ.get('LIGHTNING_USER_ID') and not os.environ.get('LIGHTNING_API_KEY'),'no_platform_credentials')
  from lightning_sdk.api.deployment_api import BasicAuth,to_endpoint_auth
  from lightning_sdk.lightning_cloud.openapi import EndpointServiceCreateEndpointBody,V1EndpointAuth,V1EndpointType,V1UpstreamCloudSpace
  from lightning_sdk.lightning_cloud.openapi.api_client import ApiClient
  client=ApiClient()
  def make(command_present,user_api_present):
   c={'cloudspace_id':'fixture-studio','port':'8061','type':V1EndpointType.PLUGIN_PORT,'auto_start':False}
   if command_present:c['command']=''
   a={'enabled':True,'username':'fixture-user','password':'fixture-password'}
   if user_api_present:a['user_api_key']=False
   return client.sanitize_for_serialization(EndpointServiceCreateEndpointBody(name='fixture-endpoint',ports=['8061'],auth=V1EndpointAuth(**a),cloudspace=V1UpstreamCloudSpace(**c)))
  base=make(False,False)
  require(base['cloudspace']=={'cloudspaceId':'fixture-studio','port':'8061','type':'ENDPOINT_PLUGIN_PORT','autoStart':False},'omitted_cloudspace_fields_absent')
  require(set(base['auth'])=={'enabled','username','password'},'omitted_user_api_key_absent')
  canonical=client.sanitize_for_serialization(to_endpoint_auth(BasicAuth(username='fixture-user',password='fixture-password')))
  require(canonical==base['auth'],'deployment_basic_helper_matches_omission')
  r['combinations']=[]
  for cp,up in [(False,False),(True,False),(False,True),(True,True)]:
   wire=make(cp,up)
   require(('command' in wire['cloudspace'])==cp and ('userApiKey' in wire['auth'])==up,'presence_'+str(int(cp))+str(int(up)))
   if cp:require(wire['cloudspace']['command']=='','explicit_empty_command_preserved')
   if up:require(wire['auth']['userApiKey'] is False,'explicit_false_preserved')
   stripped=json.loads(json.dumps(wire));stripped['cloudspace'].pop('command',None);stripped['auth'].pop('userApiKey',None)
   require(stripped==base,'only_expected_keys_differ_'+str(int(cp))+str(int(up)))
   r['combinations'].append({'command_in_request':cp,'user_api_key_in_request':up,'cloudspace_keys':sorted(wire['cloudspace']),'auth_keys':sorted(wire['auth'])})
  require(r['socket_attempts']==0,'no_network_attempts')
  r['causation']='NOT_TESTED_ON_PLATFORM';r['status']='PASS'
 except Exception as e:
  r['error_type']=type(e).__name__
  if type(e) is RuntimeError:r['error_code']=str(e)
 finally:
  r['observed_at_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
  pathlib.Path('out').mkdir(exist_ok=True);pathlib.Path('out/studio-probe.json').write_text(json.dumps(r,indent=2)+'\n');print(r['status'])
 return 0 if r['status']=='PASS' else 1
if __name__=='__main__':sys.exit(main())
