"""Approved 19:29 paired sampling; pinned v8 request/service/cleanup unchanged."""
import hashlib,json,pathlib,sys,time
BASE=pathlib.Path(__file__).with_name('runtime_v8.py')
BASE_BLOB='f0d15b45c296dc71f37dbd19da0bb733c6cf1b69'
APPROVAL='19:29 confirm_v9_sampling_1928; one v8-cluster-only temporary8061 endpoint auth omitted autoStart false; one unchanged120s anonymous service hard165s; alternating paired probe/root sampling90s request timeout10s no early success stop; exact new endpoint deletion; abort not Running missing cluster conflicts config drift unexpected auth; preserve8060 machine sleep SSH; no lifecycle changes or replay'
OLD="""    while time.monotonic()<deadline:
     entry=observe('anonymous')
     if entry.get('http_status')==200 and entry.get('exact_marker'):ready=True;break
     if entry.get('http_status') in (401,403):break
     time.sleep(3)
    r['anonymous_marker_verified']=ready
    if ready:r['checks'].append('anonymous_exact_marker')
    root=observe('root_anonymous','/')
    r['trial_status']='PASS' if ready and root.get('http_status')==404 else 'FAIL'
"""
NEW="""    r['sampling']=sample_pairs(observe,time.monotonic,time.sleep,90)
    r['anonymous_marker_verified']=r['sampling']['probe_success_count']>0
    if r['anonymous_marker_verified']:r['checks'].append('anonymous_exact_marker')
    r['trial_status']='PASS' if r['sampling']['tail_three_pairs_ok'] and r['sampling']['post_first_good_pair_bad_requests']==0 and not r['sampling']['auth_abort'] else 'FAIL'
    save()
"""
def sample_pairs(observe,clock,sleep,window=90):
 start=clock();deadline=start+window;rows=[];pairs=[];auth_abort=False;index=0
 while clock()<deadline and not auth_abort:
  paths=['/probe','/'] if index%2==0 else ['/','/probe']
  current=[]
  for path in paths:
   if clock()>=deadline:break
   row=observe('pair_'+str(index)+'_'+('probe' if path=='/probe' else 'root'),path)
   row.update(pair=index,path=path,expected_ok=(row.get('http_status')==200 and row.get('exact_marker') is True) if path=='/probe' else row.get('http_status')==404)
   current.append(row);rows.append(row)
   if row.get('http_status') in (401,403):auth_abort=True;break
  pairs.append({'pair':index,'complete':len(current)==2,'ok':len(current)==2 and all(r['expected_ok'] for r in current)})
  index+=1
  remaining=deadline-clock()
  if remaining>0 and not auth_abort:sleep(min(3,remaining))
 first=next((p['pair'] for p in pairs if p['ok']),None)
 complete=[p for p in pairs if p['complete']]
 return {'window_seconds':window,'elapsed_seconds':round(clock()-start,3),'pairs':pairs,'request_count':len(rows),'probe_success_count':sum(r['path']=='/probe' and r['expected_ok'] for r in rows),'root_success_count':sum(r['path']=='/' and r['expected_ok'] for r in rows),'first_good_pair':first,'post_first_good_pair_bad_requests':sum(not r['expected_ok'] for r in rows if first is not None and r['pair']>first),'tail_three_pairs_ok':len(complete)>=3 and all(p['ok'] for p in complete[-3:]),'auth_abort':auth_abort,'criterion':'last3 complete pairs good AND no bad request after first good pair AND no auth abort; bounded observation only, not long-term stability'}
def prepared():
 raw=BASE.read_bytes()
 assert hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==BASE_BLOB,'BASE_CHANGED'
 source=raw.decode()
 def change(old,new):
  nonlocal source
  assert source.count(old)==1,('ANCHOR',old[:80])
  source=source.replace(old,new)
 change("b.BRANCH='audit/runtime-8061-v8-20260920'","b.BRANCH='audit/runtime-8061-v9-20260920'")
 change("b.CLAIM='claims/runtime-8061-v8-20260920-1918.json'","b.CLAIM='claims/runtime-8061-v9-20260920-1929.json'")
 line=next(l for l in source.splitlines() if l.startswith('APPROVAL='))
 change(line,'APPROVAL='+repr(APPROVAL))
 assert source.count('runtime-v8-claim.json')==2
 source=source.replace('runtime-v8-claim.json','runtime-v9-claim.json')
 change("'probe':'runtime-v8'","'probe':'runtime-v9'")
 change("'kind':'approved_runtime_v8_cluster_only'","'kind':'approved_runtime_v9_paired_sampling'")
 change("stage='diagnostic_http';deadline=time.monotonic()+70;ready=False","stage='diagnostic_http'")
 change(OLD,NEW)
 change("print('Runtime v8:'","print('Runtime v9:'")
 ns={'__name__':'v9_inherited','__file__':str(BASE),'sample_pairs':sample_pairs}
 exec(compile(source,'<pinned-v8-with-reviewed-v9-sampling>','exec'),ns)
 return ns,source
def test():
 ns,source=prepared()
 ns['test']()
 checks=[]
 def check(name,ok):
  assert ok,name
  checks.append(name)
 def fixture(statuses,window=20,cost=.1):
  t=[0];calls=[]
  def clock():return t[0]
  def sleep(n):t[0]+=n
  def observe(label,path):
   calls.append((label,path,t[0]));t[0]+=cost
   status=statuses[len(calls)-1] if len(calls)<=len(statuses) else (200 if path=='/probe' else 404)
   return {'http_status':status,'exact_marker':status==200}
  return sample_pairs(observe,clock,sleep,window),calls
 good,calls=fixture([])
 check('continues_after_first_success',good['probe_success_count']>=3 and good['root_success_count']>=3)
 check('alternates_pair_order',[p for _,p,_ in calls[:8]]==['/probe','/','/','/probe','/probe','/','/','/probe'])
 check('all_good_tail_pass',good['tail_three_pairs_ok'] and good['post_first_good_pair_bad_requests']==0)
 bad,_=fixture([200,502,404,200,502,404])
 check('intermittence_not_hidden',bad['post_first_good_pair_bad_requests']==1)
 slow,sc=fixture([],window=1,cost=2)
 check('no_new_request_after_deadline',len(sc)==1 and not slow['pairs'][0]['complete'])
 auth,ac=fixture([401])
 check('auth_stops_without_further_requests',len(ac)==1 and auth['auth_abort'])
 transient,_=fixture([404,502,502,502])
 check('initial_propagation_separate',transient['first_good_pair']==2 and transient['post_first_good_pair_bad_requests']==0)
 import ast
 def create_expr(text):
  return [ast.dump(n,include_attributes=False) for n in ast.walk(ast.parse(text)) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='EndpointServiceCreateEndpointBody']
 check('endpoint_constructor_identical',create_expr(source)==create_expr(BASE.read_text()))
 check('cleanup_identical',source[source.index("   finally:\n    stage='cleanup'"):source.index(" except Exception as e:\n  r['error_type']")]==BASE.read_text()[BASE.read_text().index("   finally:\n    stage='cleanup'"):BASE.read_text().index(" except Exception as e:\n  r['error_type']")])
 check('claim_unique',ns['b'].CLAIM=='claims/runtime-8061-v9-20260920-1929.json')
 pathlib.Path('out').mkdir(exist_ok=True)
 pathlib.Path('out/v9-local-tests.json').write_text(json.dumps({'status':'PASS','checks':checks,'base_blob':BASE_BLOB,'platform_requests':0},indent=2))
 print('PASS v9 sampling checks',len(checks))
if __name__=='__main__':
 if '--self-test' in sys.argv:test()
 elif '--claim' in sys.argv:prepared()[0]['claim']()
 else:sys.exit(prepared()[0]['execute']())
