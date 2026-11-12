/* MEASUREMENT ONLY (orchestrator, Zach's item 7, 2026-11-12; local branch wip/c15-unwind; not for merge).
** C-15 on the legacy-unwind pass: the loop is unwound K times with unwinding assertions, so nField <= K is the
** only bound. The key and the cells are allocated at exactly the sizes the contract's requires read: the key
** (nKey > 0 ? nKey : 1) + 8 bytes, the record and its cells mem_offset + sizeof(Mem) * nField. No nKey bound. */
#include "sqlite3.c"
#include "contracts/sqlite3GetVarint32.h"
#include "contracts/sqlite3VdbeSerialGet.h"
#include "contracts/serialGet.h"
#include "contracts/sqlite3VdbeSerialTypeLen.h"
#include "contracts/sqlite3VdbeMemSetNull.h"
#include "contracts/sqlite3VdbeRecordUnpack.h"
#include <stdlib.h>

#ifndef K
#define K 4
#endif

void harness_unwind(void){
  int nKey;
  size_t mem_offset, key_size, cells_size;
  u16 capacity;
  const void *bytes;
  UnpackedRecord *record;
  KeyInfo *key;

  /* SETUP */
  __CPROVER_assume(nKey >= 0);
  __CPROVER_assume(capacity <= K);
  mem_offset = ((sizeof(UnpackedRecord) + 7) / 8) * 8;
  key_size = (size_t)(nKey > 0 ? nKey : 1) + 8;
  cells_size = mem_offset + sizeof(Mem) * capacity;
  bytes = malloc(key_size);
  record = malloc(cells_size);
  key = malloc(sizeof(KeyInfo));
  __CPROVER_assume(bytes != 0 && record != 0 && key != 0);
  record->aMem = (Mem *)((unsigned char *)record + mem_offset);
  record->pKeyInfo = key;
  record->nField = capacity;
  /* END SETUP */

  sqlite3VdbeRecordUnpack(nKey, bytes, record);
}
