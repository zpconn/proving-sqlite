#ifndef CONTRACT_SQLITE3VDBEALLOCUNPACKEDRECORD_H
#define CONTRACT_SQLITE3VDBEALLOCUNPACKEDRECORD_H

UnpackedRecord *contract_sqlite3VdbeAllocUnpackedRecord(KeyInfo *pKeyInfo)
  __CPROVER_requires(__CPROVER_r_ok(pKeyInfo,
    __builtin_offsetof(KeyInfo, db) + sizeof(sqlite3 *)))
  __CPROVER_requires(pKeyInfo->nKeyField < 65535)
  __CPROVER_assigns()
  __CPROVER_ensures(__CPROVER_return_value == 0 ||
    __CPROVER_w_ok(__CPROVER_return_value, sizeof(UnpackedRecord)))
  __CPROVER_ensures(__CPROVER_return_value == 0 ||
    __CPROVER_return_value->pKeyInfo == pKeyInfo)
  __CPROVER_ensures(__CPROVER_return_value == 0 ||
    __CPROVER_return_value->nField == pKeyInfo->nKeyField + 1)
  __CPROVER_ensures(__CPROVER_return_value == 0 ||
    __CPROVER_w_ok(__CPROVER_return_value->aMem,
      sizeof(Mem) * __CPROVER_return_value->nField));

#endif
