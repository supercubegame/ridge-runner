import unittest
import autowake_once as m
class Gates(unittest.TestCase):
    def policy(self):
        p=m.Policy()
        p.routes={'enable':('PUT','/endpoint/e'),'rollback':('PUT','/endpoint/e'),'stop':('POST','/studio/s/stop'),'fallback_start':('POST','/studio/s/start')}
        return p
    def send(self,p,kind):
        p.armed=kind;p.check(p.routes[kind][0],'lightning.ai',p.routes[kind][1])
    def test_get(self):self.policy().check('GET','lightning.ai','/v1/projects')
    def test_no_implicit_write(self):
        with self.assertRaises(m.r.SafetyError):self.policy().check('PUT','lightning.ai','/endpoint/e')
    def test_enable_once(self):
        p=self.policy();self.send(p,'enable')
        with self.assertRaises(m.r.SafetyError):self.send(p,'enable')
    def test_stop_needs_verified_enable(self):
        with self.assertRaises(m.r.SafetyError):self.send(self.policy(),'stop')
    def test_stop_once(self):
        p=self.policy();p.enabled=True;self.send(p,'stop')
        with self.assertRaises(m.r.SafetyError):self.send(p,'stop')
    def test_no_start_in_experiment(self):
        p=self.policy();p.stopped=True
        with self.assertRaises(m.r.SafetyError):self.send(p,'fallback_start')
    def test_no_start_when_running(self):
        p=self.policy();p.recovering=True
        with self.assertRaises(m.r.SafetyError):self.send(p,'fallback_start')
    def test_fallback_once(self):
        p=self.policy();p.recovering=True;p.stopped=True;self.send(p,'fallback_start')
        with self.assertRaises(m.r.SafetyError):self.send(p,'fallback_start')
    def test_no_rollback_before_failure(self):
        with self.assertRaises(m.r.SafetyError):self.send(self.policy(),'rollback')
    def test_rollback_once(self):
        p=self.policy();p.recovering=True;self.send(p,'rollback')
        with self.assertRaises(m.r.SafetyError):self.send(p,'rollback')
    def test_no_wrong_target(self):
        p=self.policy();p.armed='enable'
        with self.assertRaises(m.r.SafetyError):p.check('PUT','lightning.ai','/endpoint/other')
    def test_no_delete(self):
        with self.assertRaises(m.r.SafetyError):self.policy().check('DELETE','lightning.ai','/endpoint/e')
    def test_no_settings(self):
        p=self.policy();p.armed='enable'
        with self.assertRaises(m.r.SafetyError):p.check('PUT','lightning.ai','/sleepconfig')
    def test_no_keepalive(self):
        with self.assertRaises(m.r.SafetyError):self.policy().check('GET','lightning.ai','/keepalive')
    def test_no_bad_host(self):
        with self.assertRaises(m.r.SafetyError):self.policy().check('GET','evil.example','/')
    def test_no_http(self):
        with self.assertRaises(m.r.SafetyError):self.policy().check('GET','lightning.ai','http://lightning.ai/')
    def test_no_public_write(self):
        p=self.policy();p.armed='enable'
        with self.assertRaises(m.r.SafetyError):p.check('PUT',m.r.PREVIEW_HOST,'/endpoint/e')
    def test_quiet_window(self):
        p=self.policy();p.public_allowed=False
        with self.assertRaises(m.r.SafetyError):p.check('GET',m.r.PREVIEW_HOST,'/')
    def test_public_get(self):self.policy().check('GET',m.r.PREVIEW_HOST,'/version.json')
    def test_redaction(self):
        with self.assertRaises(m.r.SafetyError):m.r.safe_json({'x':'sentinel-secret'},['sentinel-secret'])
    def test_browser_no_secrets(self):
        env=m.browser_env({'PATH':'/bin','HOME':'/home/a','LIGHTNING_API_KEY':'sentinel','GH_TOKEN':'sentinel','LIGHTNING_USER_ID':'sentinel'})
        self.assertEqual(env,{'PATH':'/bin','HOME':'/home/a'})
    def test_stopped_requested_not_ignored(self):
        from types import SimpleNamespace as S
        self.assertFalse(m.is_stopped(S(in_use=None,requested=object())))
        self.assertTrue(m.is_stopped(S(in_use=None,requested=None)))
if __name__=='__main__':unittest.main()
