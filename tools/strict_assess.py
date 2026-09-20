"""Offline report re-evaluation only. Never imports platform SDK or mutates reports."""
import json,pathlib,sys,copy,hashlib,argparse
V9_SHA256='77f234bb38200cadfd377fe3c599ff8ddf304d19f440d2dbe7e190ee0763b209'
REQUIRED=('delete_returned','endpoint_list_absent','service_finished','8061_no_listeners_after','original_endpoint_unchanged','machine_sleep_unchanged','original_game_version_ok')
def strict_ok(row):
 if not isinstance(row,dict):return False
 if type(row.get('http_status')) is not int:return False
 if row.get('path')=='/probe':
  return row.get('http_status')==200 and row.get('exact_marker') is True
 if row.get('path')=='/':
  return row.get('http_status')==404 and type(row.get('body_bytes_sampled')) is int and row['body_bytes_sampled']==0
 return False
def assess(report):
 try:return evaluate(report)
 except (KeyError,TypeError,ValueError,AttributeError):return {'status':'FAIL_OR_INSUFFICIENT','reason':'MALFORMED_OR_MISSING_EVIDENCE'}
def evaluate(report):
 if not isinstance(report,dict):raise ValueError()
 rows=report.get('public_attempts',[])
 if not isinstance(rows,list) or not rows:raise ValueError()
 for row in rows:
  if not isinstance(row,dict) or type(row.get('pair')) is not int or row['pair']<0 or row.get('path') not in ('/','/probe'):raise ValueError()
  if 'http_status' in row and type(row['http_status']) is not int:raise ValueError()
 indices=[r['pair'] for r in rows]
 if max(indices)>=len(rows) or indices!=sorted(indices) or sorted(set(indices))!=list(range(max(indices)+1)):raise ValueError()
 probes=sum(r.get('path')=='/probe' and strict_ok(r) for r in rows)
 roots=sum(r.get('path')=='/' and strict_ok(r) for r in rows)
 groups={}
 for row in rows:
  if type(row.get('pair')) is int:groups.setdefault(row['pair'],[]).append(row)
 results=[]
 for index,group in sorted(groups.items()):
  complete=len(group)==2 and {r.get('path') for r in group}=={'/probe','/'}
  if not complete:raise ValueError()
  results.append((index,complete and all(strict_ok(r) for r in group)))
 first=next((i for i,ok in results if ok),None)
 suffix=[ok for i,ok in results if first is not None and i>=first]
 c=report.get('service',{}).get('counters',{})
 h=report.get('service',{}).get('http_classification',{})
 service=report.get('service',{})
 for v in [h.get('probe_get'),h.get('root_get'),c.get('accepted_tcp'),c.get('parse_error_count'),c.get('read_timeout_count'),*c.get('method_counts',{}).values(),*c.get('status_counts',{}).values()]:
  if type(v) is not int or v<0:raise ValueError()
 if type(service.get('exit_code')) is not int:raise ValueError()
 if not all(type(service.get('after',{}).get(k)) is int for k in ('tcp4','tcp6')):raise ValueError()
 count_match=(h.get('local_selfcheck') is True and h.get('probe_get')==probes and h.get('root_get')==roots
  and c.get('accepted_tcp')==1+probes+roots and c.get('method_counts',{}).get('GET')==1+probes+roots
  and all(c.get('method_counts',{}).get(k)==0 for k in ('HEAD','POST','OPTIONS','OTHER'))
  and c.get('status_counts',{}).get('200')==1+probes and c.get('status_counts',{}).get('404')==roots
  and all(c.get('status_counts',{}).get(k)==0 for k in ('400','405','408','501','other'))
  and c.get('parse_error_count')==0 and c.get('read_timeout_count')==0)
 cleanup=all(report.get('cleanup',{}).get(k) is True for k in REQUIRED)
 service_ok=service.get('exit_code')==0 and service.get('status')=='EXPIRED_CLOSED' and service.get('local_selfcheck_http') is True and service.get('after')=={'tcp4':0,'tcp6':0}
 pass_=len(suffix)>=3 and all(suffix) and count_match and cleanup and service_ok
 return {'status':'PASS' if pass_ else 'FAIL_OR_INSUFFICIENT','strict_first_good_pair':first,'strict_good_suffix_pairs':len(suffix) if all(suffix) else 0,'exact_probe_responses':probes,'empty_root_404_responses':roots,'rejected_nonempty_root_404':sum(r.get('path')=='/' and r.get('http_status')==404 and r.get('body_bytes_sampled')!=0 for r in rows),'service_counts_match':count_match,'cleanup_all_true':cleanup,'service_exit_ok':service_ok,'scope':'Offline stricter re-evaluation of existing report only; no cloud rerun or long-term guarantee'}
def tests(r):
 tests=[]
 def check(name,ok):
  assert ok,name
  tests.append(name)
 check('v9_strict_pass',assess(r)['status']=='PASS')
 a=assess(r);check('strict_start_pair7',a['strict_first_good_pair']==7)
 check('20_good_pairs',a['strict_good_suffix_pairs']==20)
 check('7_gateway_like_404_rejected',a['rejected_nonempty_root_404']==7)
 check('21_probe20_root',a['exact_probe_responses']==21 and a['empty_root_404_responses']==20)
 check('root404_missing_length_rejected',not strict_ok({'path':'/','http_status':404}))
 check('nonempty_root404_rejected',not strict_ok({'path':'/','http_status':404,'body_bytes_sampled':19}))
 check('wrong_marker_rejected',not strict_ok({'path':'/probe','http_status':200,'exact_marker':False}))
 for label,mutate in [
  ('bad_late_response',lambda x:x['public_attempts'][-1].update(http_status=502)),
  ('counter_mismatch',lambda x:x['service']['http_classification'].update(root_get=19)),
  ('missing_cleanup',lambda x:x['cleanup'].pop('delete_returned')),
  ('bad_exit',lambda x:x['service'].update(exit_code=1)),
  ('extra_method',lambda x:x['service']['counters']['method_counts'].update(POST=1)),
  ('missing_pair_member',lambda x:x['public_attempts'].pop()),
  ('duplicate_row',lambda x:x['public_attempts'].append(copy.deepcopy(x['public_attempts'][-1]))),
  ('missing_whole_pair',lambda x:x['public_attempts'].__delitem__(slice(20,22))),
  ('boolean_pair',lambda x:x['public_attempts'][0].update(pair=False)),
  ('negative_pair',lambda x:x['public_attempts'][0].update(pair=-1)),
  ('missing_exit',lambda x:x['service'].pop('exit_code')),
  ('boolean_exit',lambda x:x['service'].update(exit_code=False)),
  ('boolean_zero_counter',lambda x:x['service']['counters'].update(parse_error_count=False)),
  ('boolean_empty_body',lambda x:x['public_attempts'][-1].update(body_bytes_sampled=False)),
  ('string_status',lambda x:x['public_attempts'][-1].update(http_status='404')),
  ('null_service',lambda x:x.update(service=None)),
  ('null_rows',lambda x:x.update(public_attempts=None)),
  ('reordered_rows',lambda x:x['public_attempts'].reverse()),
 ]:
  candidate=copy.deepcopy(r);mutate(candidate)
  check(label,assess(candidate)['status']!='PASS')
 for value in (None,[],{},'bad'):
  check('malformed_top_'+repr(value),assess(value)['status']!='PASS')
 return tests
if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('report',type=pathlib.Path)
 parser.add_argument('--self-test',action='store_true')
 parser.add_argument('--output',type=pathlib.Path)
 args=parser.parse_args();p=args.report;raw=p.read_bytes()
 r=json.loads(raw);digest=hashlib.sha256(raw).hexdigest()
 if args.self_test and digest!=V9_SHA256:raise SystemExit('Pinned v9 report hash mismatch')
 result={'assessment':assess(r),'tests':tests(r) if args.self_test else [],'source_report_sha256':digest,'platform_requests':0}
 if args.output:
  args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(result,ensure_ascii=False,indent=2))
 sys.exit(0 if result['assessment']['status']=='PASS' else 1)
