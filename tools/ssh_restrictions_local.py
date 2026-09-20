"""Real loopback SSH tests in disposable CI only. Never access Lightning."""
import http.server,json,os,pathlib,signal,socket,subprocess,tempfile,threading,time

def port():
 with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
def run(args,**kw):return subprocess.run(args,capture_output=True,text=True,timeout=15,**kw)
def main():
 report={'kind':'isolated_loopback_sshd_restrictions','status':'FAIL','platform_requests':0,'lightning_credentials':'NOT_PROVIDED','tests':[],'limitations':['Local CI OpenSSH, not Lightning SSH implementation.','No proof of Lightning support, authentication or forwarding.','Temporary loopback test daemon permits root key login with StrictModes disabled for fixture paths; not a deployment recommendation.']}
 processes=[];httpd=None
 def check(name,ok):
  report['tests'].append({'name':name,'pass':bool(ok)})
  if not ok:raise RuntimeError('CHECK_FAILED')
 try:
  assert not any(os.environ.get(k) for k in ('LIGHTNING_USER_ID','LIGHTNING_API_KEY','STUDIO_SSH_PRIVATE_KEY','GH_TOKEN','GITHUB_TOKEN'))
  report['ssh_version']=run(['ssh','-V']).stderr.strip()
  with tempfile.TemporaryDirectory(prefix='ssh-fixture-') as tmp:
   d=pathlib.Path(tmp);key=d/'client';host=d/'host';auth=d/'authorized';known=d/'known';config=d/'sshd.conf'
   for path in (key,host):
    r=run(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(path)]);assert r.returncode==0
   pub=(d/'client.pub').read_text().strip();hp=(d/'host.pub').read_text().split();sp=port();target=port();wrong=port()
   known.write_text('[127.0.0.1]:'+str(sp)+' '+hp[0]+' '+hp[1]+'\n')
   def options(value):auth.write_text(value+' '+pub+'\n')
   options('restrict')
   config.write_text('\n'.join(['Port '+str(sp),'ListenAddress 127.0.0.1','HostKey '+str(host),'PidFile '+str(d/'pid'),'AuthorizedKeysFile '+str(auth),'StrictModes no','PermitRootLogin yes','PasswordAuthentication no','KbdInteractiveAuthentication no','PubkeyAuthentication yes','UsePAM no','AllowUsers root','AllowTcpForwarding yes','AllowStreamLocalForwarding yes','GatewayPorts no','PermitTunnel no','LogLevel ERROR'])+'\n')
   assert run(['sudo','-n','/usr/sbin/sshd','-t','-f',str(config)]).returncode==0
   daemon=subprocess.Popen(['sudo','-n','/usr/sbin/sshd','-D','-e','-f',str(config)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True);processes.append(daemon)
   for _ in range(60):
    try:
     with socket.create_connection(('127.0.0.1',sp),.1):break
    except OSError:time.sleep(.05)
   base=['ssh','-F','/dev/null','-p',str(sp),'-i',str(key),'-o','IdentityAgent=none','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(known),'-o','GlobalKnownHostsFile=/dev/null','-o','UpdateHostKeys=no','-o','ConnectTimeout=3','-o','ConnectionAttempts=1','-o','ControlMaster=no','-o','ControlPath=none','-o','ForwardAgent=no','-o','ExitOnForwardFailure=yes','-T']
   r=run(base+['root@127.0.0.1','printf RESTRICT_ALLOWS_COMMAND'])
   check('restrict_alone_allows_command',r.returncode==0 and r.stdout=='RESTRICT_ALLOWS_COMMAND')
   options('restrict,command="/bin/false"')
   r=run(base+['root@127.0.0.1','printf SHOULD_NOT_RUN'])
   check('forced_false_blocks_requested_command',r.returncode==1 and not r.stdout)
   class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self,*a):pass
    def do_GET(self):
     body=b'fixture-marker';self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
   httpd=http.server.ThreadingHTTPServer(('127.0.0.1',target),Handler)
   threading.Thread(target=httpd.serve_forever,daemon=True).start()
   opts='restrict,port-forwarding,command="/bin/false",permitopen="127.0.0.1:'+str(target)+'"'
   options(opts)
   request='GET / HTTP/1.0\r\nHost: fixture\r\n\r\n'
   r=run(base+['-W','127.0.0.1:'+str(target),'root@127.0.0.1'],input=request)
   check('permitted_tcp_target_returns_marker',r.returncode==0 and r.stdout.endswith('fixture-marker'))
   r=run(base+['-W','127.0.0.1:'+str(wrong),'root@127.0.0.1'],input=request)
   check('other_tcp_target_denied',r.returncode!=0 and 'administratively prohibited' in r.stderr.lower())
   remote=port()
   forward=subprocess.Popen(base+['-N','-R','127.0.0.1:'+str(remote)+':127.0.0.1:'+str(target),'root@127.0.0.1'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True);processes.append(forward)
   body=b''
   for _ in range(60):
    try:
     with socket.create_connection(('127.0.0.1',remote),.2) as s:
      s.settimeout(2);s.sendall(request.encode())
      while True:
       part=s.recv(4096)
       if not part:break
       body+=part
     break
    except OSError:time.sleep(.05)
   check('permitopen_does_not_block_remote_forward',body.endswith(b'fixture-marker'))
   forward.terminate();forward.wait(timeout=5)
   options(opts+',permitlisten="none"')
   r=run(base+['-W','127.0.0.1:'+str(target),'root@127.0.0.1'],input=request)
   check('permitlisten_none_rejects_key_not_remote_only',r.returncode!=0 and 'permission denied' in r.stderr.lower())
   options('restrict,command="/bin/false"')
   r=run(base+['-W','127.0.0.1:'+str(target),'root@127.0.0.1'],input=request)
   check('restrict_without_reenable_blocks_tcp',r.returncode!=0 and 'administratively prohibited' in r.stderr.lower())
   for p in reversed(processes):
    if p.poll() is None:
     if p is daemon:run(['sudo','-n','kill','-TERM','--','-'+str(p.pid)])
     else:p.terminate()
     p.wait(timeout=5)
   check('created_processes_exited',all(p.poll() is not None for p in processes))
   report['status']='PASS'
 except Exception as e:report['error_type']=type(e).__name__
 finally:
  if httpd:httpd.shutdown();httpd.server_close()
  for p in reversed(processes):
   if p.poll() is None:
    try:run(['sudo','-n','kill','-TERM','--','-'+str(p.pid)]);p.wait(timeout=5)
    except Exception:report['cleanup_unconfirmed']=True
  pathlib.Path('out').mkdir(exist_ok=True);pathlib.Path('out/studio-probe.json').write_text(json.dumps(report,indent=2)+'\n')
  print(json.dumps({'status':report['status'],'tests':len(report['tests']),'passed':sum(t['pass'] for t in report['tests'])}))
 return 0 if report['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
