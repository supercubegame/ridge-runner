"""Auditable v4-to-v5 adapter: only endpoint type changes operationally."""
import pathlib,sys
path=pathlib.Path(__file__).with_name('runtime_v4.py')
source=path.read_text()
changes=[
 ("Fresh 12:47 authorization: omit only upstream instance_type.","Fresh 12:55 authorization: PLUGIN_PORT with Basic required.",1),
 ("audit/runtime-8061-v4-20260920","audit/runtime-8061-v5-20260920",1),
 ("claims/runtime-8061-v4-20260920-1247.json","claims/runtime-8061-v5-20260920-1255.json",1),
 ("12:47 one fresh Basic PLUGIN_API 8061 endpoint omit instance_type only, auto_start false, diagnostics max180s, delete only new endpoint; no machine switch or Studio start/stop","12:55 one fresh Basic PLUGIN_PORT 8061 endpoint, only type changed, abort if Basic unsupported, omit instance_type, auto_start false, diagnostics max180s, delete only new endpoint; no machine switch or Studio start/stop",1),
 ("Claim approved 12:47 single-variable trial","Claim approved 12:55 endpoint type trial",1),
 ("runtime-v4-claim.json","runtime-v5-claim.json",2),
 ("'runtime-v4'","'runtime-v5'",1),
 ("approved_runtime_v4_omit_instance_type","approved_runtime_v5_plugin_port",1),
 ("V1EndpointType.PLUGIN_API","V1EndpointType.PLUGIN_PORT",2),
 ("print('Runtime v4:'","print('Runtime v5:'",1),
]
for old,new,count in changes:
 if source.count(old)!=count:raise RuntimeError('BASELINE_DRIFT')
 source=source.replace(old,new)
# The inherited test reads the v4 baseline for its creation-field AST check.
# Independently check the actually executed v5 creation and readback types.
import ast
tree=ast.parse(source)
calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='V1UpstreamCloudSpace']
assert len(calls)==1
fields={k.arg:k.value for k in calls[0].keywords}
assert set(fields)=={'cloudspace_id','port','auto_start','command','type'}
assert isinstance(fields['type'],ast.Attribute) and fields['type'].attr=='PLUGIN_PORT'
assert isinstance(fields['auto_start'],ast.Constant) and fields['auto_start'].value is False
assert "live.auth.enabled is True" in source and "'BASIC_CONFIG'" in source
exec(compile(source,str(path), 'exec'),{'__name__':'__main__','__file__':str(path)})
