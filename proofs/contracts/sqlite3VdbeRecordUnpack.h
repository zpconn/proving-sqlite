#ifndef CONTRACT_SQLITE3VDBERECORDUNPACK_H
#define CONTRACT_SQLITE3VDBERECORDUNPACK_H

void contract_sqlite3VdbeRecordUnpack(int nKey, const void *pKey, UnpackedRecord *p)
  __CPROVER_requires(__CPROVER_w_ok(p, sizeof(UnpackedRecord)))
  __CPROVER_requires(__CPROVER_r_ok(p->pKeyInfo,
    offsetof(KeyInfo, db) + sizeof(sqlite3 *)))
  __CPROVER_requires(__CPROVER_w_ok(p->aMem, sizeof(Mem) * p->nField))
  __CPROVER_requires(p->nField > 0)
  __CPROVER_requires(((size_t)p->aMem % 8) == 0)
  __CPROVER_requires(nKey >= 0 && __CPROVER_r_ok(pKey, (size_t)(nKey > 0 ? nKey : 1) + 8))
  __CPROVER_assigns(p->default_rc, p->nField,
    __CPROVER_object_upto(p->aMem, sizeof(Mem) * p->nField))
  __CPROVER_ensures(p->default_rc == 0)
  __CPROVER_ensures(p->nField <= __CPROVER_old(p->nField));

#endif
