import unittest
import start_only as s

class Tests(unittest.TestCase):
    def policy(self):
        p=s.Policy();p.route=('POST','/v1/projects/team/cloudspaces/studio/start');return p
    def test_get(self):
        self.policy().check('GET','lightning.ai','/v1/projects')
    def test_start_once(self):
        p=self.policy();p.armed=True;p.check('POST','lightning.ai',p.route[1])
        self.assertEqual(p.starts,1)
        p.armed=True
        with self.assertRaises(s.h.SafetyError):p.check('POST','lightning.ai',p.route[1])
    def test_unarmed(self):
        p=self.policy()
        with self.assertRaises(s.h.SafetyError):p.check('POST','lightning.ai',p.route[1])
    def test_forbidden_writes(self):
        for method,path in [('POST','/stop'),('PUT','/endpoint'),('DELETE','/studio'),('POST','/other/start')]:
            p=self.policy();p.armed=True
            with self.assertRaises(s.h.SafetyError):p.check(method,'lightning.ai',path)
            self.assertEqual(p.starts,0)
    def test_bad_reads(self):
        for host,path in [('evil.example','/'),('lightning.ai','/keepalive'),('lightning.ai','http://lightning.ai/')]:
            with self.assertRaises(s.h.SafetyError):self.policy().check('GET',host,path)
    def test_public_write(self):
        p=self.policy();p.armed=True
        with self.assertRaises(s.h.SafetyError):p.check('POST',s.h.PREVIEW_HOST,p.route[1])
    def test_secret(self):
        with self.assertRaises(s.h.SafetyError):s.h.safe_json({'x':'SENTINEL_SECRET'},['SENTINEL_SECRET'])
    def test_cpu_config(self):
        s.check_config('cpu-4',False,False,0)
        for args in [('gpu',False,False,0),('cpu-8',False,False,0),('cpu-4',True,False,0),('cpu-4',False,True,0),('cpu-4',False,False,600)]:
            with self.assertRaises(s.h.SafetyError):s.check_config(*args)

if __name__=='__main__':unittest.main()
