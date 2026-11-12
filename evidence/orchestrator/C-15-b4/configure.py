from pathlib import Path
import sys
k,n=map(int,sys.argv[1:3])
h=Path('proofs/C-15/harness.c')
s=h.read_text()
import re
s=re.sub(r'__CPROVER_assume\(nKey >= 0[^;]*;', f'__CPROVER_assume(nKey >= 0 && nKey <= {n});',s)
if '__CPROVER_assume(capacity <=' in s:
 s=re.sub(r'__CPROVER_assume\(capacity <= \d+\);',f'__CPROVER_assume(capacity <= {k});',s)
else:
 s=s.replace('  mem_offset =',f'  __CPROVER_assume(capacity <= {k});\n  mem_offset =')
s=re.sub(r'key_offset = \d+ -',f'key_offset = {n} -',s)
s=re.sub(r'record_offset = sizeof\(Mem\) \* \(\d+ -',f'record_offset = sizeof(Mem) * ({k} -',s)
s=re.sub(r'bytes = malloc\(\d+ \+ 8\);',f'bytes = malloc({n} + 8);',s)
s=re.sub(r'allocation = malloc\(mem_offset \+ sizeof\(Mem\) \* \d+\);',f'allocation = malloc(mem_offset + sizeof(Mem) * {k});',s)
h.write_text(s)
p=Path('proofs/contracts/sqlite3VdbeRecordUnpack.h')
s=p.read_text()
start=s.index('  __CPROVER_assigns(')
end=s.index('  __CPROVER_ensures',start)
frame='  __CPROVER_assigns(1: p->default_rc, p->nField;\n'
for i in range(k):
 frame+=f'    p->nField > {i}: '+', '.join(f'p->aMem[{i}].{m}' for m in ['u','z','n','flags','enc','db','szMalloc'])+(';' if i+1<k else ')')+'\n'
p.write_text(s[:start]+frame+s[end:])
print(f'Configured measurement K={k}, N={n}; no frozen property changed')
