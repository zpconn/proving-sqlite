#include "sqlite3.c"
#include "contracts/sqlite3GetVarint32.h"
#include "contracts/sqlite3VdbeSerialGet.h"
#include "contracts/serialGet7.h"
#include "contracts/sqlite3VdbeSerialTypeLen.h"
#include "contracts/sqlite3VarintLen.h"
#include "contracts/vdbeRecordDecodeInt.h"
#include "contracts/sqlite3IntFloatCompare.h"
#include "contracts/isAllZero.h"
#include "contracts/vdbeCompareMemString.h"
#include "contracts/sqlite3CorruptError.h"
#include <stdlib.h>

/* SCRATCH PROBE (T-006): contract without the per-field pointer obligations, which CBMC can't state. */
int contract_sqlite3VdbeRecordCompareWithSkip(int nKey1, const void *pKey1, UnpackedRecord *pPKey2, int bSkip)
  __CPROVER_requires(nKey1 >= 0)
  __CPROVER_requires(__CPROVER_r_ok(pKey1, (size_t)(nKey1 > (bSkip ? 11 : 10) ? nKey1 : (bSkip ? 11 : 10)) + 8))
  __CPROVER_requires(__CPROVER_rw_ok(pPKey2, sizeof(UnpackedRecord)))
  __CPROVER_requires(pPKey2->nField >= (bSkip ? 2 : 1))
  __CPROVER_requires(__CPROVER_r_ok(pPKey2->aMem, sizeof(Mem) * pPKey2->nField))
  __CPROVER_requires(__CPROVER_r_ok(pPKey2->pKeyInfo, SZ_KEYINFO(0)))
  __CPROVER_requires(__CPROVER_r_ok(pPKey2->pKeyInfo, SZ_KEYINFO(pPKey2->nField < pPKey2->pKeyInfo->nAllField ? pPKey2->nField : pPKey2->pKeyInfo->nAllField)))
  __CPROVER_requires(__CPROVER_r_ok(pPKey2->pKeyInfo->aSortFlags, pPKey2->nField))
  __CPROVER_assigns(pPKey2->errCode, pPKey2->eqSeen);

void harness_cmp(void){
  int nKey1; int bSkip; size_t extent; size_t nmem; size_t ncoll;
  const void *key; UnpackedRecord *p; Mem *mem; KeyInfo *ki; u8 *sort;
  /* SETUP */
  __CPROVER_assume(extent <= 2147483647u + 19u && nmem <= 65535 && ncoll <= 65535);
  key = malloc(extent);
  p = malloc(sizeof(UnpackedRecord));
  mem = malloc(nmem * sizeof(Mem));
  ki = malloc(sizeof(KeyInfo) + ncoll * sizeof(CollSeq*));
  sort = malloc(nmem);
  __CPROVER_assume(key != 0 && p != 0 && mem != 0 && ki != 0 && sort != 0);
  p->pKeyInfo = ki;
  p->aMem = mem;
  ki->aSortFlags = sort;
  /* END SETUP */
  sqlite3VdbeRecordCompareWithSkip(nKey1, key, p, bSkip);
}
