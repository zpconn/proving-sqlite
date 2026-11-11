#ifndef CONTRACT_SQLITE3VDBERECORDUNPACK_H
#define CONTRACT_SQLITE3VDBERECORDUNPACK_H

/* Measurement candidate only; not approved for replacement. See reports/C-15-b4.md. */
void contract_sqlite3VdbeRecordUnpack(int nKey, const void *pKey, UnpackedRecord *p)
  __CPROVER_requires(__CPROVER_w_ok(p, sizeof(UnpackedRecord)))
  __CPROVER_requires(__CPROVER_r_ok(p->pKeyInfo,
    offsetof(KeyInfo, db) + sizeof(sqlite3 *)))
  __CPROVER_requires(__CPROVER_w_ok(p->aMem, sizeof(Mem) * p->nField))
  __CPROVER_requires(p->aMem == (Mem *)((unsigned char *)p +
    ((sizeof(UnpackedRecord) + 7) / 8) * 8))
  __CPROVER_requires(!__CPROVER_same_object(p, pKey) &&
    !__CPROVER_same_object(p, p->pKeyInfo))
  __CPROVER_requires(p->nField > 0)
  __CPROVER_requires(((size_t)p->aMem % 8) == 0)
  __CPROVER_requires(nKey >= 0 && __CPROVER_r_ok(pKey, (size_t)(nKey > 0 ? nKey : 1) + 8))
  __CPROVER_assigns(1: p->default_rc, p->nField;
    p->nField > 0: p->aMem[0].u, p->aMem[0].z, p->aMem[0].n, p->aMem[0].flags, p->aMem[0].enc, p->aMem[0].db, p->aMem[0].szMalloc;
    p->nField > 1: p->aMem[1].u, p->aMem[1].z, p->aMem[1].n, p->aMem[1].flags, p->aMem[1].enc, p->aMem[1].db, p->aMem[1].szMalloc;
    p->nField > 2: p->aMem[2].u, p->aMem[2].z, p->aMem[2].n, p->aMem[2].flags, p->aMem[2].enc, p->aMem[2].db, p->aMem[2].szMalloc;
    p->nField > 3: p->aMem[3].u, p->aMem[3].z, p->aMem[3].n, p->aMem[3].flags, p->aMem[3].enc, p->aMem[3].db, p->aMem[3].szMalloc)
  __CPROVER_ensures(p->default_rc == 0)
  __CPROVER_ensures(p->nField <= __CPROVER_old(p->nField));

#endif
