#ifndef CONTRACT_SQLITE3VDBERECORDCOMPAREWITHSKIP_H
#define CONTRACT_SQLITE3VDBERECORDCOMPAREWITHSKIP_H
/* C-17, round 4: a BOUNDED measurement contract (nField <= 3), pending Zach's decision on the bound. */
int contract_sqlite3VdbeRecordCompareWithSkip(int nKey1, const void *pKey1, UnpackedRecord *pPKey2, int bSkip)
  __CPROVER_requires(nKey1 >= 0
    && __CPROVER_r_ok(pKey1, (size_t)(nKey1 > 10 + (bSkip != 0) ? nKey1 : 10 + (bSkip != 0)) + 8))
  __CPROVER_requires(__CPROVER_rw_ok(pPKey2, sizeof(UnpackedRecord)))
  __CPROVER_requires(pPKey2->nField >= 1 + (bSkip != 0) && pPKey2->nField <= 3)
  __CPROVER_requires(__CPROVER_r_ok(pPKey2->aMem, sizeof(Mem) * pPKey2->nField))
  __CPROVER_requires(__CPROVER_r_ok(pPKey2->pKeyInfo, SZ_KEYINFO(0)) && pPKey2->pKeyInfo->nAllField >= 1
    && __CPROVER_r_ok(pPKey2->pKeyInfo, SZ_KEYINFO(pPKey2->nField < pPKey2->pKeyInfo->nAllField
                                                  ? pPKey2->nField : pPKey2->pKeyInfo->nAllField)))
  __CPROVER_requires(__CPROVER_r_ok(pPKey2->pKeyInfo->aSortFlags, pPKey2->nField))
  __CPROVER_requires(pPKey2->nField <= 0 || (((pPKey2->aMem[0].flags & (MEM_Int|MEM_IntReal|MEM_Real)) != 0 || (pPKey2->aMem[0].flags & (MEM_Str|MEM_Blob)) == 0
        || ((pPKey2->aMem[0].flags & (MEM_Str|MEM_Zero)) == MEM_Zero ? pPKey2->aMem[0].u.nZero >= 0
        : (pPKey2->aMem[0].n >= 0 && __CPROVER_r_ok(pPKey2->aMem[0].z, pPKey2->aMem[0].n))))
      && (pPKey2->pKeyInfo->nAllField <= 0 || pPKey2->pKeyInfo->aColl[0] == 0
        || __CPROVER_r_ok(pPKey2->pKeyInfo->aColl[0], sizeof(CollSeq)))))
  __CPROVER_requires(pPKey2->nField <= 1 || (((pPKey2->aMem[1].flags & (MEM_Int|MEM_IntReal|MEM_Real)) != 0 || (pPKey2->aMem[1].flags & (MEM_Str|MEM_Blob)) == 0
        || ((pPKey2->aMem[1].flags & (MEM_Str|MEM_Zero)) == MEM_Zero ? pPKey2->aMem[1].u.nZero >= 0
        : (pPKey2->aMem[1].n >= 0 && __CPROVER_r_ok(pPKey2->aMem[1].z, pPKey2->aMem[1].n))))
      && (pPKey2->pKeyInfo->nAllField <= 1 || pPKey2->pKeyInfo->aColl[1] == 0
        || __CPROVER_r_ok(pPKey2->pKeyInfo->aColl[1], sizeof(CollSeq)))))
  __CPROVER_requires(pPKey2->nField <= 2 || (((pPKey2->aMem[2].flags & (MEM_Int|MEM_IntReal|MEM_Real)) != 0 || (pPKey2->aMem[2].flags & (MEM_Str|MEM_Blob)) == 0
        || ((pPKey2->aMem[2].flags & (MEM_Str|MEM_Zero)) == MEM_Zero ? pPKey2->aMem[2].u.nZero >= 0
        : (pPKey2->aMem[2].n >= 0 && __CPROVER_r_ok(pPKey2->aMem[2].z, pPKey2->aMem[2].n))))
      && (pPKey2->pKeyInfo->nAllField <= 2 || pPKey2->pKeyInfo->aColl[2] == 0
        || __CPROVER_r_ok(pPKey2->pKeyInfo->aColl[2], sizeof(CollSeq)))))
  __CPROVER_assigns(pPKey2->errCode, pPKey2->eqSeen);
#endif
