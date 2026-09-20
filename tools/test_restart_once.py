import importlib.util, pathlib, unittest
P = pathlib.Path(__file__).with_name('restart_once.py')
spec = importlib.util.spec_from_file_location('restart', P)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class SafetyTests(unittest.TestCase):
    def policy(self):
        p = m.Policy()
        p.routes = {'stop': ('POST', '/v1/projects/team/cloudspaces/studio/stop'),
                    'start': ('POST', '/v1/projects/team/cloudspaces/studio/start')}
        return p
    def test_read(self):
        self.policy().check('GET', 'lightning.ai', '/v1/projects')
    def test_public_read(self):
        self.policy().check('GET', m.PREVIEW_HOST, '/version.json')
    def test_other_host(self):
        with self.assertRaises(m.SafetyError): self.policy().check('GET','evil.example','/')
    def test_http(self):
        with self.assertRaises(m.SafetyError): self.policy().check('GET','lightning.ai','http://lightning.ai/')
    def test_keepalive(self):
        with self.assertRaises(m.SafetyError): self.policy().check('GET','lightning.ai','/keepalive')
    def test_no_unarmed_write(self):
        with self.assertRaises(m.SafetyError): self.policy().check('POST','lightning.ai',self.policy().routes['stop'][1])
    def test_one_stop(self):
        p=self.policy();p.armed='stop';p.check('POST','lightning.ai',p.routes['stop'][1]);p.armed='stop'
        with self.assertRaises(m.SafetyError):p.check('POST','lightning.ai',p.routes['stop'][1])
    def test_start_requires_stopped(self):
        p=self.policy();p.armed='start'
        with self.assertRaises(m.SafetyError):p.check('POST','lightning.ai',p.routes['start'][1])
    def test_authorized_cycle(self):
        p=self.policy();p.armed='stop';p.check('POST','lightning.ai',p.routes['stop'][1]);p.stopped=True;p.armed='start';p.check('POST','lightning.ai',p.routes['start'][1])
        self.assertEqual(p.writes,{'stop':1,'start':1})
    def test_wrong_target(self):
        p=self.policy();p.armed='stop'
        with self.assertRaises(m.SafetyError):p.check('POST','lightning.ai','/v1/projects/team/cloudspaces/other/stop')
    def test_settings_write(self):
        with self.assertRaises(m.SafetyError):self.policy().check('PUT','lightning.ai','/sleepconfig')
    def test_delete(self):
        with self.assertRaises(m.SafetyError):self.policy().check('DELETE','lightning.ai','/v1/projects')
    def test_preview_write(self):
        p=self.policy();p.armed='stop'
        with self.assertRaises(m.SafetyError):p.check('POST',m.PREVIEW_HOST,p.routes['stop'][1])
    def test_secret_sentinel(self):
        with self.assertRaises(m.SafetyError):m.safe_json({'bad':'sentinel-credential'},['sentinel-credential'])
    def test_empty_assets(self):
        with self.assertRaises(m.SafetyError):m.validate_manifest({})
    def test_asset_escape(self):
        with self.assertRaises(m.SafetyError):m.validate_manifest({'../secret':'a'*64})

if __name__=='__main__':unittest.main()
