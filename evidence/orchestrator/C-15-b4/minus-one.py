from pathlib import Path
import subprocess
h=Path('proofs/C-15/harness.c'); c=Path('proofs/contracts/sqlite3VdbeRecordUnpack.h')
h0=h.read_text(); c0=c.read_text()
try:
 for n in (0,2):
  h.write_text(h0.replace('__CPROVER_assume(nKey >= 0 && nKey <= 256);',f'nKey = {n};').replace('malloc(256 + 8)','malloc(256 + 7)'))
  c.write_text(c0.replace('(size_t)(nKey > 0 ? nKey : 1) + 8','(size_t)(nKey > 0 ? nKey : 1) + 7'))
  subprocess.run(['python3','tmp/b4/run.py',f'minus-one-n{n}'],check=True)
finally:
 h.write_text(h0);c.write_text(c0)
print('RESULT minus-one experiments complete; retained files restored')
