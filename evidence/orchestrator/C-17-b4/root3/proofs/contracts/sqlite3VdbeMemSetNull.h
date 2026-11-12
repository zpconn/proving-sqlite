#ifndef CONTRACT_SQLITE3VDBEMEMSETNULL_H
#define CONTRACT_SQLITE3VDBEMEMSETNULL_H

void contract_sqlite3VdbeMemSetNull(Mem *pMem)
  __CPROVER_requires(__CPROVER_w_ok(pMem, offsetof(Mem, flags) + sizeof(pMem->flags)))
  __CPROVER_requires(!VdbeMemDynamic(pMem))
  __CPROVER_assigns(pMem->flags)
  __CPROVER_ensures(pMem->flags == MEM_Null);

#endif
