#!/usr/bin/env python3
import os,pathlib,subprocess,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
def main():
    binary=os.environ.get('GODOT','godot')
    for command in [[binary,'--headless','--path',str(ROOT/'game'),'--editor','--import'],[binary,'--headless','--path',str(ROOT/'game'),'--script','res://tests/rules_test.gd'],[binary,'--headless','--path',str(ROOT/'game'),'--script','res://tests/world_test.gd']]:
        r=subprocess.run(command,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
        print(r.stdout,flush=True)
        if r.returncode or any(x in r.stdout for x in ('SCRIPT ERROR:', 'Parse Error:', 'ERROR:')): return 1
    print('PASS real Godot import, rules and world physics; visual/device acceptance separate')
    return 0
if __name__=='__main__':sys.exit(main())
