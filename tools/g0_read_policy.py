"""Local-only candidate for G0 reads. No network client, no credentials."""
import math
from urllib.parse import urlsplit,parse_qsl,quote

class Policy:
 def __init__(self,project,org,provider,host='lightning.ai',max_reads=12):
  if not all(isinstance(x,str) and x for x in (project,org,provider)):raise ValueError('SCOPE_REQUIRED')
  self.project,self.org,self.provider,self.host=project,org,provider,host
  self.remaining=max_reads
 def check(self,method,url):
  u=urlsplit(url)
  if method!='GET' or u.scheme!='https' or u.netloc!=self.host or u.fragment or u.username:raise ValueError('TRANSPORT')
  pairs=parse_qsl(u.query,keep_blank_values=True)
  if len({k for k,v in pairs})!=len(pairs):raise ValueError('DUPLICATE_QUERY')
  q=dict(pairs)
  base='/v1/cloudspaces/environment-templates'
  if u.path=='/v1/projects/'+quote(self.project,safe='')+'/clusters':
   ok=not q
  elif u.path=='/v1/core/clusters':
   ok=q=={'projectId':self.project,'orgId':self.org}
  elif u.path=='/v1/core/accelerators':
   ok=q=={'projectId':self.project,'cloudProvider':self.provider}
  elif u.path in (base,base+'/managed'):
   ok=(q.get('orgId')==self.org and set(q)<= {'orgId','limit','pageToken'}
       and q.get('limit')=='20' and (not 'pageToken' in q or 0<len(q['pageToken'])<=2048))
  else:ok=False
  if not ok:raise ValueError('ROUTE_OR_SCOPE')
  if self.remaining<=0:raise ValueError('READ_BUDGET')
  self.remaining-=1

def numeric_cost(raw):
 """Preserve missing/invalid/zero distinctions; never infer free eligibility."""
 if raw is None:return {'state':'MISSING','value':None,'free_eligibility':'UNKNOWN'}
 if type(raw) not in (int,float) or not math.isfinite(raw) or raw<0:
  return {'state':'INVALID','value':None,'free_eligibility':'UNKNOWN'}
 return {'state':'EXPLICIT_ZERO' if raw==0 else 'PRESENT','value':raw,'free_eligibility':'UNKNOWN'}

def selftest():
 good=[
 'https://lightning.ai/v1/projects/fixture-project/clusters',
 'https://lightning.ai/v1/core/clusters?projectId=fixture-project&orgId=fixture-org',
 'https://lightning.ai/v1/core/accelerators?projectId=fixture-project&cloudProvider=fixture-provider',
 'https://lightning.ai/v1/cloudspaces/environment-templates?orgId=fixture-org&limit=20',
 'https://lightning.ai/v1/cloudspaces/environment-templates/managed?orgId=fixture-org&limit=20&pageToken=fixture',
 ]
 make=lambda:Policy('fixture-project','fixture-org','fixture-provider')
 tests=[]
 for i,url in enumerate(good):make().check('GET',url);tests.append('allowed_'+str(i))
 bad=[('POST',good[0]),('DELETE',good[0]),('PUT',good[0]),('GET',good[0].replace('https:','http:')),
 ('GET',good[0].replace('lightning.ai','evil.example')),('GET',good[0].replace('fixture-project','other')),
 ('GET',good[1].replace('fixture-org','other')),('GET',good[2].replace('fixture-provider','other')),
 ('GET',good[2]+'&cloudProvider=other'),('GET',good[3].replace('limit=20','limit=500')),
 ('GET','https://lightning.ai/v1/keepalive'),('GET','https://lightning.ai/v1/projects/fixture-project/secrets'),
 ('GET','https://lightning.ai/v1/projects/fixture-project/cloudspaces/studio/start'),
 ('GET',good[0]+'#fragment'),('GET',good[0]+'?unlisted=true'),('GET',good[4].replace('pageToken=fixture','pageToken='))]
 for i,(method,url) in enumerate(bad):
  try:make().check(method,url)
  except ValueError:tests.append('blocked_'+str(i))
  else:raise AssertionError(url)
 p=make()
 for _ in range(12):p.check('GET',good[0])
 try:p.check('GET',good[0])
 except ValueError:tests.append('budget_enforced')
 else:raise AssertionError('budget')
 for raw,state in [(None,'MISSING'),(False,'INVALID'),('0','INVALID'),(-1,'INVALID'),(float('nan'),'INVALID'),(float('inf'),'INVALID'),(0,'EXPLICIT_ZERO'),(.12,'PRESENT')]:
  x=numeric_cost(raw);assert x['state']==state and x['free_eligibility']=='UNKNOWN';tests.append('cost_'+str(len(tests)))
 return tests

if __name__=='__main__':
 import json
 checks=selftest()
 print(json.dumps({'status':'PASS','tests':checks,'test_count':len(checks),'platform_requests':0,'scope':'Local candidate; reviewed frontend GET routes, not SDK transport integration or account qualification'},indent=2))
