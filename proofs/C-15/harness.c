#include "sqlite3.c"
#include "contracts/sqlite3GetVarint32.h"
#include "contracts/sqlite3VdbeSerialGet.h"
#include "contracts/serialGet.h"
#include "contracts/sqlite3VdbeSerialTypeLen.h"
#include "contracts/sqlite3VdbeMemSetNull.h"
#include "contracts/sqlite3VdbeRecordUnpack.h"
#include <stdlib.h>

void harness_unpack(void){
  int nKey;
  size_t mem_offset, key_offset, record_offset;
  u16 capacity;
  const void *bytes;
  void *allocation;
  UnpackedRecord *record;
  Mem *cells;
  KeyInfo *key;

  /* SETUP */
  /* Proposed bounds only: pending Zach and auditor approval. */
  __CPROVER_assume(nKey >= 0 && nKey <= 256);
  __CPROVER_assume(capacity <= 4);
  mem_offset = ((sizeof(UnpackedRecord) + 7) / 8) * 8;
  key_offset = 256 - (nKey > 0 ? nKey : 1);
  record_offset = sizeof(Mem) * (4 - capacity);
  bytes = malloc(256 + 8);
  __CPROVER_assume(bytes != 0);
  bytes = bytes + key_offset;
  allocation = malloc(mem_offset + sizeof(Mem) * 4);
  __CPROVER_assume(allocation != 0);
  record = allocation + record_offset;
  cells = allocation + record_offset + mem_offset;
  key = malloc(sizeof(KeyInfo));
  __CPROVER_assume(bytes != 0 && record != 0 && cells != 0 && key != 0);
  record->aMem = cells;
  record->pKeyInfo = key;
  record->nField = capacity;
  /* END SETUP */

  sqlite3VdbeRecordUnpack(nKey, bytes, record);
}
