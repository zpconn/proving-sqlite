#ifndef CONTRACT_SQLITE3VDBERECORDCOMPAREWITHSKIP_H
#define CONTRACT_SQLITE3VDBERECORDCOMPAREWITHSKIP_H
/* C-17, round 4: a BOUNDED measurement contract (nField <= 8), pending Zach's decision on the bound. */
int contract_sqlite3VdbeRecordCompareWithSkip(int nKey1, const void *pKey1, UnpackedRecord *pPKey2, int bSkip)
  __CPROVER_requires(nKey1 >= 0
    && __CPROVER_r_ok(pKey1, (size_t)(nKey1 > 10 + (bSkip != 0) ? nKey1 : 10 + (bSkip != 0)) + 8))
  __CPROVER_requires(__CPROVER_rw_ok(pPKey2, sizeof(UnpackedRecord)))
  __CPROVER_requires(pPKey2->nField >= 1 + (bSkip != 0) && pPKey2->nField <= 8)
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
  __CPROVER_requires(pPKey2->nField <= 3 || (((pPKey2->aMem[3].flags & (MEM_Int|MEM_IntReal|MEM_Real)) != 0 || (pPKey2->aMem[3].flags & (MEM_Str|MEM_Blob)) == 0
        || ((pPKey2->aMem[3].flags & (MEM_Str|MEM_Zero)) == MEM_Zero ? pPKey2->aMem[3].u.nZero >= 0
        : (pPKey2->aMem[3].n >= 0 && __CPROVER_r_ok(pPKey2->aMem[3].z, pPKey2->aMem[3].n))))
      && (pPKey2->pKeyInfo->nAllField <= 3 || pPKey2->pKeyInfo->aColl[3] == 0
        || __CPROVER_r_ok(pPKey2->pKeyInfo->aColl[3], sizeof(CollSeq)))))
  __CPROVER_requires(pPKey2->nField <= 4 || (((pPKey2->aMem[4].flags & (MEM_Int|MEM_IntReal|MEM_Real)) != 0 || (pPKey2->aMem[4].flags & (MEM_Str|MEM_Blob)) == 0
        || ((pPKey2->aMem[4].flags & (MEM_Str|MEM_Zero)) == MEM_Zero ? pPKey2->aMem[4].u.nZero >= 0
        : (pPKey2->aMem[4].n >= 0 && __CPROVER_r_ok(pPKey2->aMem[4].z, pPKey2->aMem[4].n))))
      && (pPKey2->pKeyInfo->nAllField <= 4 || pPKey2->pKeyInfo->aColl[4] == 0
        || __CPROVER_r_ok(pPKey2->pKeyInfo->aColl[4], sizeof(CollSeq)))))
  __CPROVER_requires(pPKey2->nField <= 5 || (((pPKey2->aMem[5].flags & (MEM_Int|MEM_IntReal|MEM_Real)) != 0 || (pPKey2->aMem[5].flags & (MEM_Str|MEM_Blob)) == 0
        || ((pPKey2->aMem[5].flags & (MEM_Str|MEM_Zero)) == MEM_Zero ? pPKey2->aMem[5].u.nZero >= 0
        : (pPKey2->aMem[5].n >= 0 && __CPROVER_r_ok(pPKey2->aMem[5].z, pPKey2->aMem[5].n))))
      && (pPKey2->pKeyInfo->nAllField <= 5 || pPKey2->pKeyInfo->aColl[5] == 0
        || __CPROVER_r_ok(pPKey2->pKeyInfo->aColl[5], sizeof(CollSeq)))))
  __CPROVER_requires(pPKey2->nField <= 6 || (((pPKey2->aMem[6].flags & (MEM_Int|MEM_IntReal|MEM_Real)) != 0 || (pPKey2->aMem[6].flags & (MEM_Str|MEM_Blob)) == 0
        || ((pPKey2->aMem[6].flags & (MEM_Str|MEM_Zero)) == MEM_Zero ? pPKey2->aMem[6].u.nZero >= 0
        : (pPKey2->aMem[6].n >= 0 && __CPROVER_r_ok(pPKey2->aMem[6].z, pPKey2->aMem[6].n))))
      && (pPKey2->pKeyInfo->nAllField <= 6 || pPKey2->pKeyInfo->aColl[6] == 0
        || __CPROVER_r_ok(pPKey2->pKeyInfo->aColl[6], sizeof(CollSeq)))))
  __CPROVER_requires(pPKey2->nField <= 7 || (((pPKey2->aMem[7].flags & (MEM_Int|MEM_IntReal|MEM_Real)) != 0 || (pPKey2->aMem[7].flags & (MEM_Str|MEM_Blob)) == 0
        || ((pPKey2->aMem[7].flags & (MEM_Str|MEM_Zero)) == MEM_Zero ? pPKey2->aMem[7].u.nZero >= 0
        : (pPKey2->aMem[7].n >= 0 && __CPROVER_r_ok(pPKey2->aMem[7].z, pPKey2->aMem[7].n))))
      && (pPKey2->pKeyInfo->nAllField <= 7 || pPKey2->pKeyInfo->aColl[7] == 0
        || __CPROVER_r_ok(pPKey2->pKeyInfo->aColl[7], sizeof(CollSeq)))))
  __CPROVER_assigns(pPKey2->errCode, pPKey2->eqSeen);
#endif
