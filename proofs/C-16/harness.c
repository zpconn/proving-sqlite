#include "sqlite3.c"
#include "contracts/sqlite3VdbeFindCompare.h"
#include <stdlib.h>

void harness_sqlite3VdbeFindCompare(void){
  UnpackedRecord *p;
  KeyInfo *key;
  Mem *mem;
  u8 *sort;
  size_t p_extent, mem_extent, sort_extent;

  /* SETUP */
  __CPROVER_assume(p_extent >= (sizeof(KeyInfo*) + sizeof(Mem*)) &&
                   p_extent <= sizeof(UnpackedRecord) + 1);
  __CPROVER_assume(mem_extent <= sizeof(Mem) + 1 && sort_extent <= 2);
  p = malloc(p_extent);
  key = malloc(sizeof(KeyInfo) + sizeof(CollSeq*));
  mem = malloc(mem_extent);
  sort = malloc(sort_extent);
  __CPROVER_assume(p != 0 && key != 0 && mem != 0 && sort != 0);
  p->pKeyInfo = key;
  p->aMem = mem;
  key->aSortFlags = sort;
  /* END SETUP */

  sqlite3VdbeFindCompare(p);
  /* SETUP's call allowlist excludes SZ_KEYINFO; check the exact size here. */
  __CPROVER_assert(__CPROVER_OBJECT_SIZE(key) == SZ_KEYINFO(1),
                   "KeyInfo allocation is exactly one whole entry");
}
