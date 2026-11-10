/* Boundary contract for vdbeCompareMemString (upstream/sqlite3.c:92350), replaced at its calls in C-17 (sqlite3VdbeRecordCompareWithSkip, call at 92734).
   Ledger: A-003. The clause below is LEDGER.md A-003's, word for word (scan.py checks it); written at
   checkpoint 1 and frozen in proof.lock. Builders do not change it. */
int contract_vdbeCompareMemString(const Mem *pMem1, const Mem *pMem2, const CollSeq *pColl, u8 *prcErr)
  __CPROVER_requires(__CPROVER_r_ok(pMem1, sizeof(Mem)) && __CPROVER_r_ok(pMem2, sizeof(Mem))
                     && __CPROVER_r_ok(pColl, sizeof(CollSeq)))
  __CPROVER_requires(pMem1->n >= 0 && __CPROVER_r_ok(pMem1->z, pMem1->n)
                     && pMem2->n >= 0 && __CPROVER_r_ok(pMem2->z, pMem2->n))
  __CPROVER_requires(prcErr == NULL || __CPROVER_w_ok(prcErr, 1))
  __CPROVER_assigns(prcErr != NULL: *prcErr);
