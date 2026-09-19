#!/usr/bin/env python3
import unittest
from studio_recovery import BEGIN,END,prepare_hook,RUNNER
class Gate(unittest.TestCase):
 def setUp(self):self.block=b'\n'+BEGIN+b'\npython3 safe.py &\n'+END+b'\n'
 def test_preserves_every_original_byte(self):
  old=b'#!/bin/bash\n# existing setup\necho ready\n'
  self.assertEqual(prepare_hook(old,self.block),old+self.block)
 def test_idempotent(self):
  once=prepare_hook(b'#!/bin/bash\n',self.block)
  self.assertEqual(prepare_hook(once,self.block),once)
 def test_refuses_conflicting_block(self):
  with self.assertRaises(ValueError):prepare_hook(BEGIN+b'\nother\n'+END,self.block)
 def test_refuses_duplicate_block(self):
  with self.assertRaises(ValueError):prepare_hook(self.block*2,self.block)
 def test_refuses_exit(self):
  with self.assertRaises(ValueError):prepare_hook(b'#!/bin/bash\nexit 0\n',self.block)
 def test_refuses_exec(self):
  with self.assertRaises(ValueError):prepare_hook(b'#!/bin/bash\nexec service\n',self.block)
 def test_refuses_heredoc(self):
  with self.assertRaises(ValueError):prepare_hook(b'cat <<EOF\n',self.block)
 def test_runner_compiles(self):compile(RUNNER,'resume','exec')
if __name__=='__main__':unittest.main()
