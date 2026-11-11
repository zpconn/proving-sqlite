import sys,json
sys.path.insert(0,'tools')
import prove
from pathlib import Path
lm=prove.ov.LineMap(Path('overlay/sqlite3.c').read_bytes())
for cfg in ('lp64-le','ilp32-le','lp64-be'):
 p=Path('tmp/b4/coverage')/cfg/'unpack.cover.cbmc'
 b=[(ls,s) for f,ls,s in prove.parse_cover(p.read_text(),'overlay/sqlite3.c') if f=='__CPROVER_contracts_original_sqlite3VdbeRecordUnpack']
 all_=sorted({lm.upstream_line(i) for ls,s in b for i in ls if 92116<=lm.upstream_line(i)<=92159})
 unc=sorted({lm.upstream_line(i) for ls,s in b if not s for i in ls if 92116<=lm.upstream_line(i)<=92159})
 print(cfg,'raw',len(b),'blocks',sum(not s for ls,s in b),'failed;',len(all_),'C-15 lines; uncovered',unc)
for p in sorted(Path('tmp/b4').glob('*/prove-summary.json')):
 for r in json.loads(p.read_text()):
  print(p.parent.name,r['config'],r['status'],r.get('cbmc_seconds'),r['seconds'],r['properties'],r['failed'])
