#!/usr/bin/env python3
"""Safe structured SSH diagnostics; no raw SSH output, private key, login or paths."""
import base64,hashlib,re,sys
import studio_probe as probe
original=probe.command

def diagnostic_command(args,**kwargs):
    result=original(args,**kwargs)
    if args[:2]==['ssh-keygen','-y'] and result.returncode==0:
        parts=result.stdout.strip().split()
        if len(parts)>=2:
            fingerprint='SHA256:'+base64.b64encode(hashlib.sha256(base64.b64decode(parts[1],validate=True)).digest()).decode().rstrip('=')
            kind=parts[0] if parts[0] in ('ssh-ed25519','ssh-rsa','ecdsa-sha2-nistp256') else 'other-public-key-type'
            probe.record('client_public_key','INFO',kind+' '+fingerprint)
    if args[0]=='ssh':
        for expression,name in [(r'kex: host key algorithm: ([a-zA-Z0-9@._+-]+)','host_signature_algorithm'),(r'kex: algorithm: ([a-zA-Z0-9@._+-]+)','key_exchange_algorithm')]:
            match=re.search(expression,result.stderr)
            if match:probe.record(name,'INFO',match.group(1))
        for marker,name in [('Offering public key:','client_key_offered'),('Server accepts key:','server_accepted_client_key'),('Authenticated to ','authentication_completed')]:
            probe.record(name,'INFO','yes' if marker in result.stderr else 'not observed')
        if 'Permission denied (publickey)' in result.stderr:
            probe.record('authorization_detail','FAIL','Server rejected public-key authentication; host signature policy is not the blocker')
    return result

probe.command=diagnostic_command
if __name__=='__main__':sys.exit(probe.main())
