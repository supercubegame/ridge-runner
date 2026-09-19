#!/usr/bin/env python3
"""Read-only Studio probe. Public evidence contains fixed checks only, never raw SSH logs."""
import json,os,pathlib,re,shlex,subprocess,sys,tempfile
OUT=pathlib.Path('out');OUT.mkdir(exist_ok=True)
report={'schema':1,'sha':os.environ.get('GITHUB_SHA','local'),'run_id':os.environ.get('GITHUB_RUN_ID','local'),'status':'FAIL','checks':[]}
def record(name,status,detail):
    report['checks'].append({'name':name,'status':status,'detail':detail});print(status,name,detail,flush=True)
def classify(error):
    low=error.lower()
    for phrase,category in [('host key verification failed','HOST_IDENTITY_NOT_VERIFIED'),('remote host identification has changed','HOST_KEY_CHANGED'),('permission denied','SSH_AUTHORIZATION_REJECTED'),('could not resolve hostname','DNS_FAILED'),('connection timed out','CONNECTION_TIMEOUT'),('connection refused','CONNECTION_REFUSED'),('no route to host','NO_ROUTE'),('error in libcrypto','PRIVATE_KEY_PARSE_ERROR'),('load key','PRIVATE_KEY_LOAD_ERROR')]:
        if phrase in low:return category
    return 'SSH_OR_REMOTE_COMMAND_FAILED'
def command(args,**kwargs):
    return subprocess.run(args,capture_output=True,text=True,timeout=35,**kwargs)
REMOTE='''import json,platform,shutil,socket,sys
port=socket.socket()
try:
 port.bind(("127.0.0.1",8060)); free=True
except OSError: free=False
finally: port.close()
print("RIDGE_PROBE_JSON="+json.dumps({"linux":platform.system()=="Linux","x86_64":platform.machine()=="x86_64","python_compatible":sys.version_info>=(3,8),"curl":bool(shutil.which("curl")),"port_8060_available":free,"disk_1g_available":shutil.disk_usage(".").free>=1073741824}))
'''
def main():
    try:
        required=['STUDIO_SSH_TARGET','STUDIO_SSH_PRIVATE_KEY','STUDIO_SSH_KNOWN_HOSTS']
        missing=[k for k in required if not os.environ.get(k,'').strip()]
        if missing:
            record('configuration','FAIL','Missing Secrets: '+', '.join(missing));return 1
        record('configuration','PASS','All three required Secrets supplied to this run')
        target=os.environ['STUDIO_SSH_TARGET'].strip()
        if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*@ssh\.lightning\.ai',target):
            record('target','FAIL','Expected only login@ssh.lightning.ai, without ssh prefix, mailto, or options');return 1
        record('target','PASS','Login target restricted to Lightning SSH gateway')
        with tempfile.TemporaryDirectory(prefix='ridge-ssh-') as folder:
            key=pathlib.Path(folder)/'key';known=pathlib.Path(folder)/'known_hosts'
            key.write_text(os.environ['STUDIO_SSH_PRIVATE_KEY'].replace('\r\n','\n').strip()+'\n');key.chmod(0o600)
            known.write_text(os.environ['STUDIO_SSH_KNOWN_HOSTS'].replace('\r\n','\n').strip()+'\n');known.chmod(0o600)
            r=command(['ssh-keygen','-y','-P','','-f',str(key)])
            if r.returncode:
                record('key_format','FAIL','Private key invalid or requires passphrase; no key material logged');return 1
            record('key_format','PASS','OpenSSH accepted supplied private key without a passphrase')
            r=command(['ssh-keygen','-F','ssh.lightning.ai','-f',str(known)])
            if r.returncode:
                record('known_hosts','FAIL','No host entry for ssh.lightning.ai; provide known_hosts records, not just SHA256 fingerprint');return 1
            record('known_hosts','PASS','Gateway host entry present; SSH will enforce strict identity verification')
            clean={k:v for k,v in os.environ.items() if k not in required and k not in ('GH_TOKEN','GITHUB_TOKEN')}
            args=['ssh','-F','/dev/null','-T','-i',str(key),'-o','IdentitiesOnly=yes','-o','IdentityAgent=none','-o','BatchMode=yes','-o','ConnectTimeout=12','-o','ConnectionAttempts=1','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(known),'-o','GlobalKnownHostsFile=/dev/null','-o','ForwardAgent=no','-o','ClearAllForwardings=yes','-o','ServerAliveInterval=5','-o','ServerAliveCountMax=2',target,'python3 -c '+shlex.quote(REMOTE)]
            r=command(args,env=clean)
            if r.returncode:
                record('ssh_session','FAIL',classify(r.stderr));return 1
            lines=[l.split('RIDGE_PROBE_JSON=',1)[1] for l in r.stdout.splitlines() if l.startswith('RIDGE_PROBE_JSON=')]
            if len(lines)!=1:
                record('ssh_session','FAIL','No unique structured remote reply; raw output withheld');return 1
            remote=json.loads(lines[0])
            record('ssh_session','PASS','Strict host verification, key authentication, remote Python command and clean exit succeeded')
            for name in ['linux','x86_64','python_compatible','curl','port_8060_available','disk_1g_available']:
                value=remote.get(name)
                if not isinstance(value,bool):raise ValueError('Invalid remote response')
                record('remote_'+name,'PASS' if value else 'WARN','Available' if value else 'Not available; requires review before deployment')
            report['status']='PASS'
            return 0
    except subprocess.TimeoutExpired:
        record('probe','FAIL','Probe exceeded hard timeout; no raw output or secrets published');return 1
    except Exception:
        record('probe','FAIL','Unexpected probe error; raw exception suppressed to avoid disclosing credentials');return 1
    finally:
        (OUT/'studio-probe.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':sys.exit(main())
