import subprocess
from pathlib import Path
cmd=['cc','-std=gnu11','-g','-O1','-fsanitize=address,undefined','-I','upstream','tmp/b4/native.c','-o','tmp/b4/native','-lm','-ldl','-pthread']
with open('tmp/b4/native-build.log','w') as f:
 r=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,timeout=600)
if r.returncode: raise SystemExit('native compile failed')
for label,args in [('native',[]),('native-short0',['0']),('native-short2',['2'])]:
 with open('tmp/b4/'+label+'.log','w') as f:
  r=subprocess.run(['tmp/b4/native',*args],stdout=f,stderr=subprocess.STDOUT,timeout=600)
 text=Path('tmp/b4/'+label+'.log').read_text()
 print(label,'exit',r.returncode)
 print('\n'.join(x for x in text.splitlines() if 'RESULT' in x or 'SUMMARY:' in x or '#0 ' in x or '#1 ' in x or '#2 ' in x))
print('RESULT native experiments complete')
