#!/usr/bin/env python3
"""Publish only allowlisted probe fields, never environment or raw process output."""
import base64,json,os,pathlib,urllib.error,urllib.request
repo=os.environ['GITHUB_REPOSITORY'];sha=os.environ['GITHUB_SHA'];token=os.environ['GH_TOKEN']
def api(method,path,data=None):
    r=urllib.request.Request('https://api.github.com/repos/'+repo+path,data=None if data is None else json.dumps(data).encode(),headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json'},method=method)
    with urllib.request.urlopen(r,timeout=45) as stream:return json.load(stream)
p=pathlib.Path('out/studio-probe.json')
report=json.loads(p.read_text()) if p.exists() else {'status':'FAIL','checks':[{'name':'probe','status':'FAIL','detail':'No report produced'}]}
report['sha']=sha;report['run_id']=os.environ['GITHUB_RUN_ID'];report['attempt']=os.environ['GITHUB_RUN_ATTEMPT']
report['run_url']='https://github.com/'+repo+'/actions/runs/'+report['run_id']
try:api('GET','/git/ref/heads/studio-results')
except urllib.error.HTTPError as e:
    if e.code!=404:raise
    api('POST','/git/refs',{'ref':'refs/heads/studio-results','sha':sha})
name='reports/studio-'+sha+'.json';old=None
try:old=api('GET','/contents/'+name+'?ref=studio-results')
except urllib.error.HTTPError as e:
    if e.code!=404:raise
data={'message':'Record redacted Studio probe '+sha[:12],'branch':'studio-results','content':base64.b64encode(json.dumps(report,indent=2).encode()).decode()}
if old:data['sha']=old['sha']
api('PUT','/contents/'+name,data)
live=api('GET','/contents/'+name+'?ref=studio-results')
if json.loads(base64.b64decode(live['content']))!=report:raise RuntimeError('Evidence readback mismatch')
print('PASS redacted Studio evidence written and read back')
