from pathlib import Path
import subprocess
p=Path('proofs/contracts/sqlite3VdbeRecordUnpack.h');s=p.read_text()
try:
 t=s
 for i in range(4):t=t.replace(f', p->aMem[{i}].enc','')
 p.write_text(t)
 subprocess.run(['python3','tmp/b4/run.py','missing-enc-ilp32','ilp32-le'],check=True)
finally:p.write_text(s)
print('RESULT missing-enc diagnostic complete; retained frame restored')
