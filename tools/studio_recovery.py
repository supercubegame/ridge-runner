#!/usr/bin/env python3
"""Preserving startup hook installer; never stops Studio or an existing service."""
import hashlib,json,os,pathlib,shlex,subprocess,sys,tempfile
BEGIN=b'# BEGIN RIDGE RUNNER PREVIEW V1'
END=b'# END RIDGE RUNNER PREVIEW V1'
ARCHIVE='ad73d9ba67b3cf31f5c9ab57c84d1eeeb74653f748a73d76b5dc32c9b36192f5'
SERVER_HASH='6e6ad8ec1fc3699abe5df1ca269b54c2515df50a30a367133be5fa2848e95a47'
RUNNER=r'''import hashlib,json,os,pathlib,socket,subprocess,sys,time,urllib.request
base=pathlib.Path(sys.argv[1])
release=base/'ad73d9ba67b3cf31f5c9ab57c84d1eeeb74653f748a73d76b5dc32c9b36192f5'
expected={'archive_sha256':'ad73d9ba67b3cf31f5c9ab57c84d1eeeb74653f748a73d76b5dc32c9b36192f5','game':'ridge-runner','release':'playtest-35445091317-1'}
def version():
 with urllib.request.urlopen('http://127.0.0.1:8060/version.json',timeout=3) as r:return json.load(r)
def main():
 server=release/'server.py';site=release/'site'
 if base.is_symlink() or release.is_symlink() or site.is_symlink() or server.is_symlink():raise ValueError('UNSAFE_PATH')
 if hashlib.sha256(server.read_bytes()).hexdigest()!='6e6ad8ec1fc3699abe5df1ca269b54c2515df50a30a367133be5fa2848e95a47':raise ValueError('SERVER_MISMATCH')
 manifest=json.loads((base/'resume-manifest.json').read_text())
 for name,want in manifest.items():
  p=site/name
  if p.is_symlink() or not p.resolve().is_relative_to(site.resolve()) or hashlib.sha256(p.read_bytes()).hexdigest()!=want:raise ValueError('ASSET_MISMATCH')
 if json.loads((site/'version.json').read_text())!=expected:raise ValueError('VERSION_MISMATCH')
 free=True
 with socket.socket() as s:
  try:s.bind(('0.0.0.0',8060))
  except OSError:free=False
 if not free:
  if version()!=expected:raise ValueError('PORT_CONFLICT')
  return {'status':'PASS','mode':'reused'}
 env={'PATH':os.environ.get('PATH','/usr/bin:/bin'),'LANG':'C.UTF-8','HOME':str(base.parent)}
 with (release/'server.log').open('ab') as log:
  p=subprocess.Popen([sys.executable,str(server),str(site)],cwd=release,stdin=subprocess.DEVNULL,stdout=log,stderr=log,env=env,start_new_session=True,close_fds=True)
 (release/'server.pid').write_text(str(p.pid)+'\n')
 for _ in range(40):
  if p.poll() is not None:raise ValueError('SERVER_EXITED')
  try:
   if version()==expected:return {'status':'PASS','mode':'started'}
  except Exception:pass
  time.sleep(.2)
 raise ValueError('SERVER_NOT_READY')
try:
 result=main();print(json.dumps(result));sys.exit(0)
except Exception as e:
 print(json.dumps({'status':'FAIL','error_type':type(e).__name__}));sys.exit(1)
'''
def prepare_hook(old,block):
    if BEGIN in old or END in old:
        if old.count(BEGIN)!=1 or old.count(END)!=1 or not old.endswith(block):raise ValueError('EXISTING_HOOK_DIFFERS')
        return old
    # Do not append after scripts that may terminate or consume appended input.
    text=old.decode('utf-8')
    import re
    if re.search(r'(^|[;\n])\s*(exit|exec|return)\b|<<|\\\s*$',text):raise ValueError('COMPLEX_STARTUP_REQUIRES_REVIEW')
    return old+block

def write_exact(path,data):
    if path.is_symlink():raise ValueError('SYMLINK_REFUSED')
    if path.exists():
        if path.read_bytes()!=data:raise ValueError('EXISTING_FILE_DIFFERS')
    else:
        with path.open('xb') as f:f.write(data)
        path.chmod(0o600)

def remote():
    out={'status':'FAIL','stage':'inspect','actual_sleep_wake_test':'NOT_RUN','auto_wake':'NOT_CONFIGURED'}
    try:
        home=pathlib.Path('/teamspace/studios/this_studio');base=home/'.ridge-runner-preview';release=base/ARCHIVE
        startup=home/'.lightning_studio';hook=startup/'on_start.sh'
        if any(p.is_symlink() for p in (base,release,startup,hook)):raise ValueError('SYMLINK_REFUSED')
        if not (release/'site/version.json').is_file():raise ValueError('DEPLOYMENT_NOT_FOUND')
        if hashlib.sha256((release/'server.py').read_bytes()).hexdigest()!=SERVER_HASH:raise ValueError('SERVER_MISMATCH')
        old=hook.read_bytes() if hook.exists() else b'#!/bin/bash\n'
        if len(old)>65536:raise ValueError('STARTUP_TOO_LARGE')
        runner=base/'resume-v1.py'
        cmd=' '.join(shlex.quote(x) for x in (sys.executable,str(runner),str(base)))
        block=('\n'+BEGIN.decode()+'\n'+cmd+' >> '+shlex.quote(str(base/'resume.log'))+' 2>&1 &\n'+END.decode()+'\n').encode()
        merged=prepare_hook(old,block)
        checked=subprocess.run(['/bin/bash','-n'],input=merged,capture_output=True)
        if checked.returncode:raise ValueError('STARTUP_SYNTAX_INVALID')
        out['checks']={'existing_startup_inspected':True,'original_bytes_preserved':merged.startswith(old),'bash_syntax':True}
        manifest={}
        for p in sorted((release/'site').rglob('*')):
            if p.is_symlink():raise ValueError('SYMLINK_REFUSED')
            if p.is_file():manifest[str(p.relative_to(release/'site'))]=hashlib.sha256(p.read_bytes()).hexdigest()
        if not manifest:raise ValueError('EMPTY_SITE')
        out['stage']='install_runner'
        write_exact(base/'resume-manifest.json',(json.dumps(manifest,sort_keys=True)+'\n').encode())
        write_exact(runner,RUNNER.encode())
        out['stage']='live_idempotence'
        modes=[]
        for _ in range(2):
            r=subprocess.run([sys.executable,str(runner),str(base)],capture_output=True,text=True,timeout=25)
            evidence=json.loads(r.stdout)
            if r.returncode or evidence.get('status')!='PASS':raise ValueError('RESUME_CHECK_FAILED')
            modes.append(evidence['mode'])
        out['resume_modes']=modes
        out['stage']='preserve_and_install_hook'
        startup.mkdir(exist_ok=True)
        backup=base/('on-start-before-'+hashlib.sha256(old).hexdigest()+'.sh')
        write_exact(backup,old)
        if merged!=old:
            mode=(hook.stat().st_mode & 0o777) if hook.exists() else 0o700
            with tempfile.NamedTemporaryFile(dir=startup,delete=False) as f:
                tmp=pathlib.Path(f.name);f.write(merged);f.flush();os.fsync(f.fileno())
            tmp.chmod(mode)
            if (hook.read_bytes() if hook.exists() else b'#!/bin/bash\n')!=old:raise ValueError('STARTUP_CHANGED_DURING_INSTALL')
            os.replace(tmp,hook)
        out['checks']['hook_readback']=hook.read_bytes()==merged
        out['checks']['backup_readback']=backup.read_bytes()==old
        out['checks']['single_managed_block']=hook.read_bytes().count(BEGIN)==1
        if not all(out['checks'].values()):raise ValueError('READBACK_MISMATCH')
        out['status']='PASS';out['stage']='complete'
    except Exception as e:
        out['error_type']=type(e).__name__
        if isinstance(e,ValueError) and str(e).isupper() and len(str(e))<80:out['error_code']=str(e)
    print('RIDGE_RECOVERY_JSON='+json.dumps(out),flush=True)
    return 0 if out['status']=='PASS' else 1

def client():
    import studio_diagnostics
    probe=studio_diagnostics.probe;original=probe.command;recovery=None
    def command(args,**kwargs):
        nonlocal recovery
        result=original(args,**kwargs)
        if args[0]=='ssh' and result.returncode==0 and 'RIDGE_PROBE_JSON=' in result.stdout and recovery is None:
            source=pathlib.Path(__file__).read_text()
            try:
                r=subprocess.run(args[:-1]+['python3 -c '+shlex.quote(source)+' --remote'],capture_output=True,text=True,timeout=90,env=kwargs.get('env'))
                lines=[s.split('=',1)[1] for s in r.stdout.splitlines() if s.startswith('RIDGE_RECOVERY_JSON=')]
                recovery=json.loads(lines[0]) if len(lines)==1 else {'status':'FAIL','stage':'missing_reply'}
                if r.returncode:recovery['status']='FAIL'
            except Exception as e:recovery={'status':'UNVERIFIED','stage':'remote_execution','error_type':type(e).__name__}
        return result
    p=pathlib.Path('out/studio-probe.json')
    prior=json.loads(p.read_text()) if p.exists() else {'status':'FAIL'}
    probe.command=command
    code=probe.main()
    prior['recovery']=recovery or {'status':'NOT_RUN'}
    ok=code==0 and recovery and recovery.get('status')=='PASS'
    if not ok:prior['status']='FAIL'
    p.write_text(json.dumps(prior,indent=2)+'\n')
    return 0 if ok else 1
if __name__=='__main__':sys.exit(remote() if '--remote' in sys.argv else client())
