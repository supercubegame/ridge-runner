"""One approved local HTTP read and listener metadata snapshot; no bind."""
import base64,json,os,pathlib,shlex,sys
import listener_once as b
b.BRANCH='audit/loopback8060-once-20260920'
b.CLAIM='claims/loopback8060-once-20260920-1240.json'
VERSION={'game':'ridge-runner','release':'playtest-35445091317-1','archive_sha256':'ad73d9ba67b3cf31f5c9ab57c84d1eeeb74653f748a73d76b5dc32c9b36192f5'}
REMOTE='''import http.client,json
out={'schema':2,'scope':'command_process_network_namespace','ports':{'8060':{'tcp4':0,'tcp6':0},'8061':{'tcp4':0,'tcp6':0}},'tables':{},'http':{'attempted':True,'version_matches':False}}
for family,path in [('tcp4','/proc/net/tcp'),('tcp6','/proc/net/tcp6')]:
 try:
  with open(path) as stream:lines=stream.read().splitlines()[1:]
  for line in lines:
   fields=line.split()
   if fields[3]!='0A':continue
   port=str(int(fields[1].rsplit(':',1)[1],16))
   if port in out['ports']:out['ports'][port][family]+=1
  out['tables'][family]='READ'
 except FileNotFoundError:out['tables'][family]='UNAVAILABLE'
 except Exception:out['tables'][family]='READ_FAILED'
conn=None
try:
 conn=http.client.HTTPConnection('127.0.0.1',8060,timeout=5)
 conn.request('GET','/version.json',headers={'Cache-Control':'no-cache'})
 response=conn.getresponse();body=response.read(4097)
 out['http']['status']=response.status
 out['http']['version_matches']=response.status==200 and len(body)<=4096 and json.loads(body)==__VERSION__
except Exception as e:out['http']['error_type']=type(e).__name__
finally:
 if conn:conn.close()
print(json.dumps(out,sort_keys=True))
'''.replace('__VERSION__',repr(VERSION))
base_parse=b.parse_output
def parse(text):
 value=json.loads(text)
 b.require(set(value)=={'schema','scope','ports','tables','http'} and value['schema']==2,'OUTPUT_SCHEMA')
 h=value['http']
 b.require(set(h)<= {'attempted','version_matches','status','error_type'} and h.get('attempted') is True and type(h.get('version_matches')) is bool,'HTTP_SCHEMA')
 if 'status' in h:b.require(type(h['status']) is int and 100<=h['status']<=599,'HTTP_STATUS')
 if 'error_type' in h:b.require(h['error_type'] in ('ConnectionRefusedError','TimeoutError','OSError','RemoteDisconnected','IncompleteRead','JSONDecodeError','UnicodeDecodeError','ConnectionResetError','BadStatusLine'),'HTTP_ERROR_CLASS')
 base={k:v for k,v in value.items() if k!='http'};base['schema']=1;base_parse(json.dumps(base))
 return value
b.REMOTE=REMOTE
b.COMMAND='exec env -i PATH=/usr/local/bin:/usr/bin:/bin python3 -c '+shlex.quote(REMOTE)
b.parse_output=parse
def claim():
 b.require(os.environ['GITHUB_REPOSITORY']=='supercubegame/ridge-runner' and os.environ['GITHUB_REF']=='refs/heads/'+b.BRANCH and os.environ['GITHUB_RUN_ATTEMPT']=='1','CLAIM_SCOPE')
 data={'run_id':os.environ['GITHUB_RUN_ID'],'sha':os.environ['GITHUB_SHA'],'approved':'12:40 one runtime read: loopback8060 version match and proc tcp8060/8061 listener counts; no bind/service/endpoint/lifecycle/env/commandline reads','at':b.stamp()}
 b.github('PUT','/contents/'+b.CLAIM,{'branch':'studio-results','message':'Claim one approved loopback read','content':base64.b64encode(json.dumps(data).encode()).decode()})
 live=b.github('GET','/contents/'+b.CLAIM+'?ref=studio-results')
 b.require(json.loads(base64.b64decode(live['content']))==data,'CLAIM_READBACK')
 pathlib.Path('out').mkdir(exist_ok=True);pathlib.Path('out/listener-claim.json').write_text(json.dumps(data))
def test():
 import contextlib,http.client,io
 from unittest.mock import patch
 for status,payload,match in [(200,json.dumps(VERSION).encode(),True),(200,b'{"game":"other"}',False),(302,b'{}',False),(200,b'not-json',False)]:
  calls=[]
  class Response:
   def read(self,n):assert n==4097;return payload
  Response.status=status
  class Fake:
   def __init__(self,host,port,timeout):assert (host,port,timeout)==('127.0.0.1',8060,5)
   def request(self,method,path,headers):calls.append((method,path));assert headers=={'Cache-Control':'no-cache'}
   def getresponse(self):return Response()
   def close(self):pass
  sink=io.StringIO()
  with patch.object(http.client,'HTTPConnection',Fake),contextlib.redirect_stdout(sink):exec(REMOTE,{})
  value=parse(sink.getvalue());assert value['http']['version_matches'] is match and calls==[('GET','/version.json')]
 for method,path in [('POST','/start'),('POST','/stop'),('DELETE','/endpoint'),('PUT','/endpoint')]:
  p=b.Policy();p.route='/execute';p.armed=True
  try:p.check(method,'lightning.ai',path)
  except RuntimeError:pass
  else:raise AssertionError('WRITE')
 p=b.Policy();p.route='/execute';p.armed=True;p.check('POST','lightning.ai','/execute');p.armed=True
 try:p.check('POST','lightning.ai','/execute')
 except RuntimeError:pass
 else:raise AssertionError('REPLAY')
 assert all(x not in REMOTE for x in ('environ','subprocess','.bind(','.listen(','cmdline'))
 print('PASS 4 HTTP outcome fixtures, 4 forbidden writes, replay and remote scope')
if __name__=='__main__':
 if '--self-test' in sys.argv:test()
 elif '--claim' in sys.argv:claim()
 else:
  code=b.execute()
  path=pathlib.Path('out/studio-probe.json');r=json.loads(path.read_text())
  r['kind']='approved_loopback8060_read_once'
  r['verification']='MATCH' if r.get('listeners',{}).get('http',{}).get('version_matches') else 'NOT_CONFIRMED'
  path.write_text(json.dumps(r,indent=2)+'\n')
  sys.exit(code)
