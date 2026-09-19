#!/usr/bin/env python3
"""User-pinned host identity, independent CI scan, strict SSH and redacted evidence."""
import base64,hashlib,json,os,pathlib,re,shlex,subprocess,sys,tempfile
OUT=pathlib.Path('out');OUT.mkdir(exist_ok=True)
EXPECTED='SHA256:AerGo33D0P3gzPfHmG0WwW3D3D9j6UsJ7epj1agSi0U'
report={'schema':2,'sha':os.environ.get('GITHUB_SHA','local'),'run_id':os.environ.get('GITHUB_RUN_ID','local'),'status':'FAIL','checks':[]}
def record(name,status,detail):
    report['checks'].append({'name':name,'status':status,'detail':detail});print(status,name,detail,flush=True)
def classify(error):
    low=error.lower()
    for phrase,category in [('remote host identification has changed','HOST_KEY_CHANGED'),('host key verification failed','HOST_IDENTITY_NOT_VERIFIED'),('no matching host key type found','HOST_SIGNATURE_ALGORITHM_MISMATCH'),('permission denied','SSH_AUTHORIZATION_REJECTED'),('could not resolve hostname','DNS_FAILED'),('connection timed out','CONNECTION_TIMEOUT'),('connection refused','CONNECTION_REFUSED'),('no route to host','NO_ROUTE'),('error in libcrypto','PRIVATE_KEY_PARSE_ERROR'),('load key','PRIVATE_KEY_LOAD_ERROR')]:
        if phrase in low:return category
    return 'SSH_OR_REMOTE_COMMAND_FAILED'
def command(args,**kwargs):
    return subprocess.run(args,capture_output=True,text=True,timeout=40,**kwargs)
def key_records(text):
    rows={}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith('#'):continue
        bits=line.split()
        if len(bits)<3 or bits[0].startswith('@'):raise ValueError('Invalid host-key record')
        raw=base64.b64decode(bits[2],validate=True)
        if len(raw)<8:raise ValueError('Invalid host-key blob')
        length=int.from_bytes(raw[:4],'big')
        if raw[4:4+length].decode()!=bits[1]:raise ValueError('Host-key type mismatch')
        fp='SHA256:'+base64.b64encode(hashlib.sha256(raw).digest()).decode().rstrip('=')
        rows[fp]=(bits[1],bits[2])
    return rows
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
        names=['STUDIO_SSH_TARGET','STUDIO_SSH_PRIVATE_KEY','STUDIO_SSH_KNOWN_HOSTS']
        missing=[k for k in names if not os.environ.get(k,'').strip()]
        if missing:record('configuration','FAIL','Missing Secrets: '+', '.join(missing));return 1
        record('configuration','PASS','All three required Secrets are present')
        target=os.environ['STUDIO_SSH_TARGET'].strip()
        if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*@ssh\.lightning\.ai',target):
            record('target','FAIL','Expected login@ssh.lightning.ai only');return 1
        record('target','PASS','Restricted to Lightning SSH gateway')
        clean={k:v for k,v in os.environ.items() if k not in names and k not in ('GH_TOKEN','GITHUB_TOKEN')}
        with tempfile.TemporaryDirectory(prefix='ridge-ssh-') as folder:
            key=pathlib.Path(folder)/'key';known=pathlib.Path(folder)/'known_hosts';pinned=pathlib.Path(folder)/'pinned'
            key.write_text(os.environ[names[1]].replace('\r\n','\n').strip()+'\n');key.chmod(0o600)
            known.write_text(os.environ[names[2]].replace('\r\n','\n').strip()+'\n');known.chmod(0o600)
            r=command(['ssh-keygen','-y','-P','','-f',str(key)],env=clean)
            if r.returncode:record('key_format','FAIL','Invalid or passphrase-protected private key; output withheld');return 1
            record('key_format','PASS','Private key parsed without passphrase')
            r=command(['ssh-keygen','-F','ssh.lightning.ai','-f',str(known)],env=clean)
            if r.returncode:record('known_hosts','FAIL','No matching gateway host record in supplied Secret');return 1
            supplied=key_records(r.stdout)
            if set(supplied)!={EXPECTED} or supplied[EXPECTED][0]!='ssh-rsa':
                record('secret_fingerprint','FAIL','Supplied host record does not exactly match user-approved RSA pin; stopped');return 1
            record('secret_fingerprint','PASS',EXPECTED)
            r=command(['ssh-keyscan','-T','15','-t','rsa,ecdsa,ed25519','ssh.lightning.ai'],env=clean)
            scanned=key_records(r.stdout)
            for fp in sorted(scanned):record('ci_observed_fingerprint','INFO',scanned[fp][0]+' '+fp)
            if r.returncode or set(scanned)!={EXPECTED}:
                record('cross_network_comparison','FAIL','CI scan empty, failed, or differs from approved pin; no login attempted');return 1
            record('cross_network_comparison','PASS','CI observation and user observation match; not independent official certification')
            pinned.write_text('ssh.lightning.ai '+supplied[EXPECTED][0]+' '+supplied[EXPECTED][1]+'\n');pinned.chmod(0o600)
            args=['ssh','-v','-F','/dev/null','-T','-i',str(key),'-o','IdentitiesOnly=yes','-o','IdentityAgent=none','-o','BatchMode=yes','-o','ConnectTimeout=12','-o','ConnectionAttempts=1','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(pinned),'-o','GlobalKnownHostsFile=/dev/null','-o','UpdateHostKeys=no','-o','ForwardAgent=no','-o','ClearAllForwardings=yes','-o','ServerAliveInterval=5','-o','ServerAliveCountMax=2']
            remote_command='python3 -c '+shlex.quote(REMOTE)
            r=command(args+[target,remote_command],env=clean)
            report['legacy_host_signature_fallback']=False
            if r.returncode and classify(r.stderr)=='HOST_SIGNATURE_ALGORITHM_MISMATCH' and 'Their offer: ssh-rsa' in r.stderr:
                record('default_host_algorithms','WARN','Gateway offers only legacy ssh-rsa signatures; applying user-authorized host-only exception')
                r=command(args+['-o','HostKeyAlgorithms=+ssh-rsa',target,remote_command],env=clean)
                report['legacy_host_signature_fallback']=True
            if r.returncode:record('ssh_session','FAIL',classify(r.stderr));return 1
            found=re.search(r'kex: host key algorithm: ([a-zA-Z0-9@._+-]+)',r.stderr)
            if found:record('negotiated_host_signature','PASS',found.group(1))
            lines=[l.split('RIDGE_PROBE_JSON=',1)[1] for l in r.stdout.splitlines() if l.startswith('RIDGE_PROBE_JSON=')]
            if len(lines)!=1:record('ssh_session','FAIL','Expected one structured remote response; raw output withheld');return 1
            remote=json.loads(lines[0]);record('ssh_session','PASS','Strict host verification, authentication and read-only remote command succeeded')
            for name in ['linux','x86_64','python_compatible','curl','port_8060_available','disk_1g_available']:
                value=remote.get(name)
                if not isinstance(value,bool):raise ValueError('Invalid remote reply')
                record('remote_'+name,'PASS' if value else 'WARN','Available' if value else 'Requires review before deployment')
            report['status']='PASS';return 0
    except subprocess.TimeoutExpired:
        record('probe','FAIL','Hard timeout; no raw output published');return 1
    except Exception:
        record('probe','FAIL','Malformed data or unexpected probe failure; raw exception suppressed');return 1
    finally:
        (OUT/'studio-probe.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':sys.exit(main())
