#include "sqlite3.c"
#include "contracts/sqlite3VdbeRecordCompareWithSkip.h"
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
#include "contracts/memcmp.h"
#include <stdlib.h>

/* C-17 round 4, bounded measurement harness: nField <= 2, string/blob lengths <= 16. */
void harness_cmp(void){
  int nKey1;
  const void *pKey1;
  UnpackedRecord *pPKey2;
  int bSkip;
  size_t ext, nA, nF;
  u16 nField, nAllField;
  KeyInfo *ki;
  Mem *mem;
  u8 *sf;
  size_t k1, a1;
  Mem *m1;
  char *z1;
  int n1;
  CollSeq *c1;
  size_t k0, a0;
  Mem *m0;
  char *z0;
  int n0;
  CollSeq *c0;

  /* SETUP */
  __CPROVER_assume(nKey1 >= 0 && nKey1 <= 16);
  ext = (size_t)(nKey1 > 10 + (bSkip != 0) ? nKey1 : 10 + (bSkip != 0)) + 8;
  pKey1 = malloc(ext);
  __CPROVER_assume(nField >= 1 + (bSkip != 0) && nField == 2 && nAllField >= 2);
  nF = nField;
  nA = nField < nAllField ? nField : nAllField;
  pPKey2 = malloc(sizeof(UnpackedRecord));
  mem = malloc(sizeof(Mem) * nF);
  ki = malloc(sizeof(KeyInfo) + sizeof(CollSeq *) * nA);
  sf = malloc(nF);
  __CPROVER_assume(pKey1 != 0 && pPKey2 != 0 && mem != 0 && ki != 0 && sf != 0);
  pPKey2->pKeyInfo = ki;
  pPKey2->aMem = mem;
  pPKey2->nField = nField;
  ki->nAllField = nAllField;
  ki->aSortFlags = sf;
  k1 = 1;
  a1 = 1;
  __CPROVER_assume(n1 >= 0 && n1 <= 16);
  z1 = malloc(n1);
  m1 = mem + k1;
  m1->z = z1;
  m1->n = n1;
  c1 = malloc(sizeof(CollSeq));
  ki->aColl[a1] = c1;
  k0 = 0;
  a0 = 0;
  __CPROVER_assume(n0 >= 0 && n0 <= 16);
  z0 = malloc(n0);
  m0 = mem + k0;
  m0->z = z0;
  m0->n = n0;
  c0 = malloc(sizeof(CollSeq));
  ki->aColl[a0] = c0;
  /* END SETUP */

  sqlite3VdbeRecordCompareWithSkip(nKey1, pKey1, pPKey2, bSkip);
}
