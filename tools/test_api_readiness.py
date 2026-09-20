"""Local HTTP fixtures only; never contact Lightning."""
import contextlib, http.server, json, os, pathlib, subprocess, sys, threading, time, unittest
SCRIPT=pathlib.Path(__file__).with_name('api_readiness.py')
VERSION={'game':'ridge-runner','release':'playtest-35445091317-1','archive_sha256':'ad73d9ba67b3cf31f5c9ab57c84d1eeeb74653f748a73d76b5dc32c9b36192f5'}
SENTINEL='fixture-secret-never-print-82934'

@contextlib.contextmanager
def fixture(mode):
    state={'requests':0,'writes':0}
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            state['requests']+=1
            if self.path!='/version.json':
                self.send_error(404);return
            status=200;body=json.dumps(VERSION).encode()
            if mode=='delayed' and state['requests']<3:status=503
            if mode=='unready':status=503
            if mode=='wrong':body=json.dumps({**VERSION,'release':'other'}).encode()
            if mode=='invalid':body=(SENTINEL+'not-json').encode()
            if mode=='large':body=b'x'*4097
            if mode=='redirect':status=302
            if mode=='slow':time.sleep(.6)
            self.send_response(status)
            self.send_header('Content-Length',str(len(body)))
            if mode=='redirect':self.send_header('Location','http://example.invalid/secret')
            self.end_headers()
            try:self.wfile.write(body)
            except OSError:pass
        def do_POST(self):
            state['writes']+=1;self.send_error(405)
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:yield server.server_port,state
    finally:server.shutdown();server.server_close();thread.join()

class Tests(unittest.TestCase):
    def run_candidate(self,port,timeout='.35'):
        env={**os.environ,'LIGHTNING_API_KEY':SENTINEL,'HTTP_PROXY':'http://127.0.0.1:1','NO_PROXY':''}
        start=time.monotonic()
        p=subprocess.run([sys.executable,str(SCRIPT),'--port',str(port),'--timeout',timeout],
            capture_output=True,text=True,env=env,timeout=4)
        self.assertNotIn(SENTINEL,p.stdout+p.stderr)
        self.assertEqual(p.stderr,'')
        self.assertLess(time.monotonic()-start,3)
        return p,json.loads(p.stdout)
    def test_ready_reuses_server(self):
        with fixture('ready') as (port,state):
            p,r=self.run_candidate(port)
            self.assertEqual(p.returncode,0);self.assertEqual(r['status'],'READY')
            self.assertEqual(r['attempts'],1);self.assertEqual(state,{'requests':1,'writes':0})
    def test_delayed_ready(self):
        with fixture('delayed') as (port,state):
            p,r=self.run_candidate(port,'1')
            self.assertEqual(p.returncode,0);self.assertEqual(r['attempts'],3)
            self.assertEqual(state['writes'],0)
    def test_wrong_version_rejected(self):
        with fixture('wrong') as (port,state):
            p,r=self.run_candidate(port)
            self.assertEqual(p.returncode,2);self.assertEqual(r['reason'],'VERSION_MISMATCH')
            self.assertEqual(state['requests'],1)
    def test_unready_timeout(self):
        with fixture('unready') as (port,state):
            p,r=self.run_candidate(port)
            self.assertEqual(p.returncode,3);self.assertEqual(r['reason'],'DEADLINE')
    def test_no_listener(self):
        import socket
        with socket.socket() as s:
            s.bind(('127.0.0.1',0));port=s.getsockname()[1]
            p,r=self.run_candidate(port)
            self.assertEqual(p.returncode,3);self.assertEqual(r['reason'],'DEADLINE')
    def test_malformed_redacted(self):
        with fixture('invalid') as (port,state):
            p,r=self.run_candidate(port)
            self.assertEqual(p.returncode,2);self.assertEqual(r['reason'],'INVALID_VERSION_JSON')
    def test_redirect_not_followed(self):
        with fixture('redirect') as (port,state):
            p,r=self.run_candidate(port)
            self.assertEqual(p.returncode,2);self.assertEqual(r['reason'],'HTTP_REJECTED')
            self.assertEqual(state['requests'],1)
    def test_oversize_rejected(self):
        with fixture('large') as (port,state):
            p,r=self.run_candidate(port)
            self.assertEqual(p.returncode,2);self.assertEqual(r['reason'],'VERSION_TOO_LARGE')
    def test_slow_response_deadline(self):
        with fixture('slow') as (port,state):
            p,r=self.run_candidate(port)
            self.assertEqual(p.returncode,3);self.assertEqual(r['reason'],'DEADLINE')
    def test_no_mutating_capabilities(self):
        import ast
        tree=ast.parse(SCRIPT.read_text())
        imports={n.name for a in ast.walk(tree) if isinstance(a,ast.Import) for n in a.names}
        self.assertEqual(imports,{'argparse','http.client','json','math','sys','time'})
        calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call)]
        requests=[n for n in calls if isinstance(n.func,ast.Attribute) and n.func.attr=='request']
        self.assertEqual(len(requests),1)
        self.assertEqual(ast.literal_eval(requests[0].args[0]),'GET')
        connections=[n for n in calls if isinstance(n.func,ast.Attribute) and n.func.attr=='HTTPConnection']
        self.assertEqual(len(connections),1)
        self.assertEqual(ast.literal_eval(connections[0].args[0]),'127.0.0.1')
        forbidden={'exec','eval','open','__import__','compile'}
        self.assertFalse(any(isinstance(n.func,ast.Name) and n.func.id in forbidden for n in calls))

if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(Tests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    failures=[{'test':test.id(),'detail':text[-2000:].replace(SENTINEL,'[REDACTED]')} for test,text in result.failures+result.errors]
    report={'status':'PASS' if result.wasSuccessful() else 'FAIL','kind':'local_fixture_readiness_candidate',
        'tests_run':result.testsRun,'failures':failures,'real_studio_requests':0,
        'auto_start_test':'NOT_RUN','platform_command_lifecycle':'UNVERIFIED'}
    out=pathlib.Path('out');out.mkdir(exist_ok=True)
    (out/'studio-probe.json').write_text(json.dumps(report,indent=2)+'\n')
    sys.exit(0 if result.wasSuccessful() else 1)
