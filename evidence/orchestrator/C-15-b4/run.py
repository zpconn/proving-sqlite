from pathlib import Path
import subprocess, sys, json
label=sys.argv[1]
config=sys.argv[2] if len(sys.argv)>2 else 'lp64-le'
base=Path('tmp/b4')
cmd=['/usr/bin/time','-f','elapsed_s=%e peak_rss_kib=%M','-o',str(base/(label+'.time')),'nice','-n','10','python3','tools/prove.py','prove','--card-dir','proofs/C-15','--config',config,'--build-dir',str(base/label),'--trace']
with (base/(label+'.log')).open('w') as f:
 r=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT)
s=(base/(label+'.log')).read_text()
print('\n'.join(s.splitlines()[-8:]))
print((base/(label+'.time')).read_text())
print(Path('.campaign/usage').read_text())
print('RESULT measurement',label,'exit',r.returncode)
