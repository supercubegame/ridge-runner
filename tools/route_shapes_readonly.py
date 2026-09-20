"""Distinguish non-null default objects from populated upstream metadata."""
import json,sys
import route_metadata_readonly as b
base=b.summarize
def populated_leaves(value):
 if isinstance(value,dict):return sum(populated_leaves(v) for v in value.values())
 if isinstance(value,list):return sum(populated_leaves(v) for v in value)
 return int(value is not None and value is not False and value!=0 and value!='')
def shape(value):
 return {'json_type':'OBJECT' if isinstance(value,dict) else 'NULL' if value is None else 'OTHER','key_count':len(value) if isinstance(value,dict) else 0,'nondefault_leaf_count':populated_leaves(value)}
def summarize(raw,root_map,up_map):
 result=base(raw,root_map,up_map)
 result['upstream_object_shapes']={k:shape(raw.get(k)) for k in ('job','managed','openai','prewarm')}
 job=raw.get('job') or {};up=raw['cloudspace']
 result['job_fields']={
  'job_id_present':bool(job.get('jobId')),
  'job_id_matches_cloudspace_job':bool(job.get('jobId')) and job.get('jobId')==up.get('studioJobId'),
  'port_class':'ABSENT_OR_EMPTY' if not job.get('port') else 'ZERO_STRING' if job['port']=='0' else 'SAME_AS_8060' if job['port']=='8060' else 'OTHER',
  'idle_seconds_class':'ABSENT_OR_EMPTY' if not job.get('idleShutdownSeconds') else 'ZERO_STRING' if job['idleShutdownSeconds']=='0' else 'OTHER',
  'auto_start':b.tri(job.get('autoStart')),
  'idle_shutdown':b.tri(job.get('idleShutdown')),
 }
 result['warning']='NON_NULL_OBJECT_DOES_NOT_PROVE_ACTIVE_UPSTREAM'
 return result
b.summarize=summarize
if __name__=='__main__':
 if '--self-test' in sys.argv:
  b.test()
  assert shape({})=={'json_type':'OBJECT','key_count':0,'nondefault_leaf_count':0}
  assert populated_leaves({'id':'','ready':False,'count':0,'nested':{'a':None},'items':[]})==0
  assert populated_leaves({'id':'sentinel-SECRET','nested':{'a':True}})==2
  assert 'sentinel-SECRET' not in json.dumps(shape({'id':'sentinel-SECRET'}))
  assert populated_leaves({'port':'0','idleShutdownSeconds':'0'})==2
  print('PASS default-object and nondefault-value redaction fixtures')
 else:sys.exit(b.main())
