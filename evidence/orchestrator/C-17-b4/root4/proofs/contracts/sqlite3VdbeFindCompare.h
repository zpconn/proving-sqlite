#ifndef CONTRACT_SQLITE3VDBEFINDCOMPARE_H
#define CONTRACT_SQLITE3VDBEFINDCOMPARE_H

RecordCompare contract_sqlite3VdbeFindCompare(UnpackedRecord *p)
  __CPROVER_requires(__CPROVER_w_ok(p, sizeof(*p)))
  __CPROVER_requires(__CPROVER_r_ok(p->pKeyInfo, SZ_KEYINFO(1)))
  __CPROVER_requires(__CPROVER_r_ok(p->aMem, sizeof(Mem)))
  __CPROVER_requires(__CPROVER_r_ok(p->pKeyInfo->aSortFlags, 1))
  __CPROVER_requires(p->pKeyInfo->nAllField > 13 ||
    (p->pKeyInfo->aSortFlags[0] & KEYINFO_ORDER_BIGNULL) != 0 ||
    (p->aMem[0].flags & (MEM_Int|MEM_Str|MEM_Real|MEM_IntReal|MEM_Null|MEM_Blob)) != 0 ||
    p->pKeyInfo->aColl[0] != 0)
  __CPROVER_assigns(p->r1, p->r2, p->u, p->n)
  __CPROVER_ensures(__CPROVER_return_value == sqlite3VdbeRecordCompare ||
                    __CPROVER_return_value == vdbeRecordCompareInt ||
                    __CPROVER_return_value == vdbeRecordCompareString)
  __CPROVER_ensures(__CPROVER_return_value != vdbeRecordCompareInt ||
    (p->pKeyInfo->nAllField <= 13 && (p->aMem[0].flags & MEM_Int) != 0 &&
     p->u.i == p->aMem[0].u.i))
  __CPROVER_ensures(__CPROVER_return_value != vdbeRecordCompareString ||
    (p->pKeyInfo->nAllField <= 13 && (p->aMem[0].flags & MEM_Str) != 0 &&
     (p->aMem[0].flags & (MEM_Int|MEM_Real|MEM_IntReal|MEM_Null|MEM_Blob)) == 0 &&
     p->pKeyInfo->aColl[0] == 0 &&
     p->u.z == p->aMem[0].z && p->n == p->aMem[0].n))
  __CPROVER_ensures(__CPROVER_return_value == sqlite3VdbeRecordCompare ||
    ((p->pKeyInfo->aSortFlags[0] & KEYINFO_ORDER_BIGNULL) == 0 &&
     p->r1 == (p->pKeyInfo->aSortFlags[0] ? 1 : -1) && p->r2 == -p->r1));

#endif
