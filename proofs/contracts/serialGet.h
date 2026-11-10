#ifndef CONTRACT_SERIALGET_H
#define CONTRACT_SERIALGET_H
void contract_serialGet(const unsigned char *buf, u32 serial_type, Mem *pMem)
  __CPROVER_requires(__CPROVER_r_ok(buf, 8))
  __CPROVER_requires(__CPROVER_w_ok(pMem, sizeof(Mem)))
  __CPROVER_assigns(pMem->u, pMem->flags)
  __CPROVER_ensures(serial_type == 6 ? pMem->flags == MEM_Int :
    (pMem->flags == MEM_Null || pMem->flags == MEM_Real));
#endif
