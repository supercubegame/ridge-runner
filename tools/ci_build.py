#!/usr/bin/env python3
import hashlib,json,os,pathlib,shutil,subprocess,sys,urllib.request,zipfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/'out';CACHE=ROOT/'.cache';VERSION='4.5.1'

def download(url,path):
    with urllib.request.urlopen(url,timeout=120) as r,open(path,'wb') as w:shutil.copyfileobj(r,w)

def unpack(file,dest):
    with zipfile.ZipFile(file) as z:
        for e in z.infolist():
            p=pathlib.PurePosixPath(e.filename)
            if p.is_absolute() or '..' in p.parts or '\\' in e.filename or (e.external_attr>>16)&0o170000==0o120000:raise ValueError('Unsafe archive member')
        z.extractall(dest)

def run(command):
    print('RUN',command,flush=True)
    r=subprocess.run(command,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=300)
    print(r.stdout,flush=True)
    if r.returncode or any(s in r.stdout for s in ('SCRIPT ERROR:','Parse Error:','ERROR:')):raise RuntimeError('Command failed; see output above')

def main():
    OUT.mkdir(exist_ok=True);CACHE.mkdir(exist_ok=True)
    base=f'https://github.com/godotengine/godot/releases/download/{VERSION}-stable/'
    download(base+'SHA512-SUMS.txt',CACHE/'sums')
    sums={bits[1].lstrip('*'):bits[0] for line in (CACHE/'sums').read_text().splitlines() if len(bits:=line.split())==2}
    editor=f'Godot_v{VERSION}-stable_linux.x86_64.zip';templates=f'Godot_v{VERSION}-stable_export_templates.tpz'
    for name in [editor,templates]:
        file=CACHE/name;download(base+name,file)
        h=hashlib.sha512()
        with file.open('rb') as f:
            for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
        if h.hexdigest()!=sums[name]:raise RuntimeError('Official checksum mismatch')
    unpack(CACHE/editor,CACHE/'editor');unpack(CACHE/templates,CACHE/'templates')
    binary=next((CACHE/'editor').glob('Godot*'));binary.chmod(0o755)
    target=pathlib.Path.home()/'.local/share/godot/export_templates'/f'{VERSION}.stable'
    shutil.copytree(CACHE/'templates/templates',target,dirs_exist_ok=True)
    os.environ['GODOT']=str(binary)
    version=subprocess.check_output([str(binary),'--version'],text=True).strip()
    if not version.startswith(VERSION+'.stable'):raise RuntimeError('Editor version mismatch')
    run([sys.executable,str(ROOT/'tools/engine_gate.py')])
    for key,preset,file in [('web','Web','index.html'),('windows','Windows','RidgeRunner.exe')]:
        directory=OUT/key;directory.mkdir(exist_ok=True)
        run([str(binary),'--headless','--path',str(ROOT/'game'),'--export-release',preset,str(directory/file)])
        if not (directory/file).is_file():raise RuntimeError('Export missing')
        if key=='web':
            for pattern in ['*.wasm','*.pck','*.js']:
                if not list(directory.glob(pattern)):raise RuntimeError('Web companion missing: '+pattern)
        if key=='windows':
            with (directory/file).open('rb') as f:
                if f.read(2)!=b'MZ':raise RuntimeError('Windows PE signature missing')
        shutil.copy2(ROOT/'LICENSE',directory/'LICENSE.txt')
        (directory/'ENGINE-NOTICES.txt').write_text('Godot Engine (MIT). Full engine and dependency license notices: https://godotengine.org/license/\nCopyright Godot Engine contributors.\n')
        if key=='web':(directory/'PLAY.txt').write_text('Run python3 -m http.server 8060 in this folder. Open http://localhost:8060\nWASD move, Space jump, right mouse look, R restart.\n')
        shutil.make_archive(str(OUT/f'RidgeRunner-{key}'),'zip',directory)
    manifest={'sha':os.environ.get('GITHUB_SHA'),'run':os.environ.get('GITHUB_RUN_ID'),'godot':version,'engine':'PASS','exports':['web','windows'],'native_device_acceptance':'SKIP','files':[]}
    for f in OUT.glob('RidgeRunner-*.zip'):
        manifest['files'].append({'name':f.name,'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'bytes':f.stat().st_size})
    (OUT/'build.json').write_text(json.dumps(manifest,indent=2))
    print('PASS real engine gates and Web/Windows exports',flush=True)
if __name__=='__main__':main()
