#include "sqlite3.c"
#include "contracts/sqlite3VdbeFindCompare.h"
#include <stdlib.h>

void harness_sqlite3VdbeFindCompare(void){
  UnpackedRecord *p;
  KeyInfo *key;
  Mem *mem;
  u8 *sort;
  size_t extra, p_extent, mem_extent, sort_extent;

  /* SETUP */
  __CPROVER_assume(p_extent >= (sizeof(KeyInfo*) + sizeof(Mem*)) &&
                   p_extent <= sizeof(UnpackedRecord) + 1);
  __CPROVER_assume(mem_extent <= sizeof(Mem) + 1 && sort_extent <= 2);
  p = malloc(p_extent);
  __CPROVER_assume(extra <= sizeof(CollSeq*) + 1);
  key = malloc(sizeof(KeyInfo) + extra);
  mem = malloc(mem_extent);
  sort = malloc(sort_extent);
  __CPROVER_assume(p != 0 && key != 0 && mem != 0 && sort != 0);
  p->pKeyInfo = key;
  p->aMem = mem;
  key->aSortFlags = sort;
  /* END SETUP */

  sqlite3VdbeFindCompare(p);
}
