#ifndef CONTRACT_SERIALGET7_H
#define CONTRACT_SERIALGET7_H
int contract_serialGet7(const unsigned char *buf, Mem *pMem)
  __CPROVER_requires(__CPROVER_r_ok(buf, 8))
  __CPROVER_requires(__CPROVER_w_ok(pMem, sizeof(Mem)))
  __CPROVER_assigns(pMem->u, pMem->flags)
  __CPROVER_ensures(__CPROVER_return_value == 0 || __CPROVER_return_value == 1)
  __CPROVER_ensures(pMem->flags ==
    (__CPROVER_return_value == 1 ? MEM_Null : MEM_Real));
#endif
