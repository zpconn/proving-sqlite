from pathlib import Path
import resource,subprocess,json
resource.setrlimit(resource.RLIMIT_AS,(24*1024**3,24*1024**3))
checks=[s for s in Path('proofs/CHECKS').read_text().splitlines() if s.startswith('--')]
base=Path('tmp/b4/frame-toy.c').read_text()
for label,src in [
 ('tail-bad',base),
 ('tail-good',base.replace('p->b=0','p->a=0')),
 ('exact-bad',base.replace('__CPROVER_object_from(p)','cells[0].a,cells[n-1].a')),
 ('direct-bad',base[:base.index('  unsigned i=0;')]+'  cells[0].b=0;\n}'+base[base.index('\nvoid entry'):]),
 ('tail-unguarded-bad',base.replace('1: cells[0].a; n>1: cells[1].a','cells[0].a,cells[n-1].a'))
]:
 d=Path('tmp/b4')/label;d.mkdir(exist_ok=True);(d/'toy.c').write_text(src)
 cmds=[['goto-cc','-m64',str(d/'toy.c'),'--function','entry','-o',str(d/'a.goto')],['goto-instrument','--apply-loop-contracts',str(d/'a.goto'),str(d/'b.goto')],['goto-instrument','--enforce-contract','f',str(d/'b.goto'),str(d/'c.goto')],['cbmc',str(d/'c.goto'),*checks]]
 for i,cmd in enumerate(cmds):
  with (d/f'{i}.log').open('w') as f:r=subprocess.run(['nice','-n','10',*cmd],stdout=f,stderr=subprocess.STDOUT,timeout=600)
  if r.returncode:break
 text=(d/f'{i}.log').read_text()
 print(label,'stage',i,'rc',r.returncode)
 print('\n'.join(x for x in text.splitlines() if 'FAILURE' in x or 'VERIFICATION' in x or 'of ' in x and 'failed' in x))
 print(Path('.campaign/usage').read_text().splitlines()[0])
print('RESULT frame-suite complete')
