#!/usr/bin/env python3
import base64,json,os,pathlib,urllib.error,urllib.request
ROOT=pathlib.Path(__file__).resolve().parents[1];OUT=ROOT/'out';OUT.mkdir(exist_ok=True)
REPO=os.environ['GITHUB_REPOSITORY'];TOKEN=os.environ['GH_TOKEN'];SHA=os.environ['GITHUB_SHA']
def api(method,path,data=None):
    payload=None if data is None else json.dumps(data).encode()
    req=urllib.request.Request('https://api.github.com/repos/'+REPO+path,data=payload,headers={'Authorization':'Bearer '+TOKEN,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'},method=method)
    with urllib.request.urlopen(req,timeout=60) as r:return json.load(r)
def read_json(name):
    p=OUT/name
    return json.loads(p.read_text()) if p.exists() else None
report={'sha':SHA,'run_id':os.environ['GITHUB_RUN_ID'],'attempt':os.environ['GITHUB_RUN_ATTEMPT'],'run_url':f'https://github.com/{REPO}/actions/runs/'+os.environ['GITHUB_RUN_ID'],'build_outcome':os.environ.get('BUILD_OUTCOME','missing'),'browser_outcome':os.environ.get('BROWSER_OUTCOME','missing'),'release_outcome':os.environ.get('RELEASE_OUTCOME','missing'),'build':read_json('build.json'),'browser':read_json('browser.json'),'release':read_json('release.json'),'logs':{}}
for name in ['build.log','browser-install.log','browser.log','browser-console.log']:
    p=OUT/name
    if p.exists():report['logs'][name]=p.read_text(errors='replace')[-18000:].replace(TOKEN,'[REDACTED]')
report['status']='PASS' if all(report[k]=='success' for k in ['build_outcome','browser_outcome','release_outcome']) else 'FAIL'
(OUT/'report.json').write_text(json.dumps(report,indent=2))
try:api('GET','/git/ref/heads/build-results')
except urllib.error.HTTPError as e:
    if e.code!=404:raise
    api('POST','/git/refs',{'ref':'refs/heads/build-results','sha':SHA})
for name in [f'reports/{SHA}.json','reports/latest.json']:
    old=None
    try:old=api('GET','/contents/'+name+'?ref=build-results')
    except urllib.error.HTTPError as e:
        if e.code!=404:raise
    data={'message':'Record build evidence '+SHA[:12],'branch':'build-results','content':base64.b64encode(json.dumps(report,indent=2).encode()).decode()}
    if old:data['sha']=old['sha']
    api('PUT','/contents/'+name,data)
    live=api('GET','/contents/'+name+'?ref=build-results')
    if json.loads(base64.b64decode(live['content']))!=report:raise RuntimeError('Report readback mismatch')
print('Evidence written and read back for',SHA,report['status'])
