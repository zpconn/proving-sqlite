import subprocess, resource
from pathlib import Path
resource.setrlimit(resource.RLIMIT_AS,(24*1024**3,24*1024**3))
checks=[x for x in Path('proofs/CHECKS').read_text().splitlines() if x.startswith('--')]
cmds=[['goto-cc','-m64','tmp/b4/frame-toy.c','--function','entry','-o','tmp/b4/toy.goto'],['goto-instrument','--apply-loop-contracts','tmp/b4/toy.goto','tmp/b4/toy.loop'],['goto-instrument','--enforce-contract','f','tmp/b4/toy.loop','tmp/b4/toy.enforced'],['cbmc','tmp/b4/toy.enforced',*checks]]
for i,cmd in enumerate(cmds):
  with open(f'tmp/b4/toy-{i}.log','w') as log:
    r=subprocess.run(['nice','-n','10',*cmd],stdout=log,stderr=subprocess.STDOUT,timeout=600)
  print(i,r.returncode)
  if r.returncode: break
print(Path(f'tmp/b4/toy-{i}.log').read_text()[-5000:])
print(Path('.campaign/usage').read_text())
print('RESULT toy complete')
